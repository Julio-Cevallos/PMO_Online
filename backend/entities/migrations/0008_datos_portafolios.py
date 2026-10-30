"""Datos de portafolios (D-29): permisos, roles y paso de las entidades existentes.

- Siembra los permisos de portafolio y los roles `Gestor del portafolio` y `Coordinador`.
- Cada persona que ya creó entidades recibe su **portafolio personal** («Mis entidades»), donde es
  Gestor, y sus entidades pasan a él. Las que no tienen creador (cuenta borrada) van a un
  portafolio compartido «General» sin miembros: el Admin las sigue viendo y puede reasignarlas.

Es una migración de datos (se ejecuta una vez) para no pisar los ajustes que el Admin haga después.
"""

from django.db import migrations

PERMISOS = [
    ("view_portfolio", "Ver el portafolio y todas sus entidades"),
    ("edit_portfolio", "Editar los datos del portafolio y eliminarlo si está vacío"),
    ("create_portfolio_entities", "Crear entidades en el portafolio"),
    ("edit_portfolio_entities", "Editar los datos de las entidades del portafolio"),
    ("manage_portfolio_entity_members", "Gestionar los miembros de las entidades del portafolio"),
    ("archive_portfolio_entities", "Archivar y reactivar entidades del portafolio"),
    ("move_portfolio_entities", "Mover entidades del portafolio a otro portafolio"),
    ("manage_portfolio_members", "Gestionar los miembros del portafolio"),
    ("view_portfolio_log", "Ver el historial del portafolio y de sus entidades"),
]

# Rol -> (nivel, mínimo para asignar, permisos)
ROLES = {
    "Gestor del portafolio": (40, 41, [codename for codename, _ in PERMISOS]),
    "Coordinador": (
        30,
        31,
        [
            "view_portfolio",
            "create_portfolio_entities",
            "edit_portfolio_entities",
            "manage_portfolio_entity_members",
            "view_portfolio_log",
        ],
    ),
}

GESTOR = "Gestor del portafolio"


def sembrar(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    PerfilRol = apps.get_model("accounts", "PerfilRol")
    Entidad = apps.get_model("entities", "Entidad")
    Portafolio = apps.get_model("entities", "Portafolio")
    MembresiaPortafolio = apps.get_model("entities", "MembresiaPortafolio")
    User = apps.get_model("accounts", "User")

    contenido, _ = ContentType.objects.get_or_create(app_label="entities", model="portafolio")
    permisos = {}
    for codename, nombre in PERMISOS:
        permisos[codename], _ = Permission.objects.get_or_create(
            content_type=contenido, codename=codename, defaults={"name": nombre}
        )

    grupos = {}
    for nombre, (nivel, minimo, codenames) in ROLES.items():
        grupo, _ = Group.objects.get_or_create(name=nombre)
        PerfilRol.objects.get_or_create(
            grupo=grupo,
            defaults={"nivel": nivel, "nivel_minimo_para_asignar": minimo, "ambito": "portafolio"},
        )
        grupo.permissions.add(*[permisos[c] for c in codenames])
        grupos[nombre] = grupo

    # Entidades que ya existen: cada creador tiene su portafolio personal.
    creadores = (
        Entidad.objects.filter(portafolio__isnull=True, creado_por__isnull=False)
        .values_list("creado_por_id", flat=True)
        .distinct()
    )
    for usuario_id in creadores:
        usuario = User.objects.get(pk=usuario_id)
        portafolio = Portafolio.objects.create(
            nombre="Mis entidades", personal=True, creado_por=usuario
        )
        MembresiaPortafolio.objects.create(
            usuario=usuario, portafolio=portafolio, rol=grupos[GESTOR], creado_por=usuario
        )
        Entidad.objects.filter(portafolio__isnull=True, creado_por_id=usuario_id).update(
            portafolio=portafolio
        )

    if Entidad.objects.filter(portafolio__isnull=True).exists():
        general, _ = Portafolio.objects.get_or_create(
            nombre="General",
            personal=False,
            defaults={"descripcion": "Entidades sin responsable asignado."},
        )
        Entidad.objects.filter(portafolio__isnull=True).update(portafolio=general)


class Migration(migrations.Migration):
    dependencies = [
        ("entities", "0007_portafolios"),
        ("accounts", "0007_perfilrol_ambito"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(sembrar, migrations.RunPython.noop)]
