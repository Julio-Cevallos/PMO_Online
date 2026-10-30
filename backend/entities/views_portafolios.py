"""API de portafolios (D-29): grupos de entidades que varias personas gestionan en conjunto."""

from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Count
from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions, status, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.errores import Conflicto
from accounts.models import User
from accounts.permissions import requiere_permiso

from . import auditoria
from .models import InvitacionPortafolio, MembresiaPortafolio, Portafolio
from .portafolios import (
    PERMISO_EDITAR,
    PERMISO_GESTIONAR_MIEMBROS,
    PERMISO_VER,
    ROL_GESTOR,
    membresias_portafolio_activas,
    portafolios_visibles,
    puede_en_portafolio,
    puede_gestionar_rol_de_portafolio,
    roles_asignables_en_portafolio,
)
from .serializers import RolAsignableSerializer
from .serializers_portafolios import (
    InvitacionPortafolioCrearSerializer,
    InvitacionPortafolioSerializer,
    PortafolioMiembroEditarSerializer,
    PortafolioMiembroSerializer,
    PortafolioSerializer,
)


class PortafolioViewSet(viewsets.ModelViewSet):
    """Portafolios: grupos de entidades gestionados en conjunto (D-29).

    - Cada persona ve aquellos donde es miembro; el Admin ve todos.
    - Crear: Admin o Moderador (`entities.create_entity`). Quien crea queda como Gestor.
    - Editar y eliminar (solo si está vacío y no es personal): `entities.edit_portfolio`.
    """

    serializer_class = PortafolioSerializer
    parser_classes = (JSONParser,)
    pagination_class = None
    http_method_names = ("get", "post", "patch", "delete", "head", "options")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return Portafolio.objects.none()
        return portafolios_visibles(self.request.user).annotate(total_entidades=Count("entidades"))

    def get_permissions(self):
        if self.action == "create":
            return [requiere_permiso("entities.create_entity")()]
        return [permissions.IsAuthenticated()]

    def get_serializer_context(self) -> dict:
        contexto = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated:
            contexto["portafolios"] = membresias_portafolio_activas(user)
        return contexto

    @transaction.atomic
    def perform_create(self, serializer: PortafolioSerializer) -> None:
        portafolio = serializer.save()
        MembresiaPortafolio.objects.create(
            usuario=self.request.user,
            portafolio=portafolio,
            rol=Group.objects.get(name=ROL_GESTOR),
            creado_por=self.request.user,
        )
        auditoria.portafolio_creado(self.request, portafolio)

    def update(self, request: Request, *args, **kwargs) -> Response:
        portafolio = self.get_object()
        if not puede_en_portafolio(request.user, portafolio.pk, PERMISO_EDITAR):
            raise PermissionDenied("No tienes permiso para editar este portafolio.")
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def perform_update(self, serializer: PortafolioSerializer) -> None:
        antes = auditoria.foto_portafolio(serializer.instance)
        auditoria.portafolio_editado(self.request, serializer.save(), antes)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        portafolio = self.get_object()
        if not puede_en_portafolio(request.user, portafolio.pk, PERMISO_EDITAR):
            raise PermissionDenied("No tienes permiso para eliminar este portafolio.")
        if portafolio.personal:
            raise Conflicto("El portafolio personal no se elimina.")
        if portafolio.entidades.exists():
            raise Conflicto("El portafolio tiene entidades: muévelas antes de eliminarlo.")
        return super().destroy(request, *args, **kwargs)

    @transaction.atomic
    def perform_destroy(self, instance: Portafolio) -> None:
        # Se registra antes de borrar (después pierde su id), en la misma transacción.
        auditoria.portafolio_eliminado(self.request, instance)
        instance.delete()


