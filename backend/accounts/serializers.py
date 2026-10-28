import math

from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, AuthenticationFailed, PermissionDenied
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .roles import ROL_ADMIN


class AccountLocked(APIException):
    """423: la cuenta está bloqueada por demasiados intentos fallidos (HU-21)."""

    status_code = status.HTTP_423_LOCKED
    default_code = "account_locked"

    def __init__(self, user: User) -> None:
        segundos = (user.locked_until - timezone.now()).total_seconds()
        minutos = max(1, math.ceil(segundos / 60))
        super().__init__(
            f"Cuenta bloqueada por intentos fallidos. Inténtalo de nuevo en {minutos} "
            "minuto(s) o pide a un administrador que la desbloquee."
        )


class LoginSerializer(TokenObtainPairSerializer):
    """Login JWT con bloqueo tras varios intentos fallidos de contraseña.

    - Cuenta bloqueada: se rechaza aunque la contraseña sea correcta.
    - Fallo de contraseña en un usuario existente y activo: suma un intento; al llegar al
      máximo se bloquea. Usuario inexistente o inactivo: mismo 401, sin contar nada.
    - Éxito: reinicia el contador.
    La fila del usuario se bloquea (`select_for_update`) para que intentos simultáneos no
    se salten el límite. Las excepciones se lanzan fuera de la transacción: si no, el
    `rollback` desharía el conteo.
    """

    def validate(self, attrs: dict) -> dict:
        username = attrs.get(self.username_field)
        data: dict | None = None
        error: AuthenticationFailed | None = None
        locked_user: User | None = None

        with transaction.atomic():
            user = User.objects.select_for_update().filter(username=username).first()
            if user is not None:
                user.release_if_expired()
            if user is not None and user.is_locked:
                locked_user = user
            else:
                try:
                    data = super().validate(attrs)
                except AuthenticationFailed as exc:
                    error = exc
                    if user is not None and user.is_active and user.register_failed_login():
                        locked_user = user
                else:
                    if user is not None:
                        user.unlock()

        if locked_user is not None:
            raise AccountLocked(locked_user)
        if error is not None:
            raise error
        assert data is not None
        return data


def normalizar_correo(value: str | None, excluir_pk: int | None = None) -> str | None:
    """Correo opcional: vacío → None; si existe, minúsculas y único sin importar mayúsculas."""
    value = (value or "").strip().lower()
    if not value:
        return None
    if User.objects.filter(email__iexact=value).exclude(pk=excluir_pk).exists():
        raise serializers.ValidationError("Ya existe un usuario con este correo.")
    return value


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ("id", "username", "email", "password", "first_name", "last_name")
        read_only_fields = ("id",)

    def validate_email(self, value: str | None) -> str | None:
        return normalizar_correo(value)

    def validate(self, attrs: dict) -> dict:
        # Se valida con los datos del usuario para detectar claves parecidas al nombre/correo.
        datos = {k: v for k, v in attrs.items() if k != "password"}
        try:
            validate_password(attrs["password"], User(**datos))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data: dict) -> User:
        return User.objects.create_user(**validated_data)


class LogoutSerializer(serializers.Serializer):
    """Invalida (lista negra) el refresh token recibido."""

    refresh = serializers.CharField()

    def validate_refresh(self, value: str) -> str:
        try:
            self.token = RefreshToken(value)
        except TokenError as exc:
            raise serializers.ValidationError("Token inválido o expirado.") from exc
        return value

    def save(self, **kwargs) -> None:
        self.token.blacklist()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_old_password(self, value: str) -> str:
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("La contraseña actual es incorrecta.")
        return value

    def validate_new_password(self, value: str) -> str:
        validate_password(value, self.context["request"].user)
        return value

    def save(self, **kwargs) -> None:
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])


class UserSerializer(serializers.ModelSerializer):
    """Perfil del usuario autenticado. El username no se puede cambiar."""

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "date_joined")
        read_only_fields = ("id", "username", "date_joined")

    def validate_email(self, value: str | None) -> str | None:
        return normalizar_correo(value, excluir_pk=self.instance.pk)


class UserAdminSerializer(serializers.ModelSerializer):
    """Gestión de usuarios por el rol Admin (HU-24).

    - `username` solo se define al crear; la contraseña solo se define al crear.
    - `is_admin` (rol global Admin) solo lo cambia un superusuario (D-16).
    - `is_staff` e `is_superuser` no existen aquí: nunca se pueden dar por la API.
    """

    password = serializers.CharField(
        write_only=True, required=False, style={"input_type": "password"}
    )
    is_admin = serializers.BooleanField(required=False)
    is_locked = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_admin",
            "password",
            "failed_attempts",
            "locked_until",
            "is_locked",
            "date_joined",
        )
        read_only_fields = ("id", "failed_attempts", "locked_until", "date_joined")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.instance is not None:
            self.fields["username"].read_only = True

    def validate_email(self, value: str | None) -> str | None:
        return normalizar_correo(value, excluir_pk=self.instance.pk if self.instance else None)

    def validate_is_admin(self, value: bool) -> bool:
        actual = self.instance.is_admin if self.instance else False
        if value != actual and not self.context["request"].user.is_superuser:
            raise PermissionDenied("Solo un superusuario puede crear o quitar administradores.")
        return value

    def validate(self, attrs: dict) -> dict:
        if self.instance is None:
            if "password" not in attrs:
                raise serializers.ValidationError({"password": "Este campo es requerido."})
            datos = {k: v for k, v in attrs.items() if k not in ("password", "is_admin")}
            try:
                validate_password(attrs["password"], User(**datos))
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": list(exc.messages)}) from exc
            return attrs
        if "password" in attrs:
            raise serializers.ValidationError(
                {"password": "La contraseña no se cambia desde aquí."}
            )
        if self.instance == self.context["request"].user and attrs.get("is_active") is False:
            raise serializers.ValidationError(
                {"is_active": "No puedes desactivar tu propia cuenta."}
            )
        return attrs

    def _asignar_rol_admin(self, user: User, es_admin: bool | None) -> None:
        if es_admin is None:
            return
        grupo = Group.objects.get(name=ROL_ADMIN)
        if es_admin:
            user.groups.add(grupo)
        else:
            user.groups.remove(grupo)

    @transaction.atomic
    def create(self, validated_data: dict) -> User:
        es_admin = validated_data.pop("is_admin", None)
        user = User.objects.create_user(**validated_data)
        self._asignar_rol_admin(user, es_admin)
        return user

    @transaction.atomic
    def update(self, instance: User, validated_data: dict) -> User:
        es_admin = validated_data.pop("is_admin", None)
        user = super().update(instance, validated_data)
        self._asignar_rol_admin(user, es_admin)
        return User.objects.prefetch_related("groups").get(pk=user.pk)
