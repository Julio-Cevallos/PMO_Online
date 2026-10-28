"""Utilitarios compartidos por las pruebas de `entities`."""

from django.contrib.auth.models import Group, Permission

from accounts.models import User
from accounts.roles import ROL_ADMIN

from .models import Entidad, Membresia, TipoEntidad

PASSWORD = "Clave-Segura-2026"

RESPONSABLE = "Responsable de entidad"
PLANIFICADOR = "Planificador"
OPERARIO = "Operario de campo"
AUDITOR = "Auditor"


def usuario(nombre: str, *, admin: bool = False, superuser: bool = False) -> User:
    if superuser:
        return User.objects.create_superuser(nombre, f"{nombre}@example.com", PASSWORD)
    user = User.objects.create_user(nombre, f"{nombre}@example.com", PASSWORD)
    if admin:
        user.groups.add(Group.objects.get(name=ROL_ADMIN))
    return User.objects.get(pk=user.pk)  # sin la caché de permisos de la instancia


def entidad(nombre: str = "Alfa", tipo: str = "Proyecto") -> Entidad:
    return Entidad.objects.create(tipo=TipoEntidad.objects.get(nombre=tipo), nombre=nombre)


def miembro(user: User, ent: Entidad, rol: str, *, activa: bool = True) -> Membresia:
    return Membresia.objects.create(
        usuario=user, entidad=ent, rol=Group.objects.get(name=rol), activa=activa
    )


def dar_permiso(rol: str, codename: str) -> None:
    """Concede un permiso a un rol (para probar jerarquías con otros permisos)."""
    Group.objects.get(name=rol).permissions.add(Permission.objects.get(codename=codename))
