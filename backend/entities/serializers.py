from django.contrib.auth.models import Group
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from accounts.serializers import RegisterSerializer

from .models import Entidad, Invitacion, Membresia, Portafolio, TipoEntidad
from .permisos import (
    capacidades,
    es_administrador_global,
    puede_archivar_entidad,
    puede_crear_en_portafolio,
    puede_crear_entidades,
    puede_gestionar_rol,
)
from .portafolios import portafolio_personal


def _limpiar_nombre(value: str) -> str:
    value = value.strip()
    if not value:
        raise serializers.ValidationError("Este campo no puede estar vacío.")
    return value


class TipoEntidadSerializer(serializers.ModelSerializer):
    total_entidades = serializers.SerializerMethodField()

    class Meta:
        model = TipoEntidad
        fields = (
            "id",
            "nombre",
            "nombre_plural",
            "admite_tareas",
            "activo",
            "total_entidades",
        )

    def get_total_entidades(self, obj: TipoEntidad) -> int:
        anotado = getattr(obj, "total_entidades", None)
        return anotado if anotado is not None else obj.entidades.count()

    def validate_nombre(self, value: str) -> str:
        value = _limpiar_nombre(value)
        repetidos = TipoEntidad.objects.filter(nombre__iexact=value)
        if self.instance is not None:
            repetidos = repetidos.exclude(pk=self.instance.pk)
        if repetidos.exists():
            raise serializers.ValidationError("Ya existe un tipo con ese nombre.")
        return value

    def validate_nombre_plural(self, value: str) -> str:
        return _limpiar_nombre(value)


