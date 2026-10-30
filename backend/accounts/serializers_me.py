from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .catalogo import AMBITO_GLOBAL, permisos_registrados
from .serializers import UserSerializer


class MeSerializer(UserSerializer):
    """Perfil propio, con lo que la web necesita para decidir qué menús mostrar.

    Es solo informativo: el backend sigue aplicando todos los permisos en cada endpoint.
    Los permisos de cada entidad (y el rol en ella) llegan en `/api/entities/`.
    """

    is_admin = serializers.BooleanField(read_only=True)
    is_moderator = serializers.BooleanField(read_only=True)
    is_superuser = serializers.BooleanField(read_only=True)
    global_permissions = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = (
            *UserSerializer.Meta.fields,
            "is_admin",
            "is_moderator",
            "is_superuser",
            "global_permissions",
        )
        read_only_fields = (
            *UserSerializer.Meta.read_only_fields,
            "is_admin",
            "is_moderator",
            "is_superuser",
        )

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_global_permissions(self, obj) -> list[str]:
        """Permisos globales del catálogo que tiene el usuario (todos, si es superusuario)."""
        return sorted(
            d.codename
            for d in permisos_registrados()
            if d.ambito == AMBITO_GLOBAL and obj.has_perm(d.codename)
        )
