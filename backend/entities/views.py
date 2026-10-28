from django.db import transaction
from django.db.models import Count
from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions, status, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.errores import Conflicto
from accounts.models import User
from accounts.permissions import requiere_permiso

from .models import Entidad, Membresia, TipoEntidad
from .permisos import (
    PuedeVerTipos,
    entidades_visibles,
    puede_editar_entidad,
    puede_gestionar_miembros,
    puede_ver_miembros,
)
from .serializers import (
    EntidadSerializer,
    MiembroCrearSerializer,
    MiembroEditarSerializer,
    MiembroSerializer,
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


class EntidadViewSet(viewsets.ModelViewSet):
    """Entidades. Cada persona ve solo las suyas; el Admin y el superusuario ven todas.

    - Crear: solo el Admin (`entities.manage_entities`).
    - Editar nombre y descripción: Admin o quien tenga `entities.edit_entity` en esa entidad.
    - Archivar o reactivar (`estado`): solo el Admin. No hay DELETE.
    """

    serializer_class = EntidadSerializer
    parser_classes = (JSONParser,)
    http_method_names = ("get", "post", "patch", "head", "options")
    filterset_fields = ("tipo", "estado")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return Entidad.objects.none()
        return entidades_visibles(self.request.user).select_related("tipo").distinct()

    def get_permissions(self):
        if self.action == "create":
            return [requiere_permiso("entities.manage_entities")()]
        return [permissions.IsAuthenticated()]

    def get_serializer_context(self) -> dict:
        contexto = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated:
            contexto["roles_por_entidad"] = dict(
                Membresia.objects.filter(usuario=user, activa=True).values_list(
                    "entidad_id", "rol__name"
                )
            )
        return contexto

    def update(self, request: Request, *args, **kwargs) -> Response:
        if not puede_editar_entidad(request.user, self.get_object()):
            raise PermissionDenied("No tienes permiso para editar esta entidad.")
        return super().update(request, *args, **kwargs)


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
    - POST: crea la cuenta de una persona nueva o suma una existente, con un rol de nivel menor
      al propio (D-18). Si la persona ya fue miembro y está inactiva, se reactiva.
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

    @extend_schema(
        parameters=[OpenApiParameter("activa", str, description="true (defecto), false o todas")]
    )
    def list(self, request: Request, *args, **kwargs) -> Response:
        if not puede_ver_miembros(request.user, self.get_entidad()):
            raise PermissionDenied("No tienes permiso para ver los miembros de esta entidad.")
        return super().list(request, *args, **kwargs)

    @extend_schema(request=MiembroCrearSerializer, responses={201: MiembroSerializer})
    @transaction.atomic
    def create(self, request: Request, *args, **kwargs) -> Response:
        entidad = self.exigir_gestion()
        entrada = MiembroCrearSerializer(data=request.data, context=self.get_serializer_context())
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data

        if "new_user" in datos:
            usuario = User.objects.create_user(**datos["new_user"])
        else:
            # Un superusuario no se puede sumar a una entidad por esta vía.
            usuario = User.objects.filter(
                username=datos["username"], is_active=True, is_superuser=False
            ).first()
            if usuario is None:
                raise NotFound("Usuario no encontrado.")

        membresia = Membresia.objects.filter(usuario=usuario, entidad=entidad).first()
        if membresia is not None and membresia.activa:
            raise Conflicto("La persona ya es miembro de esta entidad.")
        if membresia is None:
            membresia = Membresia(usuario=usuario, entidad=entidad, creado_por=request.user)
        membresia.rol = datos["rol"]
        membresia.activa = True
        membresia.save()
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
        entrada.save()
        membresia.refresh_from_db()
        salida = MiembroSerializer(membresia, context=self.get_serializer_context())
        return Response(salida.data)

    @extend_schema(request=MiembroEditarSerializer, responses={200: MiembroSerializer})
    def patch(self, request: Request, *args, **kwargs) -> Response:
        return self._modificar(request.data)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request: Request, *args, **kwargs) -> Response:
        self._modificar({"activa": False})
        return Response(status=status.HTTP_204_NO_CONTENT)
