from django.contrib.auth.models import Group
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from accounts.serializers import RegisterSerializer

from .models import Entidad, Membresia, TipoEntidad
from .permisos import es_administrador_global, puede_gestionar_rol


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
            "es_filtro_contexto",
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
    mi_rol = serializers.SerializerMethodField()

    class Meta:
        model = Entidad
        fields = (
            "id",
            "tipo",
            "tipo_nombre",
            "nombre",
            "descripcion",
            "estado",
            "mi_rol",
            "creado_por",
            "creado_en",
        )
        read_only_fields = ("id", "creado_por", "creado_en")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.instance is not None and not isinstance(self.instance, list | tuple):
            self.fields["tipo"].read_only = True

    def get_mi_rol(self, obj: Entidad) -> str | None:
        """Nombre del rol del usuario en la entidad (null si no es miembro, p. ej. el Admin)."""
        return self.context.get("roles_por_entidad", {}).get(obj.pk)

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
        if instancia is None:
            attrs.pop("estado", None)  # toda entidad nueva nace activa
        elif attrs.get("estado", instancia.estado) != instancia.estado and not (
            es_administrador_global(self.context["request"].user)
        ):
            raise PermissionDenied("Solo un administrador archiva o reactiva entidades.")
        return attrs

    def create(self, validated_data: dict) -> Entidad:
        validated_data["creado_por"] = self.context["request"].user
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
    if getattr(rol, "perfil", None) is None:
        raise serializers.ValidationError({"rol": "Este rol no se puede asignar a una entidad."})


class MiembroCrearSerializer(serializers.Serializer):
    """Agrega a una persona a la entidad: una cuenta existente (`username`) o una nueva."""

    username = serializers.CharField(required=False, help_text="Cuenta que ya existe.")
    new_user = RegisterSerializer(required=False, help_text="Datos para crear la cuenta.")
    rol = serializers.PrimaryKeyRelatedField(queryset=Group.objects.select_related("perfil"))

    def validate(self, attrs: dict) -> dict:
        if ("username" in attrs) == ("new_user" in attrs):
            raise serializers.ValidationError("Indica `username` (cuenta existente) o `new_user`.")
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
