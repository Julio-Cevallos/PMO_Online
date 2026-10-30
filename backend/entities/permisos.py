"""Reglas de acceso a entidades y miembros (D-16, D-18, D-19, D-29).

- Admin y superusuario administran **todas** las entidades y sus membresías, pero eso no les
  da acceso al contenido de las entidades (punto abierto de D-16). Por eso aquí el permiso de
  un rol dentro de una entidad (`tiene_permiso_en_entidad`) no cede ante el Admin.
- Cada entidad pertenece a un **portafolio** (D-29). Quien tenga un rol en él (Gestor,
  Coordinador…) gestiona sus entidades según los permisos de ese rol (ver `portafolios.py`),
  sin necesidad de ser miembro de cada entidad.
- Los demás usuarios solo ven las entidades donde tienen una membresía activa.
"""

from django.contrib.auth.models import Group
from django.db.models import Q, QuerySet
from rest_framework.permissions import BasePermission

from accounts.jerarquia import puede_asignar
from accounts.models import User

from .models import Entidad, Membresia, MembresiaPortafolio
from .portafolios import (
    PERMISO_ARCHIVAR_ENTIDADES,
    PERMISO_CREAR_ENTIDADES,
    PERMISO_EDITAR_ENTIDADES,
    PERMISO_GESTIONAR_MIEMBROS_ENTIDAD,
    PERMISO_MOVER_ENTIDADES,
    PERMISO_VER,
    PERMISO_VER_HISTORIAL,
    permisos_en_portafolio,
    portafolios_con_permiso,
    puede_en_portafolio,
)

PERMISO_ADMINISTRAR = "entities.manage_entities"
PERMISO_CREAR = "entities.create_entity"
PERMISO_EDITAR = "entities.edit_entity"
PERMISO_VER_MIEMBROS = "entities.view_members"
PERMISO_GESTIONAR_MIEMBROS = "entities.manage_members"
# Permisos de `audit` (strings, para no importar `audit`, que ya importa este módulo).
PERMISO_HISTORIAL_SISTEMA = "audit.view_system_log"
PERMISO_HISTORIAL_ENTIDAD = "audit.view_entity_log"


def es_administrador_global(user) -> bool:
    """Superusuario o rol Admin (tiene `entities.manage_entities`)."""
    return bool(user and user.is_authenticated and user.has_perm(PERMISO_ADMINISTRAR))


def puede_crear_entidades(user) -> bool:
    """Admin, superusuario o Moderador: pueden crear portafolios y entidades por su cuenta."""
    return bool(user and user.is_authenticated and user.has_perm(PERMISO_CREAR))


def puede_crear_en_portafolio(user, portafolio_id: int) -> bool:
    return puede_en_portafolio(user, portafolio_id, PERMISO_CREAR_ENTIDADES)


def entidades_visibles(user) -> QuerySet[Entidad]:
    """El Admin ve todas; los demás, aquellas donde son miembros y las de sus portafolios."""
    if es_administrador_global(user):
        return Entidad.objects.all()
    visibles = Q(membresias__usuario=user, membresias__activa=True)
    visibles |= Q(portafolio_id__in=portafolios_con_permiso(user, PERMISO_VER))
    return Entidad.objects.filter(visibles).distinct()


def entidades_de_mis_portafolios(user, permiso: str) -> QuerySet:
    """Ids de las entidades de los portafolios donde el usuario tiene `permiso` (sin el Admin)."""
    return Entidad.objects.filter(
        portafolio_id__in=portafolios_con_permiso(user, permiso)
    ).values_list("pk", flat=True)


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


def _en_portafolio(user, entidad: Entidad, permiso: str) -> bool:
    return puede_en_portafolio(user, entidad.portafolio_id, permiso)


def puede_editar_entidad(user, entidad: Entidad) -> bool:
    return _en_portafolio(user, entidad, PERMISO_EDITAR_ENTIDADES) or tiene_permiso_en_entidad(
        user, entidad, PERMISO_EDITAR
    )


def puede_ver_miembros(user, entidad: Entidad) -> bool:
    return (
        _en_portafolio(user, entidad, PERMISO_VER)
        or tiene_permiso_en_entidad(user, entidad, PERMISO_VER_MIEMBROS)
        or tiene_permiso_en_entidad(user, entidad, PERMISO_GESTIONAR_MIEMBROS)
    )


