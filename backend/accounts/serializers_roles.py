from django.contrib.auth.models import Group, Permission
from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .catalogo import AMBITO_ENTIDAD, obtener_permiso
from .models import PerfilRol
from .roles import ROL_ADMIN, ROLES_POR_ENTIDAD


class PermisoCatalogoSerializer(serializers.Serializer):
    """Un permiso del catálogo (solo lectura)."""

    codename = serializers.CharField()
    nombre = serializers.CharField()
    ambito = serializers.CharField()


@extend_schema_field(serializers.ListField(child=serializers.CharField()))
class PermisosField(serializers.Field):
    """Lista de permisos de un rol como textos 'app.codename'."""

    def to_representation(self, value) -> list[str]:
        return sorted(f"{p.content_type.app_label}.{p.codename}" for p in value.all())

    def to_internal_value(self, data) -> list[str]:
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            raise serializers.ValidationError("Debe ser una lista de textos 'app.codename'.")
        return list(dict.fromkeys(data))  # sin repetidos, conservando el orden


class RoleSerializer(serializers.ModelSerializer):
    """Roles (`Group`) y sus permisos. Solo `Admin` es global; los demás son por entidad (D-16)."""

    permissions = PermisosField(required=False)
    scope = serializers.SerializerMethodField()
    is_system = serializers.SerializerMethodField()
    # Jerarquía (D-18). `null` en `Admin`, que es global y no tiene perfil. Obligatorio al crear.
    nivel = serializers.IntegerField(
        source="perfil.nivel", min_value=1, max_value=99, required=False, allow_null=True
    )
    nivel_minimo_para_asignar = serializers.IntegerField(
        source="perfil.nivel_minimo_para_asignar",
        min_value=2,
        max_value=100,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Group
        fields = (
            "id",
            "name",
            "scope",
            "is_system",
            "nivel",
            "nivel_minimo_para_asignar",
            "permissions",
        )

    def get_scope(self, obj: Group) -> str:
        return "global" if obj.name == ROL_ADMIN else "entidad"

    def get_is_system(self, obj: Group) -> bool:
        return obj.name == ROL_ADMIN or obj.name in ROLES_POR_ENTIDAD

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Este campo no puede estar vacío.")
        repetidos = Group.objects.filter(name__iexact=value)
        if self.instance is not None:
            repetidos = repetidos.exclude(pk=self.instance.pk)
        if repetidos.exists():
            raise serializers.ValidationError("Ya existe un rol con ese nombre.")
        if (
            self.instance is not None
            and self.instance.name in ROLES_POR_ENTIDAD
            and value != self.instance.name
        ):
            raise serializers.ValidationError("Un rol del sistema no se puede renombrar.")
        return value

    def validate_nivel(self, value: int | None) -> int:
        if value is None:
            raise serializers.ValidationError("Este campo no puede ser nulo.")
        return value

    def validate_nivel_minimo_para_asignar(self, value: int | None) -> int:
        if value is None:
            raise serializers.ValidationError("Este campo no puede ser nulo.")
        return value

    def validate(self, attrs: dict) -> dict:
        datos = attrs.get("perfil", {})
        actual = getattr(self.instance, "perfil", None) if self.instance is not None else None
        nivel = datos.get("nivel", actual.nivel if actual else None)
        minimo = datos.get(
            "nivel_minimo_para_asignar", actual.nivel_minimo_para_asignar if actual else None
        )
        if nivel is None:
            if self.instance is None or datos:
                raise serializers.ValidationError({"nivel": "Este campo es requerido."})
            return attrs  # edición que no toca la jerarquía (p. ej. solo el nombre)
        if "nivel_minimo_para_asignar" not in datos and (minimo is None or minimo <= nivel):
            minimo = nivel + 1  # por defecto, o se ajusta al cambiar el nivel
        if minimo <= nivel:
            raise serializers.ValidationError(
                {"nivel_minimo_para_asignar": "Debe ser mayor que el nivel del rol."}
            )
        if minimo > 100:
            raise serializers.ValidationError(
                {"nivel_minimo_para_asignar": "No puede pasar de 100."}
            )
        if datos or actual is None:
            attrs["perfil"] = {"nivel": nivel, "nivel_minimo_para_asignar": minimo}
        return attrs

    def validate_permissions(self, value: list[str]) -> list[Permission]:
        errores: list[str] = []
        permisos: list[Permission] = []
        for codename in value:
            definicion = obtener_permiso(codename)
            if definicion is None:
                errores.append(f"{codename}: no está en el catálogo de permisos.")
                continue
            if definicion.ambito != AMBITO_ENTIDAD:
                errores.append(
                    f"{codename}: es un permiso global y no se asigna a roles por entidad."
                )
                continue
            app, _, codigo = codename.partition(".")
            permiso = Permission.objects.filter(
                content_type__app_label=app, codename=codigo
            ).first()
            if permiso is None:
                errores.append(f"{codename}: no existe en la base de datos (falta migrar).")
            else:
                permisos.append(permiso)
        if errores:
            raise serializers.ValidationError(errores)
        return permisos

    def _recargar(self, grupo: Group) -> Group:
        return (
            Group.objects.select_related("perfil")
            .prefetch_related("permissions__content_type")
            .get(pk=grupo.pk)
        )

    @transaction.atomic
    def create(self, validated_data: dict) -> Group:
        permisos = validated_data.pop("permissions", [])
        perfil = validated_data.pop("perfil")
        grupo = Group.objects.create(**validated_data)
        grupo.permissions.set(permisos)
        PerfilRol.objects.create(grupo=grupo, **perfil)
        return self._recargar(grupo)

    @transaction.atomic
    def update(self, instance: Group, validated_data: dict) -> Group:
        permisos = validated_data.pop("permissions", None)
        perfil = validated_data.pop("perfil", None)
        grupo = super().update(instance, validated_data)
        if permisos is not None:
            grupo.permissions.set(permisos)
        if perfil is not None:
            PerfilRol.objects.update_or_create(grupo=grupo, defaults=perfil)
        return self._recargar(grupo)