class EntidadSerializer(serializers.ModelSerializer):
    """Una entidad. El tipo se elige al crear y no cambia después (D-19)."""

    tipo = serializers.PrimaryKeyRelatedField(queryset=TipoEntidad.objects.filter(activo=True))
    tipo_nombre = serializers.CharField(source="tipo.nombre", read_only=True)
    estado = serializers.ChoiceField(choices=Entidad.Estado.choices, required=False)
    # Al crear se elige el portafolio; si no, va al portafolio personal. Después se cambia moviéndola.
    portafolio = serializers.PrimaryKeyRelatedField(
        queryset=Portafolio.objects.all(), required=False
    )
    portafolio_nombre = serializers.CharField(source="portafolio.nombre", read_only=True)
    mi_rol = serializers.SerializerMethodField()
    puede_editar = serializers.SerializerMethodField()
    puede_ver_miembros = serializers.SerializerMethodField()
    puede_gestionar_miembros = serializers.SerializerMethodField()
    puede_ver_historial = serializers.SerializerMethodField()
    puede_archivar = serializers.SerializerMethodField()
    puede_mover = serializers.SerializerMethodField()

    class Meta:
        model = Entidad
        fields = (
            "id",
            "tipo",
            "tipo_nombre",
            "portafolio",
            "portafolio_nombre",
            "nombre",
            "descripcion",
            "estado",
            "mi_rol",
            "puede_editar",
            "puede_ver_miembros",
            "puede_gestionar_miembros",
            "puede_ver_historial",
            "puede_archivar",
            "puede_mover",
            "creado_por",
            "creado_en",
        )
        read_only_fields = ("id", "creado_por", "creado_en")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.instance is not None and not isinstance(self.instance, list | tuple):
            self.fields["tipo"].read_only = True
            self.fields["portafolio"].read_only = True
            self.fields["portafolio"].read_only = True

    def _membresia(self, obj: Entidad) -> dict | None:
        return self.context.get("membresias", {}).get(obj.pk)

    def _capacidades(self, obj: Entidad) -> dict[str, bool]:
        return capacidades(
            self.context["request"].user,
            self._membresia(obj),
            obj,
            self.context.get("portafolios"),
        )

    def get_mi_rol(self, obj: Entidad) -> str | None:
        """Nombre del rol del usuario en la entidad (null si no es miembro, p. ej. el Admin)."""
        info = self._membresia(obj)
        return info["rol"] if info else None

    def get_puede_editar(self, obj: Entidad) -> bool:
        return self._capacidades(obj)["editar"]

    def get_puede_ver_miembros(self, obj: Entidad) -> bool:
        return self._capacidades(obj)["ver_miembros"]

    def get_puede_gestionar_miembros(self, obj: Entidad) -> bool:
        return self._capacidades(obj)["gestionar_miembros"]

    def get_puede_ver_historial(self, obj: Entidad) -> bool:
        return self._capacidades(obj)["ver_historial"]

    def get_puede_archivar(self, obj: Entidad) -> bool:
        return self._capacidades(obj)["archivar"]

    def get_puede_mover(self, obj: Entidad) -> bool:
        return self._capacidades(obj)["mover"]

    def validate_nombre(self, value: str) -> str:
        return _limpiar_nombre(value)

    def validate(self, attrs: dict) -> dict:
        instancia = self.instance if isinstance(self.instance, Entidad) else None
        tipo = attrs.get("tipo") or (instancia.tipo if instancia else None)
        nombre = attrs.get("nombre", instancia.nombre if instancia else None)
        if tipo is not None and nombre:
            repetidas = Entidad.objects.filter(tipo=tipo, nombre__iexact=nombre)
            if instancia is not None:
                repetidas = repetidas.exclude(pk=instancia.pk)
            if repetidas.exists():
                raise serializers.ValidationError(
                    {"nombre": "Ya existe una entidad con ese nombre en este tipo."}
                )
        user = self.context["request"].user
        if instancia is None:
            attrs.pop("estado", None)  # toda entidad nueva nace activa
            portafolio = attrs.get("portafolio")
            if portafolio is None and not puede_crear_entidades(user):
                raise PermissionDenied("Elige un portafolio donde puedas crear entidades.")
            if portafolio is not None and not puede_crear_en_portafolio(user, portafolio.pk):
                raise PermissionDenied("No puedes crear entidades en ese portafolio.")
        elif attrs.get("estado", instancia.estado) != instancia.estado and not (
            puede_archivar_entidad(user, instancia)
        ):
            raise PermissionDenied("No tienes permiso para archivar o reactivar esta entidad.")
        return attrs

    def create(self, validated_data: dict) -> Entidad:
        user = self.context["request"].user
        validated_data["creado_por"] = user
        if "portafolio" not in validated_data:
            validated_data["portafolio"] = portafolio_personal(user, self.context["request"])
        return super().create(validated_data)


class MiembroSerializer(serializers.ModelSerializer):
    """Una membresía, con los datos básicos de la persona y su rol."""

    username = serializers.CharField(source="usuario.username", read_only=True)
    first_name = serializers.CharField(source="usuario.first_name", read_only=True)
    last_name = serializers.CharField(source="usuario.last_name", read_only=True)
    email = serializers.EmailField(source="usuario.email", read_only=True)
    rol_nombre = serializers.CharField(source="rol.name", read_only=True)
    nivel = serializers.SerializerMethodField()

    class Meta:
        model = Membresia
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

    def get_nivel(self, obj: Membresia) -> int | None:
        perfil = getattr(obj.rol, "perfil", None)
        return perfil.nivel if perfil else None


def _validar_rol_de_entidad(rol: Group) -> None:
    perfil = getattr(rol, "perfil", None)
    if perfil is None or perfil.ambito != "entidad":
        raise serializers.ValidationError({"rol": "Este rol no se puede asignar a una entidad."})


class MiembroCrearSerializer(serializers.Serializer):
    """Crea la cuenta de una persona nueva y la suma a la entidad con un rol.

    Para una cuenta que ya existe se usa una invitación (`InvitacionCrearSerializer`, D-27).
    """

    new_user = RegisterSerializer(help_text="Datos para crear la cuenta.")
    rol = serializers.PrimaryKeyRelatedField(queryset=Group.objects.select_related("perfil"))

    def validate(self, attrs: dict) -> dict:
        rol = attrs["rol"]
        _validar_rol_de_entidad(rol)
        actor = self.context["request"].user
        if not puede_gestionar_rol(actor, self.context["entidad"], rol):
            raise PermissionDenied(
                "No puedes asignar ese rol: su nivel no es menor al tuyo o no tienes permiso."
            )
        return attrs