def puede_ver_historial(user, entidad: Entidad) -> bool:
    """¿Ve el historial de auditoría de esta entidad? Mismo criterio que `audit.visibilidad`."""
    return (
        user.has_perm(PERMISO_HISTORIAL_SISTEMA)
        or (
            not es_administrador_global(user)
            and _en_portafolio(user, entidad, PERMISO_VER_HISTORIAL)
        )
        or tiene_permiso_en_entidad(user, entidad, PERMISO_HISTORIAL_ENTIDAD)
    )


def puede_gestionar_miembros(user, entidad: Entidad) -> bool:
    """¿Puede, en general, crear o modificar miembros? (Falta aún la jerarquía por rol.)"""
    return _en_portafolio(
        user, entidad, PERMISO_GESTIONAR_MIEMBROS_ENTIDAD
    ) or tiene_permiso_en_entidad(user, entidad, PERMISO_GESTIONAR_MIEMBROS)


def puede_archivar_entidad(user, entidad: Entidad) -> bool:
    return _en_portafolio(user, entidad, PERMISO_ARCHIVAR_ENTIDADES)


def puede_mover_entidad(user, entidad: Entidad) -> bool:
    return _en_portafolio(user, entidad, PERMISO_MOVER_ENTIDADES)


def candidatos_para_entidad(actor, entidad: Entidad, texto: str = "") -> QuerySet[User]:
    """Cuentas que `actor` puede buscar para sumar a `entidad` (D-26).

    - Nunca superusuarios, cuentas desactivadas, el propio actor ni quien ya es miembro activo.
    - Admin y superusuario: cualquier otra cuenta.
    - Los demás: solo cuentas con membresía activa en alguna **otra** entidad que el actor
      también ve como miembro o a través de sus portafolios (así nadie descubre cuentas ajenas a
      su círculo).
    `texto` busca por usuario, nombre o apellido (cada palabra debe aparecer en alguno).
    """
    cuentas = (
        User.objects.filter(is_active=True, is_superuser=False)
        .exclude(pk=actor.pk)
        .exclude(pk__in=Membresia.objects.filter(entidad=entidad, activa=True).values("usuario"))
    )
    if not es_administrador_global(actor):
        propias = Membresia.objects.filter(usuario=actor, activa=True).values("entidad")
        cercanas = Q(pk__in=propias) | Q(pk__in=entidades_de_mis_portafolios(actor, PERMISO_VER))
        cuentas = cuentas.filter(
            membresias__activa=True,
            membresias__entidad__in=Entidad.objects.filter(cercanas).exclude(pk=entidad.pk),
        )
    for palabra in texto.split():
        cuentas = cuentas.filter(
            Q(username__icontains=palabra)
            | Q(first_name__icontains=palabra)
            | Q(last_name__icontains=palabra)
        )
    return cuentas.distinct().order_by("username")


def puede_gestionar_rol(actor, entidad: Entidad, rol: Group) -> bool:
    """¿`actor` puede crear, asignar, cambiar o quitar el rol `rol` en `entidad`? (D-18)

    Quien gestiona las entidades del portafolio (Admin, superusuario, Gestor, Coordinador) puede
    con cualquier rol de entidad. Los demás: necesitan el permiso `manage_members` en la entidad,
    un nivel estrictamente mayor al del rol y alcanzar su nivel mínimo para asignarlo. Un rol sin
    perfil (como `Admin`, que es global) solo lo gestionan el Admin y el superusuario.
    """
    if _en_portafolio(actor, entidad, PERMISO_GESTIONAR_MIEMBROS_ENTIDAD):
        return True
    membresia = membresia_activa(actor, entidad)
    if membresia is None or not rol_tiene_permiso(membresia.rol, PERMISO_GESTIONAR_MIEMBROS):
        return False
    perfil_actor = getattr(membresia.rol, "perfil", None)
    perfil_objetivo = getattr(rol, "perfil", None)
    if perfil_actor is None or perfil_objetivo is None:
        return False
    return puede_asignar(perfil_actor.nivel, perfil_objetivo)


