from django.apps import AppConfig


class EntitiesConfig(AppConfig):
    name = "entities"

    def ready(self) -> None:
        from accounts.catalogo import (
            AMBITO_ENTIDAD,
            AMBITO_GLOBAL,
            AMBITO_PORTAFOLIO,
            registrar_permiso,
        )

        # Globales: el Admin (o un superusuario); `create_entity` también lo tiene el Moderador.
        registrar_permiso("entities.manage_types", "Gestionar tipos de entidad", AMBITO_GLOBAL)
        registrar_permiso("entities.manage_entities", "Crear y archivar entidades", AMBITO_GLOBAL)
        registrar_permiso(
            "entities.create_entity",
            "Crear portafolios y entidades por su cuenta (Moderador)",
            AMBITO_GLOBAL,
        )
        # Por entidad: se asignan a roles.
        registrar_permiso("entities.edit_entity", "Editar los datos de la entidad", AMBITO_ENTIDAD)
        registrar_permiso("entities.view_members", "Ver los miembros de la entidad", AMBITO_ENTIDAD)
        registrar_permiso(
            "entities.manage_members", "Gestionar los miembros de la entidad", AMBITO_ENTIDAD
        )
        # Por portafolio (D-29): se asignan a roles de portafolio (Gestor, Coordinador…).
        for codename, nombre in (
            ("view_portfolio", "Ver el portafolio y todas sus entidades"),
            ("edit_portfolio", "Editar los datos del portafolio y eliminarlo si está vacío"),
            ("create_portfolio_entities", "Crear entidades en el portafolio"),
            ("edit_portfolio_entities", "Editar los datos de las entidades del portafolio"),
            (
                "manage_portfolio_entity_members",
                "Gestionar los miembros de las entidades del portafolio",
            ),
            ("archive_portfolio_entities", "Archivar y reactivar entidades del portafolio"),
            ("move_portfolio_entities", "Mover entidades del portafolio a otro portafolio"),
            ("manage_portfolio_members", "Gestionar los miembros del portafolio"),
            ("view_portfolio_log", "Ver el historial del portafolio y de sus entidades"),
        ):
            registrar_permiso(f"entities.{codename}", nombre, AMBITO_PORTAFOLIO)
