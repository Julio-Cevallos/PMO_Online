"""Roles del sistema y catálogo de permisos globales (D-15, D-16).

Los roles son `Group` de Django. Solo `Admin` es global; el resto se asigna por entidad
(llega con el módulo `entities`) y por eso aquí solo se crean vacíos.
"""

from django.contrib.auth.models import Group, Permission
from django.db.models import Q

ROL_ADMIN = "Admin"
ROLES_POR_ENTIDAD = ("Responsable de entidad", "Planificador", "Operario de campo", "Auditor")

# Niveles de los roles del sistema: (nivel, nivel mínimo para asignarlo). Ver D-18.
# El Auditor lo asigna solo el Responsable (40) aunque el Planificador (30) tenga más nivel.
NIVELES_SISTEMA = {
    "Responsable de entidad": (40, 41),
    "Planificador": (30, 31),
    "Auditor": (20, 40),
    "Operario de campo": (10, 11),
}

# Permisos globales: solo los tiene el rol Admin (o un superusuario). Ningún rol por entidad
# puede recibirlos (evita escaladas de privilegios).
PERMISOS_GLOBALES = {
    "manage_users": "Gestionar usuarios del sistema",
    "manage_roles": "Gestionar roles y sus permisos",
}


def sincronizar_roles_del_sistema(**kwargs) -> None:
    """Crea los roles del sistema si faltan y fija los permisos de `Admin` (todos los globales).

    También crea su `PerfilRol` si falta (sin pisar los niveles que el Admin haya cambiado).
    Se ejecuta tras cada `migrate` (señal `post_migrate`), es idempotente y no toca los
    permisos de los demás roles: esos los edita el Admin.
    """
    permisos = Permission.objects.filter(
        content_type__app_label="accounts", codename__in=list(PERMISOS_GLOBALES)
    )
    if permisos.count() != len(PERMISOS_GLOBALES):
        return  # los permisos aún no existen (otra app está migrando)
    from .catalogo import (  # import tardío: catalogo usa este módulo
        AMBITO_GLOBAL,
        permisos_registrados,
    )

    globales = Q()
    for definicion in permisos_registrados():
        if definicion.ambito == AMBITO_GLOBAL:
            app, _, codigo = definicion.codename.partition(".")
            globales |= Q(content_type__app_label=app, codename=codigo)
    admin, _ = Group.objects.get_or_create(name=ROL_ADMIN)
    admin.permissions.set(Permission.objects.filter(globales))
    from .models import PerfilRol  # import tardío: models importa este módulo

    for nombre in ROLES_POR_ENTIDAD:
        grupo, _ = Group.objects.get_or_create(name=nombre)
        nivel, minimo = NIVELES_SISTEMA[nombre]
        # Solo si falta: el Admin puede haber ajustado los niveles y no se pisan.
        PerfilRol.objects.get_or_create(
            grupo=grupo, defaults={"nivel": nivel, "nivel_minimo_para_asignar": minimo}
        )