def membresias_activas(user) -> dict[int, dict]:
    """Membresías activas del usuario: `{entidad_id: {"rol": nombre, "permisos": {...}}}`.

    Son 3 consultas en total, sin importar cuántas entidades haya (evita N+1 al listar).
    """
    miembros = (
        Membresia.objects.filter(usuario=user, activa=True)
        .select_related("rol")
        .prefetch_related("rol__permissions__content_type")
    )
    return {
        m.entidad_id: {
            "rol": m.rol.name,
            "permisos": {
                f"{p.content_type.app_label}.{p.codename}" for p in m.rol.permissions.all()
            },
        }
        for m in miembros
    }


def capacidades(
    user,
    info: dict | None,
    entidad: Entidad,
    portafolios: dict[int, dict] | None = None,
) -> dict[str, bool]:
    """Qué puede hacer `user` en `entidad`: su membresía (`info`) y sus roles de portafolio.

    Debe coincidir con las funciones `puede_*` de este módulo (hay una prueba que lo verifica);
    esta versión evita consultar la base de datos por cada entidad al listar (`portafolios` es el
    resultado de `membresias_portafolio_activas`).
    """
    permisos = info["permisos"] if info else set()
    pf = permisos_en_portafolio(user, entidad.portafolio_id, portafolios)
    historial = (
        user.has_perm(PERMISO_HISTORIAL_SISTEMA)
        or (not es_administrador_global(user) and PERMISO_VER_HISTORIAL in pf)
        or PERMISO_HISTORIAL_ENTIDAD in permisos
    )
    gestionar = PERMISO_GESTIONAR_MIEMBROS_ENTIDAD in pf or PERMISO_GESTIONAR_MIEMBROS in permisos
    return {
        "editar": PERMISO_EDITAR_ENTIDADES in pf or PERMISO_EDITAR in permisos,
        "ver_miembros": PERMISO_VER in pf or PERMISO_VER_MIEMBROS in permisos or gestionar,
        "gestionar_miembros": gestionar,
        "ver_historial": historial,
        "archivar": PERMISO_ARCHIVAR_ENTIDADES in pf,
        "mover": PERMISO_MOVER_ENTIDADES in pf,
    }


def roles_asignables(actor, entidad: Entidad) -> list[Group]:
    """Roles de entidad que `actor` puede asignar en `entidad`, del de más nivel al de menos."""
    roles = (
        Group.objects.select_related("perfil")
        .filter(perfil__ambito="entidad")
        .order_by("-perfil__nivel", "name")
    )
    if _en_portafolio(actor, entidad, PERMISO_GESTIONAR_MIEMBROS_ENTIDAD):
        return list(roles)
    membresia = membresia_activa(actor, entidad)
    if membresia is None or not rol_tiene_permiso(membresia.rol, PERMISO_GESTIONAR_MIEMBROS):
        return []
    perfil_actor = getattr(membresia.rol, "perfil", None)
    if perfil_actor is None:
        return []
    return [r for r in roles if puede_asignar(perfil_actor.nivel, r.perfil)]


def entidades_con_permiso(user, permiso: str) -> QuerySet:
    """Ids de las entidades donde el usuario es miembro activo con un rol que incluye `permiso`."""
    app, _, codigo = permiso.partition(".")
    return (
        Membresia.objects.filter(
            usuario=user,
            activa=True,
            rol__permissions__content_type__app_label=app,
            rol__permissions__codename=codigo,
        )
        .values_list("entidad_id", flat=True)
        .distinct()
    )


class PuedeVerTipos(BasePermission):
    """Ver los tipos de entidad: quien puede crear entidades, o es miembro de una o de un portafolio."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return (
            puede_crear_entidades(user)
            or Membresia.objects.filter(usuario=user, activa=True).exists()
            or MembresiaPortafolio.objects.filter(usuario=user, activa=True).exists()
        )


class PuedeCrearEntidades(BasePermission):
    """Crear entidades: Admin y Moderador (en su portafolio personal), o quien tenga ese permiso
    en algún portafolio (Gestor, Coordinador). El portafolio concreto se valida al crear."""

    message = "No tienes permiso para crear entidades."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return puede_crear_entidades(user) or bool(
            portafolios_con_permiso(user, PERMISO_CREAR_ENTIDADES)
        )