class MiembroEditarSerializer(serializers.Serializer):
    """Cambia el rol de un miembro o lo activa o desactiva."""

    rol = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.select_related("perfil"), required=False
    )
    activa = serializers.BooleanField(required=False)

    def validate(self, attrs: dict) -> dict:
        membresia: Membresia = self.instance
        actor = self.context["request"].user
        entidad = self.context["entidad"]
        if membresia.usuario_id == actor.pk and not es_administrador_global(actor):
            raise PermissionDenied("No puedes modificar tu propia membresía.")
        if not puede_gestionar_rol(actor, entidad, membresia.rol):
            raise PermissionDenied(
                "No puedes gestionar a alguien con un nivel igual o superior al tuyo."
            )
        nuevo = attrs.get("rol")
        if nuevo is not None and nuevo != membresia.rol:
            _validar_rol_de_entidad(nuevo)
            if not puede_gestionar_rol(actor, entidad, nuevo):
                raise PermissionDenied("No puedes asignar ese rol: su nivel no es menor al tuyo.")
        return attrs

    def update(self, instance: Membresia, validated_data: dict) -> Membresia:
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        instance.save()
        return instance


class RolAsignableSerializer(serializers.Serializer):
    """Un rol que quien consulta puede asignar en la entidad (para los formularios de miembros)."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    nivel = serializers.IntegerField(source="perfil.nivel")


class CandidatoSerializer(serializers.Serializer):
    """Una cuenta que se puede sumar a la entidad (resultado de la búsqueda)."""

    id = serializers.IntegerField()
    username = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class InvitacionCrearSerializer(serializers.Serializer):
    """Invita a una cuenta que ya existe a unirse a la entidad con un rol."""

    username = serializers.CharField(help_text="Nombre de usuario de la cuenta a invitar.")
    rol = serializers.PrimaryKeyRelatedField(queryset=Group.objects.select_related("perfil"))

    def validate_username(self, value: str) -> str:
        return value.strip()

    def validate(self, attrs: dict) -> dict:
        rol = attrs["rol"]
        _validar_rol_de_entidad(rol)
        actor = self.context["request"].user
        if not puede_gestionar_rol(actor, self.context["entidad"], rol):
            raise PermissionDenied(
                "No puedes asignar ese rol: su nivel no es menor al tuyo o no tienes permiso."
            )
        return attrs


class InvitacionSerializer(serializers.ModelSerializer):
    """Una invitación, con lo necesario para mostrarla a quien la envía y a quien la recibe."""

    entidad_nombre = serializers.CharField(source="entidad.nombre", read_only=True)
    tipo_nombre = serializers.CharField(source="entidad.tipo.nombre", read_only=True)
    username = serializers.CharField(source="usuario.username", read_only=True)
    first_name = serializers.CharField(source="usuario.first_name", read_only=True)
    last_name = serializers.CharField(source="usuario.last_name", read_only=True)
    rol_nombre = serializers.CharField(source="rol.name", read_only=True)
    invitado_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Invitacion
        fields = (
            "id",
            "entidad",
            "entidad_nombre",
            "tipo_nombre",
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

    def get_invitado_por_nombre(self, obj: Invitacion) -> str:
        quien = obj.invitado_por
        if quien is None:
            return ""
        return f"{quien.first_name} {quien.last_name}".strip() or quien.get_username()


class MoverEntidadSerializer(serializers.Serializer):
    """Cambia una entidad de portafolio (D-29)."""

    portafolio = serializers.PrimaryKeyRelatedField(queryset=Portafolio.objects.all())
