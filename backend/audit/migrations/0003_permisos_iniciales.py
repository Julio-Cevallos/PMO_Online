"""Permisos de `audit` y su asignación inicial a los roles (D-21).

Migración de datos (una sola vez) para no pisar lo que el Admin ajuste después. Crea a mano las filas
de `Permission` porque Django las genera recién al terminar de migrar.
"""

from django.db import migrations

PERMISOS = [
    ("view_system_log", "Ver el historial de administración"),
    ("view_entity_log", "Ver el historial de la entidad"),
]

# Admin: administración del sistema. Responsable y Auditor: el historial de sus entidades.
PERMISOS_POR_ROL = {
    "Admin": ["view_system_log"],
    "Responsable de entidad": ["view_entity_log"],
    "Auditor": ["view_entity_log"],
}


def sembrar(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    contenido, _ = ContentType.objects.get_or_create(app_label="audit", model="eventoauditoria")
    permisos = {}
    for codename, nombre in PERMISOS:
        permiso, _ = Permission.objects.get_or_create(
            content_type=contenido, codename=codename, defaults={"name": nombre}
        )
        permisos[codename] = permiso

    for rol, codenames in PERMISOS_POR_ROL.items():
        grupo, _ = Group.objects.get_or_create(name=rol)
        grupo.permissions.add(*[permisos[c] for c in codenames])


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0002_trigger_solo_insercion"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(sembrar, migrations.RunPython.noop)]
