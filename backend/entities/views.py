from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Count
from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.response import Response

from accounts import auditoria as auditoria_cuentas
from accounts.errores import Conflicto
from accounts.models import User
from accounts.permissions import requiere_permiso

from . import auditoria
from .models import Entidad, Membresia, TipoEntidad
from .permisos import (
    PuedeCrearEntidades,
    PuedeVerTipos,
    candidatos_para_entidad,
    entidades_visibles,
    membresias_activas,
    puede_crear_en_portafolio,
    puede_editar_entidad,
    puede_gestionar_miembros,
    puede_mover_entidad,
    puede_ver_miembros,
    roles_asignables,
)
from .portafolios import membresias_portafolio_activas
from .serializers import (
    CandidatoSerializer,
    EntidadSerializer,
    MiembroCrearSerializer,
    MiembroEditarSerializer,
    MiembroSerializer,
    MoverEntidadSerializer,
    RolAsignableSerializer,
    TipoEntidadSerializer,
)


class TipoEntidadViewSet(viewsets.ModelViewSet):
    """Tipos de entidad (Proyecto, Sucursal…). Ver: Admin o miembros. Escribir: solo el Admin.

    Un tipo que ya tiene entidades no se puede eliminar (se puede desactivar con `activo`).
    """

    serializer_class = TipoEntidadSerializer
    parser_classes = (JSONParser,)
    pagination_class = None
    http_method_names = ("get", "post", "patch", "delete", "head", "options")

    def get_queryset(self):
        return TipoEntidad.objects.annotate(total_entidades=Count("entidades")).order_by("nombre")

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [PuedeVerTipos()]
        return [requiere_permiso("entities.manage_types")()]

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        if self.get_object().entidades.exists():
            raise Conflicto("El tipo tiene entidades: no se puede eliminar (puedes desactivarlo).")
        return super().destroy(request, *args, **kwargs)

    @transaction.atomic
    def perform_create(self, serializer: TipoEntidadSerializer) -> None:
        auditoria.tipo_creado(self.request, serializer.save())

    @transaction.atomic
    def perform_update(self, serializer: TipoEntidadSerializer) -> None:
        antes = auditoria.foto_tipo(serializer.instance)
        auditoria.tipo_editado(self.request, serializer.save(), antes)

    @transaction.atomic
    def perform_destroy(self, instance: TipoEntidad) -> None:
        # Se registra antes de borrar (después el tipo pierde su id) y en la misma transacción.
        auditoria.tipo_eliminado(self.request, instance)
        instance.delete()


class EntidadViewSet(viewsets.ModelViewSet):
    """Entidades. Cada persona ve solo las suyas; el Admin y el superusuario ven todas.

    - Cada entidad pertenece a un portafolio (D-29). Se ven las propias (membresía) y las de los
      portafolios donde se tiene permiso de verlas; el Admin ve todas.
    - Crear: Admin, Moderador (en su portafolio personal si no elige otro) o quien tenga
      `create_portfolio_entities` en el portafolio elegido.
    - Editar nombre y descripción: quien tenga `edit_portfolio_entities` en el portafolio o
      `entities.edit_entity` en ella.
    - Archivar o reactivar (`estado`) y mover (`/move/`): según permisos del portafolio. No hay DELETE.
    """

    serializer_class = EntidadSerializer
    parser_classes = (JSONParser,)
    http_method_names = ("get", "post", "patch", "head", "options")
    filterset_fields = ("tipo", "estado", "portafolio")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return Entidad.objects.none()
        return entidades_visibles(self.request.user).select_related("tipo", "portafolio").distinct()

    def get_permissions(self):
        if self.action == "create":
            return [PuedeCrearEntidades()]
        return [permissions.IsAuthenticated()]

    def get_serializer_context(self) -> dict:
        contexto = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated:
            contexto["membresias"] = membresias_activas(user)
            contexto["portafolios"] = membresias_portafolio_activas(user)
        return contexto

    def update(self, request: Request, *args, **kwargs) -> Response:
        if not puede_editar_entidad(request.user, self.get_object()):
            raise PermissionDenied("No tienes permiso para editar esta entidad.")
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def perform_create(self, serializer: EntidadSerializer) -> None:
        auditoria.entidad_creada(self.request, serializer.save())

    @extend_schema(request=MoverEntidadSerializer, responses={200: EntidadSerializer})
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def move(self, request: Request, pk: str | None = None) -> Response:
        """Cambia la entidad de portafolio: hace falta poder moverla en el origen y crear
        entidades en el destino (el Admin puede con cualquiera)."""
        entidad = self.get_object()
        if not puede_mover_entidad(request.user, entidad):
            raise PermissionDenied("No tienes permiso para mover esta entidad.")
        entrada = MoverEntidadSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        destino = entrada.validated_data["portafolio"]
        if destino.pk == entidad.portafolio_id:
            raise Conflicto("La entidad ya está en ese portafolio.")
        if not puede_crear_en_portafolio(request.user, destino.pk):
            raise PermissionDenied("No puedes crear entidades en el portafolio de destino.")
        origen = entidad.portafolio
        entidad.portafolio = destino
        entidad.save(update_fields=["portafolio"])
        auditoria.entidad_movida(request, entidad, origen)
        salida = self.get_serializer(entidad)
        return Response(salida.data)

    @transaction.atomic
    def perform_update(self, serializer: EntidadSerializer) -> None:
        antes = auditoria.foto_entidad(serializer.instance)
        auditoria.entidad_editada(self.request, serializer.save(), antes)


