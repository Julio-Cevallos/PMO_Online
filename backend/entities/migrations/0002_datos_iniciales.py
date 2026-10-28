"""Datos iniciales de `entities` (D-19): tipos Proyecto y Sucursal, y permisos por rol.

Es una migración de datos (se ejecuta una sola vez) y no una señal `post_migrate`, para no
pisar los permisos que el Admin ajuste después. Crea las filas de `Permission` a mano porque
Django las genera recién al terminar de migrar.
"""

from django.db import migrations

TIPOS = [("Proyecto", "Proyectos"), ("Sucursal", "Sucursales")]

PERMISOS = {
    "tipoentidad": [("manage_types", "Gestionar tipos de entidad")],
    "entidad": [
        ("manage_entities", "Crear y archivar entidades"),
        ("edit_entity", "Editar los datos de la entidad"),
        ("view_members", "Ver los miembros de la entidad"),
        ("manage_members", "Gestionar los miembros de la entidad"),
    ],
}

# Rol -> permisos iniciales. El Admin recibe los globales; los demás roles, los de entidad.
PERMISOS_POR_ROL = {
    "Admin": ["manage_types", "manage_entities"],
    "Responsable de entidad": ["edit_entity", "view_members", "manage_members"],
    "Planificador": ["view_members"],
}


def sembrar(apps, schema_editor):
    TipoEntidad = apps.get_model("entities", "TipoEntidad")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    for nombre, plural in TIPOS:
        if not TipoEntidad.objects.filter(nombre__iexact=nombre).exists():
            TipoEntidad.objects.create(
                nombre=nombre,
                nombre_plural=plural,
                admite_tareas=True,
                es_filtro_contexto=True,
            )

    permisos = {}
    for modelo, lista in PERMISOS.items():
        contenido, _ = ContentType.objects.get_or_create(app_label="entities", model=modelo)
        for codename, nombre in lista:
            permiso, _ = Permission.objects.get_or_create(
                content_type=contenido, codename=codename, defaults={"name": nombre}
            )
            permisos[codename] = permiso

    for rol, codenames in PERMISOS_POR_ROL.items():
        grupo, _ = Group.objects.get_or_create(name=rol)
        grupo.permissions.add(*[permisos[c] for c in codenames])


class Migration(migrations.Migration):
    dependencies = [
        ("entities", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(sembrar, migrations.RunPython.noop)]