class _PortafolioMixin:
    """Resuelve el portafolio de la URL: 404 si no existe o la persona no lo ve."""

    def get_portafolio(self) -> Portafolio:
        if not hasattr(self, "_portafolio"):
            portafolio = (
                portafolios_visibles(self.request.user)
                .filter(pk=self.kwargs["portafolio_id"])
                .first()
            )
            if portafolio is None:
                raise Http404
            self._portafolio = portafolio
        return self._portafolio

    def get_serializer_context(self) -> dict:
        contexto = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            contexto["portafolio"] = self.get_portafolio()
        return contexto

    def exigir(self, permiso: str, mensaje: str) -> Portafolio:
        portafolio = self.get_portafolio()
        if not puede_en_portafolio(self.request.user, portafolio.pk, permiso):
            raise PermissionDenied(mensaje)
        return portafolio


class MiembrosPortafolioView(_PortafolioMixin, generics.ListAPIView):
    """Miembros de un portafolio. Quien lo ve puede ver sus miembros.

    Por defecto solo los activos (`?activa=false` los inactivos, `?activa=todas` todos). Se suman
    por invitación (`/invitations/`).
    """

    serializer_class = PortafolioMiembroSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = None
    filter_backends = ()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return MembresiaPortafolio.objects.none()
        portafolio = self.exigir(PERMISO_VER, "No tienes permiso para ver este portafolio.")
        miembros = MembresiaPortafolio.objects.select_related("usuario", "rol__perfil").filter(
            portafolio=portafolio
        )
        estado = self.request.query_params.get("activa", "true").lower()
        if estado != "todas":
            miembros = miembros.filter(activa=estado != "false")
        return miembros

    @extend_schema(
        parameters=[OpenApiParameter("activa", str, description="true (defecto), false o todas")]
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return self.list(request, *args, **kwargs)


class MiembroPortafolioDetalleView(_PortafolioMixin, generics.RetrieveUpdateDestroyAPIView):
    """Un miembro del portafolio: ver, cambiar su rol o activarlo y desactivarlo (DELETE desactiva).

    Hace falta `entities.manage_portfolio_members` y un nivel igual o mayor al del rol. Nadie
    modifica su propia membresía (salvo el Admin) y el portafolio conserva siempre un Gestor activo.
    """

    serializer_class = PortafolioMiembroSerializer
    parser_classes = (JSONParser,)
    permission_classes = (permissions.IsAuthenticated,)
    http_method_names = ("get", "patch", "delete", "head", "options")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return MembresiaPortafolio.objects.none()
        return MembresiaPortafolio.objects.select_related("usuario", "rol__perfil").filter(
            portafolio=self.get_portafolio()
        )

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        self.exigir(PERMISO_VER, "No tienes permiso para ver este portafolio.")
        return super().retrieve(request, *args, **kwargs)

    def _modificar(self, datos: dict) -> Response:
        self.exigir(
            PERMISO_GESTIONAR_MIEMBROS,
            "No tienes permiso para gestionar los miembros del portafolio.",
        )
        membresia = self.get_object()
        entrada = PortafolioMiembroEditarSerializer(
            membresia, data=datos, partial=True, context=self.get_serializer_context()
        )
        entrada.is_valid(raise_exception=True)
        with transaction.atomic():
            antes = auditoria.foto_miembro_portafolio(membresia)
            entrada.save()
            membresia.refresh_from_db()
            auditoria.miembro_portafolio_editado(self.request, membresia, antes)
        return Response(PortafolioMiembroSerializer(membresia).data)

    @extend_schema(
        request=PortafolioMiembroEditarSerializer, responses={200: PortafolioMiembroSerializer}
    )
    def patch(self, request: Request, *args, **kwargs) -> Response:
        return self._modificar(request.data)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request: Request, *args, **kwargs) -> Response:
        self._modificar({"activa": False})
        return Response(status=status.HTTP_204_NO_CONTENT)


class RolesAsignablesPortafolioView(_PortafolioMixin, generics.ListAPIView):
    """Roles de portafolio que quien consulta puede asignar (nivel igual o menor al propio)."""

    serializer_class = RolAsignableSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = None
    filter_backends = ()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return Group.objects.none()
        portafolio = self.exigir(
            PERMISO_GESTIONAR_MIEMBROS,
            "No tienes permiso para gestionar los miembros del portafolio.",
        )
        return roles_asignables_en_portafolio(self.request.user, portafolio.pk)


