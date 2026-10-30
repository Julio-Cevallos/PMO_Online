"""Reglas de acceso a portafolios (D-29).

Un portafolio agrupa entidades y las gestionan en conjunto las personas que tienen un rol en él.
Lo que cada una puede hacer depende de los permisos de su rol de portafolio (`PERMISO_*`):

| Permiso                       | Gestor | Coordinador |
|-------------------------------|--------|-------------|
| `view_portfolio`              | sí     | sí          |
| `create_portfolio_entities`   | sí     | sí          |
| `edit_portfolio_entities`     | sí     | sí          |
| `manage_portfolio_entity_members` | sí | sí          |
| `view_portfolio_log`          | sí     | sí          |
| `archive_portfolio_entities`  | sí     | no          |
| `move_portfolio_entities`     | sí     | no          |
| `edit_portfolio`              | sí     | no          |
| `manage_portfolio_members`    | sí     | no          |

El Admin y el superusuario tienen todos, en todos los portafolios. Ninguno de estos permisos da
acceso al contenido de las entidades (punto abierto de D-16).
"""

from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import QuerySet

from accounts.jerarquia import puede_asignar_en_portafolio

from .models import MembresiaPortafolio, Portafolio

PERMISO_VER = "entities.view_portfolio"
PERMISO_EDITAR = "entities.edit_portfolio"
PERMISO_CREAR_ENTIDADES = "entities.create_portfolio_entities"
PERMISO_EDITAR_ENTIDADES = "entities.edit_portfolio_entities"
PERMISO_GESTIONAR_MIEMBROS_ENTIDAD = "entities.manage_portfolio_entity_members"
PERMISO_ARCHIVAR_ENTIDADES = "entities.archive_portfolio_entities"
PERMISO_MOVER_ENTIDADES = "entities.move_portfolio_entities"
PERMISO_GESTIONAR_MIEMBROS = "entities.manage_portfolio_members"
PERMISO_VER_HISTORIAL = "entities.view_portfolio_log"

TODOS_LOS_PERMISOS = frozenset(
    {
        PERMISO_VER,
        PERMISO_EDITAR,
        PERMISO_CREAR_ENTIDADES,
        PERMISO_EDITAR_ENTIDADES,
        PERMISO_GESTIONAR_MIEMBROS_ENTIDAD,
        PERMISO_ARCHIVAR_ENTIDADES,
        PERMISO_MOVER_ENTIDADES,
        PERMISO_GESTIONAR_MIEMBROS,
        PERMISO_VER_HISTORIAL,
    }
)

ROL_GESTOR = "Gestor del portafolio"
NOMBRE_PORTAFOLIO_PERSONAL = "Mis entidades"


def _es_admin(user) -> bool:
    """Superusuario o rol Admin (mismo criterio que `permisos.es_administrador_global`)."""
    return bool(user and user.is_authenticated and user.has_perm("entities.manage_entities"))


def membresias_portafolio_activas(user) -> dict[int, dict]:
    """Membresías activas del usuario: `{portafolio_id: {"rol", "nivel", "permisos"}}`.

    Son 3 consultas en total, sin importar cuántos portafolios haya (evita N+1 al listar).
    """
    miembros = (
        MembresiaPortafolio.objects.filter(usuario=user, activa=True)
        .select_related("rol__perfil")
        .prefetch_related("rol__permissions__content_type")
    )
    resultado = {}
    for m in miembros:
        perfil = getattr(m.rol, "perfil", None)
        resultado[m.portafolio_id] = {
            "rol": m.rol.name,
            "nivel": perfil.nivel if perfil else 0,
            "permisos": {
                f"{p.content_type.app_label}.{p.codename}" for p in m.rol.permissions.all()
            },
        }
    return resultado


def permisos_en_portafolio(
    user, portafolio_id: int, mapa: dict[int, dict] | None = None
) -> set[str]:
    """Permisos del usuario en un portafolio. `mapa` evita repetir consultas al listar."""
    if _es_admin(user):
        return set(TODOS_LOS_PERMISOS)
    if mapa is None:
        mapa = membresias_portafolio_activas(user)
    info = mapa.get(portafolio_id)
    return set(info["permisos"]) if info else set()


