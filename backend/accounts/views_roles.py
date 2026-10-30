from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import ProtectedError
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import auditoria
from .catalogo import permisos_registrados
from .errores import Conflicto
from .permissions import requiere_permiso
from .roles import ROLES_CON_PERFIL, ROLES_GLOBALES
from .serializers_roles import PermisoCatalogoSerializer, RoleSerializer


class RolViewSet(viewsets.ModelViewSet):
    """Gestión de roles y de sus permisos (solo con `accounts.manage_roles`, es decir, el Admin).

    - `Admin` y `Moderador` son del sistema y globales: no se editan ni se borran.
    - `Planificador`, `Colaborador`, `Auditor` y los de portafolio (`Gestor del portafolio`,
      `Coordinador`) son del sistema: se editan sus permisos,
      pero no se renombran ni se borran.
    - Los roles que se creen son por entidad (por defecto) o por portafolio (`ambito`) y solo
      reciben permisos de su ámbito (`/api/permissions/`); un permiso global nunca se asigna (D-16).
    """

    serializer_class = RoleSerializer
    permission_classes = (requiere_permiso("accounts.manage_roles"),)
    parser_classes = (JSONParser,)
    pagination_class = None
    http_method_names = ("get", "post", "patch", "delete", "head", "options")

    def get_queryset(self):
        return (
            Group.objects.select_related("perfil")
            .prefetch_related("permissions__content_type")
            .order_by("name")
        )

    def update(self, request: Request, *args, **kwargs) -> Response:
        nombre = self.get_object().name
        if nombre in ROLES_GLOBALES:
            raise PermissionDenied(f"El rol {nombre} es del sistema y no se modifica.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        nombre = self.get_object().name
        if nombre in ROLES_GLOBALES or nombre in ROLES_CON_PERFIL:
            raise PermissionDenied("Los roles del sistema no se pueden eliminar.")
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError as exc:  # el rol está en uso por membresías (módulo `entities`)
            raise Conflicto("El rol está en uso por miembros de alguna entidad.") from exc

    @transaction.atomic
    def perform_destroy(self, instance: Group) -> None:
        # Se registra antes de borrar (después el rol pierde su id). Si el borrado falla (rol en
        # uso), la transacción se revierte y tampoco queda el evento.
        auditoria.rol_eliminado(self.request, instance)
        instance.delete()


class PermisoCatalogoView(APIView):
    """Permisos que se pueden asignar a roles, con su ámbito (`global` o `entidad`)."""

    permission_classes = (requiere_permiso("accounts.manage_roles"),)

    @extend_schema(responses=PermisoCatalogoSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(PermisoCatalogoSerializer(permisos_registrados(), many=True).data)
