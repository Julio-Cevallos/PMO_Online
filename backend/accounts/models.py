from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser, Group
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models
from django.utils import timezone

from .roles import PERMISOS_GLOBALES, ROL_ADMIN, ROL_MODERADOR


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

    # Bloqueo por intentos fallidos de inicio de sesión (HU-21, D-15).
    failed_attempts = models.PositiveSmallIntegerField("intentos fallidos", default=0)
    locked_until = models.DateTimeField("bloqueado hasta", null=True, blank=True)

    objects = UserManager()

    REQUIRED_FIELDS: list[str] = []

    class Meta(AbstractUser.Meta):
        # Permisos globales (D-16). Solo los recibe el rol Admin.
        permissions = list(PERMISOS_GLOBALES.items())

    def __str__(self) -> str:
        return self.username

    @property
    def is_admin(self) -> bool:
        """Tiene el rol global Admin. Usa `groups.all()` para aprovechar `prefetch_related`."""
        return any(grupo.name == ROL_ADMIN for grupo in self.groups.all())

    @property
    def is_moderator(self) -> bool:
        """Tiene el rol global Moderador (crea entidades y es dueño de las suyas)."""
        return any(grupo.name == ROL_MODERADOR for grupo in self.groups.all())

    @property
    def is_locked(self) -> bool:
        return self.locked_until is not None and self.locked_until > timezone.now()

    def release_if_expired(self) -> None:
        """Si el bloqueo ya venció, reinicia el contador para empezar de cero."""
        if self.locked_until is not None and self.locked_until <= timezone.now():
            self.unlock()

    def register_failed_login(self) -> bool:
        """Cuenta un intento fallido. Devuelve True si con este la cuenta queda bloqueada."""
        self.failed_attempts += 1
        if self.failed_attempts >= settings.LOGIN_MAX_ATTEMPTS:
            self.locked_until = timezone.now() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
        self.save(update_fields=["failed_attempts", "locked_until"])
        return self.is_locked

    def unlock(self) -> None:
        """Quita el bloqueo y reinicia el contador (inicio de sesión correcto o desbloqueo del Admin)."""
        if self.failed_attempts or self.locked_until is not None:
            self.failed_attempts = 0
            self.locked_until = None
            self.save(update_fields=["failed_attempts", "locked_until"])


class PerfilRol(models.Model):
    """Jerarquía de un rol por entidad (D-18, D-19).

    - `nivel`: a mayor número, más poder dentro de la entidad (1 a 99).
    - `nivel_minimo_para_asignar`: nivel que necesita quien quiera crear, asignar o quitar este
      rol. Además debe tener un nivel estrictamente mayor al del rol. Por defecto es nivel + 1;
      el Auditor lo sube a 40 para que solo el Responsable pueda nombrarlo.

    En los roles de portafolio (`ambito=portafolio`) `nivel_minimo_para_asignar` no se usa: quien
    tenga el permiso de gestionar miembros del portafolio puede asignar roles de su mismo nivel o
    menor (así varios Gestores pueden colaborar).

    El rol `Admin` es global y no tiene perfil: queda por encima de todos los niveles.
    """

    class Ambito(models.TextChoices):
        ENTIDAD = "entidad", "Entidad"
        PORTAFOLIO = "portafolio", "Portafolio"

    grupo = models.OneToOneField(Group, on_delete=models.CASCADE, related_name="perfil")
    # Dónde se asigna el rol: en una entidad (membresía) o en un portafolio (D-29).
    ambito = models.CharField(max_length=10, choices=Ambito.choices, default=Ambito.ENTIDAD)
    nivel = models.PositiveSmallIntegerField("nivel")
    nivel_minimo_para_asignar = models.PositiveSmallIntegerField("nivel mínimo para asignar")

    class Meta:
        verbose_name = "perfil de rol"
        verbose_name_plural = "perfiles de rol"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(nivel__gte=1, nivel__lte=99), name="perfilrol_nivel_1_a_99"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    nivel_minimo_para_asignar__gt=models.F("nivel"),
                    nivel_minimo_para_asignar__lte=100,
                ),
                name="perfilrol_minimo_mayor_que_nivel",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.grupo.name} (nivel {self.nivel})"
