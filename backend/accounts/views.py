from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .serializers import (
    ChangePasswordSerializer,
    LogoutSerializer,
    RegisterSerializer,
    UserSerializer,
)


class RegisterView(generics.CreateAPIView):
    """Registro público de usuarios."""

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = (permissions.AllowAny,)


class MeView(generics.RetrieveUpdateAPIView):
    """Perfil del usuario autenticado (GET, PUT, PATCH)."""

    serializer_class = UserSerializer

    def get_object(self) -> User:
        return self.request.user


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
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
