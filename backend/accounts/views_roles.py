from django.contrib.auth.models import Group
from django.db.models import ProtectedError
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .catalogo import permisos_registrados
from .errores import Conflicto
from .permissions import requiere_permiso
from .roles import ROL_ADMIN, ROLES_POR_ENTIDAD
from .serializers_roles import PermisoCatalogoSerializer, RoleSerializer


class RolViewSet(viewsets.ModelViewSet):
    """Gestión de roles y de sus permisos (solo con `accounts.manage_roles`, es decir, el Admin).

    - `Admin` es del sistema y global: no se edita ni se borra.
    - `Planificador`, `Operario de campo` y `Auditor` son del sistema: se editan sus permisos,
      pero no se renombran ni se borran.
    - Los roles que se creen son siempre por entidad y solo reciben permisos por entidad del
      catálogo (`/api/permissions/`); un permiso global nunca se asigna (D-16).
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
        if self.get_object().name == ROL_ADMIN:
            raise PermissionDenied("El rol Admin es del sistema y no se modifica.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        nombre = self.get_object().name
        if nombre == ROL_ADMIN or nombre in ROLES_POR_ENTIDAD:
            raise PermissionDenied("Los roles del sistema no se pueden eliminar.")
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError as exc:  # el rol está en uso por membresías (módulo `entities`)
            raise Conflicto("El rol está en uso por miembros de alguna entidad.") from exc


class PermisoCatalogoView(APIView):
    """Permisos que se pueden asignar a roles, con su ámbito (`global` o `entidad`)."""

    permission_classes = (requiere_permiso("accounts.manage_roles"),)

    @extend_schema(responses=PermisoCatalogoSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(PermisoCatalogoSerializer(permisos_registrados(), many=True).data)