def _con_relaciones(consulta):
    return consulta.select_related("portafolio", "usuario", "rol", "invitado_por")


class InvitacionesPortafolioView(_PortafolioMixin, generics.ListCreateAPIView):
    """Invitaciones de un portafolio.

    - GET: quien ve sus miembros. Por defecto las pendientes (`?estado=` otro estado o `todas`).
    - POST: invita a una cuenta que ya existe con un rol de portafolio de nivel igual o menor al
      propio. La persona la acepta o rechaza desde `/api/portfolio-invitations/`.
    """

    serializer_class = InvitacionPortafolioSerializer
    parser_classes = (JSONParser,)
    pagination_class = None
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return InvitacionPortafolio.objects.none()
        portafolio = self.exigir(PERMISO_VER, "No tienes permiso para ver este portafolio.")
        invitaciones = _con_relaciones(InvitacionPortafolio.objects.filter(portafolio=portafolio))
        estado = self.request.query_params.get(
            "estado", InvitacionPortafolio.Estado.PENDIENTE
        ).lower()
        if estado != "todas":
            invitaciones = invitaciones.filter(estado=estado)
        return invitaciones

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "estado",
                str,
                description="pendiente (defecto), aceptada, rechazada, cancelada o todas",
            )
        ]
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return self.list(request, *args, **kwargs)

    @extend_schema(
        request=InvitacionPortafolioCrearSerializer, responses={201: InvitacionPortafolioSerializer}
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        return self.create(request, *args, **kwargs)

    @transaction.atomic
    def create(self, request: Request, *args, **kwargs) -> Response:
        portafolio = self.exigir(
            PERMISO_GESTIONAR_MIEMBROS,
            "No tienes permiso para gestionar los miembros del portafolio.",
        )
        entrada = InvitacionPortafolioCrearSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data

        # Un superusuario no se puede invitar.
        usuario = User.objects.filter(
            username=datos["username"], is_active=True, is_superuser=False
        ).first()
        if usuario is None:
            raise NotFound("Usuario no encontrado.")
        if MembresiaPortafolio.objects.filter(
            usuario=usuario, portafolio=portafolio, activa=True
        ).exists():
            raise Conflicto("La persona ya es miembro de este portafolio.")
        if InvitacionPortafolio.objects.filter(
            usuario=usuario, portafolio=portafolio, estado=InvitacionPortafolio.Estado.PENDIENTE
        ).exists():
            raise Conflicto("La persona ya tiene una invitación pendiente a este portafolio.")

        invitacion = InvitacionPortafolio.objects.create(
            portafolio=portafolio, usuario=usuario, rol=datos["rol"], invitado_por=request.user
        )
        auditoria.invitacion_portafolio_enviada(request, invitacion)
        salida = InvitacionPortafolioSerializer(invitacion, context=self.get_serializer_context())
        return Response(salida.data, status=status.HTTP_201_CREATED)


class InvitacionPortafolioDetalleView(_PortafolioMixin, generics.DestroyAPIView):
    """Cancela una invitación pendiente (`DELETE`): queda como cancelada."""

    serializer_class = InvitacionPortafolioSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return InvitacionPortafolio.objects.none()
        return _con_relaciones(
            InvitacionPortafolio.objects.filter(portafolio=self.get_portafolio())
        )

    @extend_schema(request=None, responses={204: None})
    def delete(self, request: Request, *args, **kwargs) -> Response:
        portafolio = self.exigir(
            PERMISO_GESTIONAR_MIEMBROS,
            "No tienes permiso para gestionar los miembros del portafolio.",
        )
        invitacion = self.get_object()
        if not puede_gestionar_rol_de_portafolio(request.user, portafolio.pk, invitacion.rol):
            raise PermissionDenied("No puedes gestionar invitaciones de un rol superior al tuyo.")
        if not invitacion.pendiente:
            raise Conflicto("La invitación ya fue respondida o cancelada.")
        with transaction.atomic():
            invitacion.estado = InvitacionPortafolio.Estado.CANCELADA
            invitacion.respondido_en = timezone.now()
            invitacion.save(update_fields=["estado", "respondido_en"])
            auditoria.invitacion_portafolio_respondida(
                request, invitacion, "portafolio.invitacion_cancelar"
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MisInvitacionesPortafolioView(generics.ListAPIView):
    """Invitaciones a portafolios pendientes de quien consulta."""

    serializer_class = InvitacionPortafolioSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = None
    filter_backends = ()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return InvitacionPortafolio.objects.none()
        return _con_relaciones(
            InvitacionPortafolio.objects.filter(
                usuario=self.request.user, estado=InvitacionPortafolio.Estado.PENDIENTE
            )
        )


class _RespuestaView(APIView):
    """Base de aceptar y rechazar: solo la persona invitada y solo si sigue pendiente."""

    permission_classes = (permissions.IsAuthenticated,)

    def invitacion_propia(self, pk: int) -> InvitacionPortafolio:
        invitacion = (
            _con_relaciones(InvitacionPortafolio.objects.select_for_update(of=("self",)))
            .filter(pk=pk, usuario=self.request.user)
            .first()
        )
        if invitacion is None:
            raise NotFound("Invitación no encontrada.")
        if not invitacion.pendiente:
            raise Conflicto("La invitación ya fue respondida o cancelada.")
        return invitacion

    def cerrar(self, invitacion: InvitacionPortafolio, estado: str) -> None:
        invitacion.estado = estado
        invitacion.respondido_en = timezone.now()
        invitacion.save(update_fields=["estado", "respondido_en"])


class AceptarInvitacionPortafolioView(_RespuestaView):
    @extend_schema(request=None, responses={200: InvitacionPortafolioSerializer})
    @transaction.atomic
    def post(self, request: Request, pk: int) -> Response:
        """Acepta: se crea (o reactiva) la membresía con el rol de la invitación."""
        invitacion = self.invitacion_propia(pk)
        membresia = MembresiaPortafolio.objects.filter(
            usuario=request.user, portafolio=invitacion.portafolio
        ).first()
        if membresia is not None and membresia.activa:
            raise Conflicto("Ya eres miembro de este portafolio. Puedes rechazar la invitación.")
        reactivada = membresia is not None
        antes = auditoria.foto_miembro_portafolio(membresia) if reactivada else None
        if membresia is None:
            membresia = MembresiaPortafolio(
                usuario=request.user,
                portafolio=invitacion.portafolio,
                creado_por=invitacion.invitado_por,
            )
        membresia.rol = invitacion.rol
        membresia.activa = True
        membresia.save()
        self.cerrar(invitacion, InvitacionPortafolio.Estado.ACEPTADA)
        auditoria.invitacion_portafolio_respondida(
            request, invitacion, "portafolio.invitacion_aceptar"
        )
        if reactivada:
            auditoria.miembro_portafolio_reactivado_al_aceptar(request, membresia, antes)
        else:
            auditoria.miembro_portafolio_agregado(request, membresia)
        return Response(InvitacionPortafolioSerializer(invitacion).data)


class RechazarInvitacionPortafolioView(_RespuestaView):
    @extend_schema(request=None, responses={200: InvitacionPortafolioSerializer})
    @transaction.atomic
    def post(self, request: Request, pk: int) -> Response:
        """Rechaza: no se crea ninguna membresía."""
        invitacion = self.invitacion_propia(pk)
        self.cerrar(invitacion, InvitacionPortafolio.Estado.RECHAZADA)
        auditoria.invitacion_portafolio_respondida(
            request, invitacion, "portafolio.invitacion_rechazar"
        )
        return Response(InvitacionPortafolioSerializer(invitacion).data)
