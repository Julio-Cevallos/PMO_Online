"""Rol global Moderador (D-28): crea entidades y es dueño de las suyas.

Siembra el permiso `entities.create_entity` y el rol `Moderador`; el Admin también recibe el permiso
(puede crear entidades). Es una migración de datos para no pisar ajustes posteriores.
"""

from django.db import migrations

PERMISO = ("create_entity", "Crear entidades propias (Moderador)")
ROLES = ("Admin", "Moderador")


def sembrar(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    contenido, _ = ContentType.objects.get_or_create(app_label="entities", model="entidad")
    permiso, _ = Permission.objects.get_or_create(
        content_type=contenido, codename=PERMISO[0], defaults={"name": PERMISO[1]}
    )
    for rol in ROLES:
        grupo, _ = Group.objects.get_or_create(name=rol)
        grupo.permissions.add(permiso)


class Migration(migrations.Migration):
    dependencies = [
        ("entities", "0005_permiso_crear_entidad"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(sembrar, migrations.RunPython.noop)]
