from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models


class UserManager(DjangoUserManager):
    @classmethod
    def normalize_email(cls, email: str | None) -> str | None:
        """Correo en minúsculas; vacío se guarda como NULL (varios usuarios pueden no tener correo)."""
        return super().normalize_email(email).lower() or None


class User(AbstractUser):
    """Usuario propio del proyecto.

    Se define desde el inicio (antes de la primera migración) para poder
    agregarle campos después sin reconstruir la base de datos.
    """

    # Opcional, pero si se indica debe ser único. Sin correo se guarda NULL (no "").
    email = models.EmailField("correo electrónico", unique=True, null=True, blank=True)

    objects = UserManager()

    REQUIRED_FIELDS: list[str] = []

    def __str__(self) -> str:
        return self.username
