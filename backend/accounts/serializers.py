from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User


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
