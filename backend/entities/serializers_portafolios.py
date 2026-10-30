"""Serializadores de portafolios, sus miembros e invitaciones (D-29)."""

from django.contrib.auth.models import Group
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from accounts.errores import Conflicto

from .models import InvitacionPortafolio, MembresiaPortafolio, Portafolio
from .permisos import es_administrador_global
from .portafolios import (
    PERMISO_CREAR_ENTIDADES,
    PERMISO_EDITAR,
    PERMISO_GESTIONAR_MIEMBROS,
    PERMISO_VER,
    PERMISO_VER_HISTORIAL,
    gestores_activos,
    permisos_en_portafolio,
    puede_gestionar_rol_de_portafolio,
    rol_de_portafolio,
    rol_puede_gestionar_miembros,
)


def _limpiar(value: str) -> str:
    value = value.strip()
    if not value:
        raise serializers.ValidationError("Este campo no puede estar vacío.")
    return value


class PortafolioSerializer(serializers.ModelSerializer):
    """Un portafolio, con lo que la persona que consulta puede hacer en él."""

    total_entidades = serializers.SerializerMethodField()
    mi_rol = serializers.SerializerMethodField()
    puede_editar = serializers.SerializerMethodField()
    puede_eliminar = serializers.SerializerMethodField()
    puede_crear_entidades = serializers.SerializerMethodField()
    puede_ver_miembros = serializers.SerializerMethodField()
    puede_gestionar_miembros = serializers.SerializerMethodField()
    puede_ver_historial = serializers.SerializerMethodField()

    class Meta:
        model = Portafolio
        fields = (
            "id",
            "nombre",
            "descripcion",
            "personal",
            "total_entidades",
            "mi_rol",
            "puede_editar",
            "puede_eliminar",
            "puede_crear_entidades",
            "puede_ver_miembros",
            "puede_gestionar_miembros",
            "puede_ver_historial",
            "creado_por",
            "creado_en",
        )
        read_only_fields = ("id", "personal", "creado_por", "creado_en")

    def _mapa(self) -> dict | None:
        return self.context.get("portafolios")

    def _permisos(self, obj: Portafolio) -> set[str]:
        return permisos_en_portafolio(self.context["request"].user, obj.pk, self._mapa())

    def get_total_entidades(self, obj: Portafolio) -> int:
        anotado = getattr(obj, "total_entidades", None)
        return anotado if anotado is not None else obj.entidades.count()

    def get_mi_rol(self, obj: Portafolio) -> str | None:
        info = (self._mapa() or {}).get(obj.pk)
        return info["rol"] if info else None

    def get_puede_editar(self, obj: Portafolio) -> bool:
        return PERMISO_EDITAR in self._permisos(obj)

    def get_puede_eliminar(self, obj: Portafolio) -> bool:
        return (
            PERMISO_EDITAR in self._permisos(obj)
            and not obj.personal
            and self.get_total_entidades(obj) == 0
        )

    def get_puede_crear_entidades(self, obj: Portafolio) -> bool:
        return PERMISO_CREAR_ENTIDADES in self._permisos(obj)

    def get_puede_ver_miembros(self, obj: Portafolio) -> bool:
        return PERMISO_VER in self._permisos(obj)

    def get_puede_gestionar_miembros(self, obj: Portafolio) -> bool:
        return PERMISO_GESTIONAR_MIEMBROS in self._permisos(obj)

    def get_puede_ver_historial(self, obj: Portafolio) -> bool:
        return PERMISO_VER_HISTORIAL in self._permisos(obj)

    def validate_nombre(self, value: str) -> str:
        value = _limpiar(value)
        if self.instance is not None and self.instance.personal and value != self.instance.nombre:
            raise serializers.ValidationError("El portafolio personal no se renombra.")
        repetidos = Portafolio.objects.filter(nombre__iexact=value, personal=False)
        if self.instance is not None:
            repetidos = repetidos.exclude(pk=self.instance.pk)
        if repetidos.exists():
            raise serializers.ValidationError("Ya existe un portafolio con ese nombre.")
        return value

    def create(self, validated_data: dict) -> Portafolio:
        validated_data["creado_por"] = self.context["request"].user
        return super().create(validated_data)


