"""Reglas de acceso a entidades y miembros (D-16, D-18, D-19).

- Admin y superusuario administran **todas** las entidades y sus membresías, pero eso no les
  da acceso al contenido de las entidades (punto abierto de D-16). Por eso aquí el permiso de
  un rol dentro de una entidad (`tiene_permiso_en_entidad`) no cede ante el Admin.
- Los demás usuarios solo ven las entidades donde tienen una membresía activa.
"""

from django.contrib.auth.models import Group
from django.db.models import QuerySet
from rest_framework.permissions import BasePermission

from accounts.jerarquia import puede_asignar

from .models import Entidad, Membresia

PERMISO_ADMINISTRAR = "entities.manage_entities"
PERMISO_EDITAR = "entities.edit_entity"
PERMISO_VER_MIEMBROS = "entities.view_members"
PERMISO_GESTIONAR_MIEMBROS = "entities.manage_members"


def es_administrador_global(user) -> bool:
    """Superusuario o rol Admin (tiene `entities.manage_entities`)."""
    return bool(user and user.is_authenticated and user.has_perm(PERMISO_ADMINISTRAR))


def entidades_visibles(user) -> QuerySet[Entidad]:
    if es_administrador_global(user):
        return Entidad.objects.all()
    return Entidad.objects.filter(membresias__usuario=user, membresias__activa=True)


def membresia_activa(user, entidad: Entidad) -> Membresia | None:
    return (
        Membresia.objects.select_related("rol__perfil")
        .filter(usuario=user, entidad=entidad, activa=True)
        .first()
    )


def rol_tiene_permiso(rol: Group, permiso: str) -> bool:
    app, _, codigo = permiso.partition(".")
    return rol.permissions.filter(content_type__app_label=app, codename=codigo).exists()


def tiene_permiso_en_entidad(user, entidad: Entidad, permiso: str) -> bool:
    """¿El rol del usuario en esa entidad incluye `permiso`? (El superusuario siempre.)"""
    if user.is_superuser:
        return True
    membresia = membresia_activa(user, entidad)
    return membresia is not None and rol_tiene_permiso(membresia.rol, permiso)


def puede_editar_entidad(user, entidad: Entidad) -> bool:
    return es_administrador_global(user) or tiene_permiso_en_entidad(user, entidad, PERMISO_EDITAR)


def puede_ver_miembros(user, entidad: Entidad) -> bool:
    return (
        es_administrador_global(user)
        or tiene_permiso_en_entidad(user, entidad, PERMISO_VER_MIEMBROS)
        or tiene_permiso_en_entidad(user, entidad, PERMISO_GESTIONAR_MIEMBROS)
    )


def puede_gestionar_miembros(user, entidad: Entidad) -> bool:
    """¿Puede, en general, crear o modificar miembros? (Falta aún la jerarquía por rol.)"""
    return es_administrador_global(user) or tiene_permiso_en_entidad(
        user, entidad, PERMISO_GESTIONAR_MIEMBROS
    )


def puede_gestionar_rol(actor, entidad: Entidad, rol: Group) -> bool:
    """¿`actor` puede crear, asignar, cambiar o quitar el rol `rol` en `entidad`? (D-18)

    Admin y superusuario: sí. Los demás: necesitan el permiso `manage_members`, un nivel
    estrictamente mayor al del rol y alcanzar su nivel mínimo para asignarlo. Un rol sin perfil
    (como `Admin`, que es global) solo lo gestionan el Admin y el superusuario.
    """
    if es_administrador_global(actor):
        return True
    membresia = membresia_activa(actor, entidad)
    if membresia is None or not rol_tiene_permiso(membresia.rol, PERMISO_GESTIONAR_MIEMBROS):
        return False
    perfil_actor = getattr(membresia.rol, "perfil", None)
    perfil_objetivo = getattr(rol, "perfil", None)
    if perfil_actor is None or perfil_objetivo is None:
        return False
    return puede_asignar(perfil_actor.nivel, perfil_objetivo)


class PuedeVerTipos(BasePermission):
    """Ver los tipos de entidad: Admin o alguien con al menos una membresía activa."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return (
            es_administrador_global(user)
            or Membresia.objects.filter(usuario=user, activa=True).exists()
        )