def puede_en_portafolio(
    user, portafolio_id: int, permiso: str, mapa: dict[int, dict] | None = None
) -> bool:
    return permiso in permisos_en_portafolio(user, portafolio_id, mapa)


def portafolios_con_permiso(user, permiso: str) -> list[int]:
    """Ids de los portafolios donde la membresía activa del usuario incluye `permiso`.

    No incluye el caso del Admin (que tiene todos): quien llama lo trata aparte.
    """
    return [
        portafolio_id
        for portafolio_id, info in membresias_portafolio_activas(user).items()
        if permiso in info["permisos"]
    ]


def portafolios_visibles(user) -> QuerySet[Portafolio]:
    """El Admin ve todos; los demás, aquellos donde tienen una membresía activa."""
    if _es_admin(user):
        return Portafolio.objects.all()
    return Portafolio.objects.filter(membresias__usuario=user, membresias__activa=True).distinct()


def _rol_gestor() -> Group:
    return Group.objects.get(name=ROL_GESTOR)


@transaction.atomic
def portafolio_personal(user, request=None) -> Portafolio:
    """El portafolio personal de `user`: se crea la primera vez (con él como Gestor).

    Si se pasa `request`, la creación queda en el historial de auditoría.
    """
    portafolio = Portafolio.objects.filter(creado_por=user, personal=True).first()
    if portafolio is None:
        portafolio = Portafolio.objects.create(
            nombre=NOMBRE_PORTAFOLIO_PERSONAL, personal=True, creado_por=user
        )
        MembresiaPortafolio.objects.create(
            usuario=user, portafolio=portafolio, rol=_rol_gestor(), creado_por=user
        )
        if request is not None:
            from . import auditoria  # import tardío: auditoria no depende de este módulo

            auditoria.portafolio_creado(request, portafolio)
    return portafolio


def rol_de_portafolio(rol: Group) -> bool:
    """¿Es un rol que se asigna en un portafolio (no en una entidad)?"""
    perfil = getattr(rol, "perfil", None)
    return perfil is not None and perfil.ambito == "portafolio"


def puede_gestionar_rol_de_portafolio(actor, portafolio_id: int, rol: Group) -> bool:
    """¿`actor` puede asignar, cambiar o quitar el rol `rol` en el portafolio? (D-29)

    Hace falta el permiso de gestionar miembros del portafolio y un nivel igual o mayor al del
    rol (los pares pueden nombrarse entre sí, para que varios Gestores colaboren). El Admin y el
    superusuario pueden con cualquier rol de portafolio.
    """
    if not rol_de_portafolio(rol):
        return False
    if _es_admin(actor):
        return True
    info = membresias_portafolio_activas(actor).get(portafolio_id)
    if info is None or PERMISO_GESTIONAR_MIEMBROS not in info["permisos"]:
        return False
    return puede_asignar_en_portafolio(info["nivel"], rol.perfil)


def roles_asignables_en_portafolio(actor, portafolio_id: int) -> list[Group]:
    """Roles de portafolio que `actor` puede asignar, del de más nivel al de menos."""
    roles = (
        Group.objects.select_related("perfil")
        .filter(perfil__ambito="portafolio")
        .order_by("-perfil__nivel", "name")
    )
    return [r for r in roles if puede_gestionar_rol_de_portafolio(actor, portafolio_id, r)]


def gestores_activos(portafolio: Portafolio) -> int:
    """Cuántas personas activas pueden gestionar los miembros del portafolio."""
    return MembresiaPortafolio.objects.filter(
        portafolio=portafolio,
        activa=True,
        rol__permissions__content_type__app_label="entities",
        rol__permissions__codename=PERMISO_GESTIONAR_MIEMBROS.partition(".")[2],
    ).count()


def rol_puede_gestionar_miembros(rol: Group) -> bool:
    """¿El rol incluye gestionar los miembros del portafolio? (Para proteger al último Gestor.)"""
    return rol.permissions.filter(
        content_type__app_label="entities",
        codename=PERMISO_GESTIONAR_MIEMBROS.partition(".")[2],
    ).exists()