class PortafolioMiembroSerializer(serializers.ModelSerializer):
    """Una membresía de portafolio, con los datos básicos de la persona y su rol."""

    username = serializers.CharField(source="usuario.username", read_only=True)
    first_name = serializers.CharField(source="usuario.first_name", read_only=True)
    last_name = serializers.CharField(source="usuario.last_name", read_only=True)
    email = serializers.EmailField(source="usuario.email", read_only=True)
    rol_nombre = serializers.CharField(source="rol.name", read_only=True)
    nivel = serializers.SerializerMethodField()

    class Meta:
        model = MembresiaPortafolio
        fields = (
            "id",
            "usuario",
            "username",
            "first_name",
            "last_name",
            "email",
            "rol",
            "rol_nombre",
            "nivel",
            "activa",
            "creado_en",
        )
        read_only_fields = fields

    def get_nivel(self, obj: MembresiaPortafolio) -> int | None:
        perfil = getattr(obj.rol, "perfil", None)
        return perfil.nivel if perfil else None


def _validar_rol_de_portafolio(rol: Group) -> None:
    if not rol_de_portafolio(rol):
        raise serializers.ValidationError({"rol": "Este rol no se puede asignar a un portafolio."})


class PortafolioMiembroEditarSerializer(serializers.Serializer):
    """Cambia el rol de un miembro del portafolio o lo activa o desactiva."""

    rol = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.select_related("perfil"), required=False
    )
    activa = serializers.BooleanField(required=False)

    def validate(self, attrs: dict) -> dict:
        membresia: MembresiaPortafolio = self.instance
        actor = self.context["request"].user
        portafolio: Portafolio = self.context["portafolio"]
        if membresia.usuario_id == actor.pk and not es_administrador_global(actor):
            raise PermissionDenied("No puedes modificar tu propia membresía.")
        if not puede_gestionar_rol_de_portafolio(actor, portafolio.pk, membresia.rol):
            raise PermissionDenied(
                "No puedes gestionar a alguien con un nivel superior al tuyo ni sin permiso."
            )
        nuevo = attrs.get("rol", membresia.rol)
        if nuevo != membresia.rol:
            _validar_rol_de_portafolio(nuevo)
            if not puede_gestionar_rol_de_portafolio(actor, portafolio.pk, nuevo):
                raise PermissionDenied("No puedes asignar ese rol: su nivel es superior al tuyo.")
        sigue_activa = attrs.get("activa", membresia.activa)
        era_gestor = membresia.activa and rol_puede_gestionar_miembros(membresia.rol)
        sigue_gestor = sigue_activa and rol_puede_gestionar_miembros(nuevo)
        if era_gestor and not sigue_gestor and gestores_activos(portafolio) <= 1:
            raise Conflicto("El portafolio debe conservar al menos un Gestor activo.")
        return attrs

    def update(self, instance: MembresiaPortafolio, validated_data: dict) -> MembresiaPortafolio:
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        instance.save()
        return instance


class InvitacionPortafolioCrearSerializer(serializers.Serializer):
    """Invita a una cuenta que ya existe a unirse al portafolio con un rol."""

    username = serializers.CharField(help_text="Nombre de usuario de la cuenta a invitar.")
    rol = serializers.PrimaryKeyRelatedField(queryset=Group.objects.select_related("perfil"))

    def validate_username(self, value: str) -> str:
        return value.strip()

    def validate(self, attrs: dict) -> dict:
        rol = attrs["rol"]
        _validar_rol_de_portafolio(rol)
        portafolio: Portafolio = self.context["portafolio"]
        if not puede_gestionar_rol_de_portafolio(self.context["request"].user, portafolio.pk, rol):
            raise PermissionDenied(
                "No puedes asignar ese rol: su nivel es superior al tuyo o no tienes permiso."
            )
        return attrs


class InvitacionPortafolioSerializer(serializers.ModelSerializer):
    """Una invitación a un portafolio, para quien la envía y para quien la recibe."""

    portafolio_nombre = serializers.CharField(source="portafolio.nombre", read_only=True)
    username = serializers.CharField(source="usuario.username", read_only=True)
    first_name = serializers.CharField(source="usuario.first_name", read_only=True)
    last_name = serializers.CharField(source="usuario.last_name", read_only=True)
    rol_nombre = serializers.CharField(source="rol.name", read_only=True)
    invitado_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = InvitacionPortafolio
        fields = (
            "id",
            "portafolio",
            "portafolio_nombre",
            "usuario",
            "username",
            "first_name",
            "last_name",
            "rol",
            "rol_nombre",
            "invitado_por",
            "invitado_por_nombre",
            "estado",
            "creado_en",
            "respondido_en",
        )
        read_only_fields = fields

    def get_invitado_por_nombre(self, obj: InvitacionPortafolio) -> str:
        quien = obj.invitado_por
        if quien is None:
            return ""
        return f"{quien.first_name} {quien.last_name}".strip() or quien.get_username()
