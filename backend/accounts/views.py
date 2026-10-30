from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from . import auditoria
from .models import User
from .permissions import requiere_permiso
from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    RegisterSerializer,
    UserAdminSerializer,
)
from .serializers_me import MeSerializer


class LoginView(TokenObtainPairView):
    """Inicio de sesión (access + refresh). 401 credenciales inválidas, 423 cuenta bloqueada."""

    serializer_class = LoginSerializer

    # El esquema sigue describiendo el serializer estándar de simplejwt (access/refresh):
    # drf-spectacular solo conoce esa clase exacta, no la nuestra.
    @extend_schema(
        request=TokenObtainPairSerializer,
        responses={
            200: TokenObtainPairSerializer,
            401: OpenApiResponse(description="Credenciales inválidas"),
            423: OpenApiResponse(description="Cuenta bloqueada por intentos fallidos"),
        },
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        return super().post(request, *args, **kwargs)


class RegisterView(generics.CreateAPIView):
    """Registro público de usuarios."""

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = (permissions.AllowAny,)

    @transaction.atomic
    def perform_create(self, serializer: RegisterSerializer) -> None:
        user = serializer.save()
        auditoria.usuario_registrado(self.request, user)


class MeView(generics.RetrieveUpdateAPIView):
    """Perfil del usuario autenticado (GET, PUT, PATCH), con su rol global y permisos."""

    serializer_class = MeSerializer

    def get_object(self) -> User:
        return self.request.user

    @transaction.atomic
    def perform_update(self, serializer: MeSerializer) -> None:
        antes = auditoria.foto_usuario(self.request.user)
        usuario = serializer.save()
        auditoria.perfil_editado(self.request, usuario, antes)


class LogoutView(APIView):
    """Cierra sesión: el refresh token queda en lista negra.

    Es público porque la validez la da el propio refresh token; así se puede
    cerrar sesión aunque el access token ya haya expirado.
    """

    permission_classes = (permissions.AllowAny,)
    authentication_classes: tuple = ()

    @extend_schema(request=LogoutSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangePasswordView(APIView):
    """Cambia la contraseña del usuario autenticado."""

    @extend_schema(request=ChangePasswordSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save()
            auditoria.clave_cambiada(request, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserAdminViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Gestión de usuarios (solo con el permiso `accounts.manage_users`, es decir, el rol Admin).

    No hay DELETE: las cuentas se desactivan (`is_active`) para conservar la trazabilidad.
    Los superusuarios no aparecen para el Admin (D-16).
    """

    serializer_class = UserAdminSerializer
    permission_classes = (requiere_permiso("accounts.manage_users"),)
    # Solo JSON: en formularios (multipart) DRF interpreta un booleano ausente como `false`
    # y crearía cuentas inactivas sin avisar.
    parser_classes = (JSONParser,)
    filterset_fields = ("is_active",)
    http_method_names = ("get", "post", "patch", "head", "options")

    def get_queryset(self):
        usuarios = User.objects.prefetch_related("groups").order_by("username")
        if not self.request.user.is_superuser:
            usuarios = usuarios.filter(is_superuser=False)
        return usuarios

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["post"])
    def unlock(self, request: Request, pk: str | None = None) -> Response:
        """Quita el bloqueo por intentos fallidos y reinicia el contador."""
        usuario = self.get_object()
        with transaction.atomic():
            usuario.unlock()
            auditoria.cuenta_desbloqueada(request, usuario)
        return Response(status=status.HTTP_204_NO_CONTENT)