class _EntidadMixin:
    """Resuelve la entidad de la URL: 404 si no existe o la persona no la ve."""

    def get_entidad(self) -> Entidad:
        if not hasattr(self, "_entidad"):
            entidad = (
                entidades_visibles(self.request.user).filter(pk=self.kwargs["entidad_id"]).first()
            )
            if entidad is None:
                raise Http404
            self._entidad = entidad
        return self._entidad

    def get_serializer_context(self) -> dict:
        contexto = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            contexto["entidad"] = self.get_entidad()
        return contexto

    def exigir_gestion(self) -> Entidad:
        entidad = self.get_entidad()
        if not puede_gestionar_miembros(self.request.user, entidad):
            raise PermissionDenied("No tienes permiso para gestionar miembros de esta entidad.")
        if entidad.archivada:
            raise Conflicto("La entidad está archivada.")
        return entidad


class MiembrosView(_EntidadMixin, generics.ListCreateAPIView):
    """Miembros de una entidad.

    - GET: Admin o quien tenga `entities.view_members`. Por defecto solo los activos
      (`?activa=false` los inactivos, `?activa=todas` todos).
    - POST: crea la cuenta de una persona nueva y la suma con un rol de nivel menor al propio
      (D-18). Para una cuenta que ya existe se usa una invitación (`/invitations/`, D-27).
    """

    serializer_class = MiembroSerializer
    parser_classes = (JSONParser,)
    pagination_class = None
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return Membresia.objects.none()
        miembros = Membresia.objects.select_related("usuario", "rol__perfil").filter(
            entidad=self.get_entidad()
        )
        estado = self.request.query_params.get("activa", "true").lower()
        if estado != "todas":
            miembros = miembros.filter(activa=estado != "false")
        return miembros

    # drf-spectacular lee las anotaciones en los métodos HTTP (`get`/`post`) de las vistas
    # genéricas; en `list`/`create` las ignora y el esquema describiría mal la petición.
    @extend_schema(
        parameters=[OpenApiParameter("activa", str, description="true (defecto), false o todas")]
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return self.list(request, *args, **kwargs)

    @extend_schema(request=MiembroCrearSerializer, responses={201: MiembroSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        return self.create(request, *args, **kwargs)

    def list(self, request: Request, *args, **kwargs) -> Response:
        if not puede_ver_miembros(request.user, self.get_entidad()):
            raise PermissionDenied("No tienes permiso para ver los miembros de esta entidad.")
        return super().list(request, *args, **kwargs)

    @transaction.atomic
    def create(self, request: Request, *args, **kwargs) -> Response:
        entidad = self.exigir_gestion()
        entrada = MiembroCrearSerializer(data=request.data, context=self.get_serializer_context())
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data

        usuario = User.objects.create_user(**datos["new_user"])
        auditoria_cuentas.usuario_creado(request, usuario, desde_entidad=entidad)
        membresia = Membresia.objects.create(
            usuario=usuario, entidad=entidad, rol=datos["rol"], creado_por=request.user
        )
        auditoria.miembro_agregado(request, membresia, cuenta_nueva=True)
        salida = MiembroSerializer(membresia, context=self.get_serializer_context())
        return Response(salida.data, status=status.HTTP_201_CREATED)


class MiembroDetalleView(_EntidadMixin, generics.RetrieveUpdateDestroyAPIView):
    """Un miembro: ver, cambiar su rol o activarlo y desactivarlo (DELETE desactiva).

    Hace falta un nivel mayor al del rol actual del miembro y, si se cambia el rol, al del nuevo.
    Nadie modifica su propia membresía (salvo el Admin).
    """

    serializer_class = MiembroSerializer
    parser_classes = (JSONParser,)
    permission_classes = (permissions.IsAuthenticated,)
    http_method_names = ("get", "patch", "delete", "head", "options")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return Membresia.objects.none()
        return Membresia.objects.select_related("usuario", "rol__perfil").filter(
            entidad=self.get_entidad()
        )

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        if not puede_ver_miembros(request.user, self.get_entidad()):
            raise PermissionDenied("No tienes permiso para ver los miembros de esta entidad.")
        return super().retrieve(request, *args, **kwargs)

    def _modificar(self, datos: dict) -> Response:
        self.exigir_gestion()
        membresia = self.get_object()
        entrada = MiembroEditarSerializer(
            membresia, data=datos, partial=True, context=self.get_serializer_context()
        )
        entrada.is_valid(raise_exception=True)
        with transaction.atomic():
            antes = auditoria.foto_miembro(membresia)
            entrada.save()
            membresia.refresh_from_db()
            auditoria.miembro_editado(self.request, membresia, antes)
        salida = MiembroSerializer(membresia, context=self.get_serializer_context())
        return Response(salida.data)

    @extend_schema(request=MiembroEditarSerializer, responses={200: MiembroSerializer})
    def patch(self, request: Request, *args, **kwargs) -> Response:
        return self._modificar(request.data)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request: Request, *args, **kwargs) -> Response:
        self._modificar({"activa": False})
        return Response(status=status.HTTP_204_NO_CONTENT)


class RolesAsignablesView(_EntidadMixin, generics.ListAPIView):
    """Roles que quien consulta puede asignar en la entidad (D-18), del de más nivel al de menos.

    Sirve para llenar el selector de rol al agregar o cambiar miembros: quien no es Admin no
    puede listar todos los roles (`/api/roles/`).
    """

    serializer_class = RolAsignableSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = None
    filter_backends = ()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return Group.objects.none()
        entidad = self.get_entidad()
        if not puede_gestionar_miembros(self.request.user, entidad):
            raise PermissionDenied("No tienes permiso para gestionar miembros de esta entidad.")
        return roles_asignables(self.request.user, entidad)


LIMITE_CANDIDATOS = 10


class CandidatosView(_EntidadMixin, generics.ListAPIView):
    """Busca cuentas para sumar a la entidad (`?q=` por usuario, nombre o apellido).

    Devuelve como máximo 10, ordenadas por usuario. El Admin busca entre todas las cuentas
    (menos superusuarios); los demás, solo entre quienes comparten con ellos otra entidad.
    """

    serializer_class = CandidatoSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = None
    filter_backends = ()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return User.objects.none()
        entidad = self.get_entidad()
        if not puede_gestionar_miembros(self.request.user, entidad):
            raise PermissionDenied("No tienes permiso para gestionar miembros de esta entidad.")
        texto = self.request.query_params.get("q", "")[:100]
        return candidatos_para_entidad(self.request.user, entidad, texto)[:LIMITE_CANDIDATOS]

    @extend_schema(
        parameters=[OpenApiParameter("q", str, description="Texto a buscar (usuario o nombre)")]
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return self.list(request, *args, **kwargs)
