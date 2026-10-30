"""Invitaciones a entidades (D-27): quien gestiona miembros invita; la persona acepta o rechaza."""

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.errores import Conflicto
from accounts.models import User

from . import auditoria
from .models import Invitacion, Membresia
from .permisos import puede_gestionar_rol, puede_ver_miembros
from .serializers import InvitacionCrearSerializer, InvitacionSerializer
from .views import _EntidadMixin


def _con_relaciones(consulta):
    return consulta.select_related("entidad__tipo", "usuario", "rol", "invitado_por")


class InvitacionesEntidadView(_EntidadMixin, generics.ListCreateAPIView):
    """Invitaciones de una entidad.

    - GET: quien puede ver miembros. Por defecto las pendientes (`?estado=` otro estado o `todas`).
    - POST: invita a una cuenta que ya existe, con un rol de nivel menor al propio (D-18).
      La persona la acepta o rechaza desde `/api/invitations/`.
    """

    serializer_class = InvitacionSerializer
    parser_classes = (JSONParser,)
    pagination_class = None
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return Invitacion.objects.none()
        invitaciones = _con_relaciones(Invitacion.objects.filter(entidad=self.get_entidad()))
        estado = self.request.query_params.get("estado", Invitacion.Estado.PENDIENTE).lower()
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

    @extend_schema(request=InvitacionCrearSerializer, responses={201: InvitacionSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        return self.create(request, *args, **kwargs)

    def list(self, request: Request, *args, **kwargs) -> Response:
        if not puede_ver_miembros(request.user, self.get_entidad()):
            raise PermissionDenied("No tienes permiso para ver los miembros de esta entidad.")
        return super().list(request, *args, **kwargs)

    @transaction.atomic
    def create(self, request: Request, *args, **kwargs) -> Response:
        entidad = self.exigir_gestion()
        entrada = InvitacionCrearSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data

        # Un superusuario no se puede invitar a una entidad.
        usuario = User.objects.filter(
            username=datos["username"], is_active=True, is_superuser=False
        ).first()
        if usuario is None:
            raise NotFound("Usuario no encontrado.")
        if Membresia.objects.filter(usuario=usuario, entidad=entidad, activa=True).exists():
            raise Conflicto("La persona ya es miembro de esta entidad.")
        if Invitacion.objects.filter(
            usuario=usuario, entidad=entidad, estado=Invitacion.Estado.PENDIENTE
        ).exists():
            raise Conflicto("La persona ya tiene una invitación pendiente a esta entidad.")

        invitacion = Invitacion.objects.create(
            entidad=entidad, usuario=usuario, rol=datos["rol"], invitado_por=request.user
        )
        auditoria.invitacion_enviada(request, invitacion)
        salida = InvitacionSerializer(invitacion, context=self.get_serializer_context())
        return Response(salida.data, status=status.HTTP_201_CREATED)


class InvitacionEntidadDetalleView(_EntidadMixin, generics.DestroyAPIView):
    """Cancela una invitación pendiente (`DELETE`): la invitación se conserva como cancelada."""

    serializer_class = InvitacionSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return Invitacion.objects.none()
        return _con_relaciones(Invitacion.objects.filter(entidad=self.get_entidad()))

    @extend_schema(request=None, responses={204: None})
    def delete(self, request: Request, *args, **kwargs) -> Response:
        entidad = self.exigir_gestion()
        invitacion = self.get_object()
        if not puede_gestionar_rol(request.user, entidad, invitacion.rol):
            raise PermissionDenied(
                "No puedes gestionar invitaciones de un rol igual o superior al tuyo."
            )
        if not invitacion.pendiente:
            raise Conflicto("La invitación ya fue respondida o cancelada.")
        with transaction.atomic():
            invitacion.estado = Invitacion.Estado.CANCELADA
            invitacion.respondido_en = timezone.now()
            invitacion.save(update_fields=["estado", "respondido_en"])
            auditoria.invitacion_respondida(request, invitacion, "invitacion.cancelar")
        return Response(status=status.HTTP_204_NO_CONTENT)


class MisInvitacionesView(generics.ListAPIView):
    """Invitaciones pendientes de quien consulta (para aceptarlas o rechazarlas)."""

    serializer_class = InvitacionSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = None
    filter_backends = ()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return Invitacion.objects.none()
        return _con_relaciones(
            Invitacion.objects.filter(usuario=self.request.user, estado=Invitacion.Estado.PENDIENTE)
        )


class _RespuestaView(APIView):
    """Base de aceptar y rechazar: solo la persona invitada y solo si sigue pendiente."""

    permission_classes = (permissions.IsAuthenticated,)

    def invitacion_propia(self, pk: int) -> Invitacion:
        invitacion = (
            _con_relaciones(Invitacion.objects.select_for_update(of=("self",)))
            .filter(pk=pk, usuario=self.request.user)
            .first()
        )
        if invitacion is None:
            raise NotFound("Invitación no encontrada.")
        if not invitacion.pendiente:
            raise Conflicto("La invitación ya fue respondida o cancelada.")
        return invitacion

    def cerrar(self, invitacion: Invitacion, estado: str) -> None:
        invitacion.estado = estado
        invitacion.respondido_en = timezone.now()
        invitacion.save(update_fields=["estado", "respondido_en"])


class AceptarInvitacionView(_RespuestaView):
    @extend_schema(request=None, responses={200: InvitacionSerializer})
    @transaction.atomic
    def post(self, request: Request, pk: int) -> Response:
        """Acepta: se crea (o reactiva) la membresía con el rol de la invitación."""
        invitacion = self.invitacion_propia(pk)
        if invitacion.entidad.archivada:
            raise Conflicto("La entidad está archivada.")
        membresia = Membresia.objects.filter(
            usuario=request.user, entidad=invitacion.entidad
        ).first()
        if membresia is not None and membresia.activa:
            raise Conflicto("Ya eres miembro de esta entidad. Puedes rechazar la invitación.")
        reactivada = membresia is not None
        antes = auditoria.foto_miembro(membresia) if reactivada else None
        if membresia is None:
            membresia = Membresia(
                usuario=request.user, entidad=invitacion.entidad, creado_por=invitacion.invitado_por
            )
        membresia.rol = invitacion.rol
        membresia.activa = True
        membresia.save()
        self.cerrar(invitacion, Invitacion.Estado.ACEPTADA)
        auditoria.invitacion_respondida(request, invitacion, "invitacion.aceptar")
        if reactivada:
            auditoria.miembro_reactivado_al_agregar(request, membresia, antes)
        else:
            auditoria.miembro_agregado(request, membresia, cuenta_nueva=False)
        return Response(InvitacionSerializer(invitacion).data)


class RechazarInvitacionView(_RespuestaView):
    @extend_schema(request=None, responses={200: InvitacionSerializer})
    @transaction.atomic
    def post(self, request: Request, pk: int) -> Response:
        """Rechaza: no se crea ninguna membresía."""
        invitacion = self.invitacion_propia(pk)
        self.cerrar(invitacion, Invitacion.Estado.RECHAZADA)
        auditoria.invitacion_respondida(request, invitacion, "invitacion.rechazar")
        return Response(InvitacionSerializer(invitacion).data)
