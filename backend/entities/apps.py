from django.apps import AppConfig


class EntitiesConfig(AppConfig):
    name = "entities"

    def ready(self) -> None:
        from accounts.catalogo import AMBITO_ENTIDAD, AMBITO_GLOBAL, registrar_permiso

        # Globales: solo el Admin (o un superusuario).
        registrar_permiso("entities.manage_types", "Gestionar tipos de entidad", AMBITO_GLOBAL)
        registrar_permiso("entities.manage_entities", "Crear y archivar entidades", AMBITO_GLOBAL)
        # Por entidad: se asignan a roles.
        registrar_permiso("entities.edit_entity", "Editar los datos de la entidad", AMBITO_ENTIDAD)
        registrar_permiso("entities.view_members", "Ver los miembros de la entidad", AMBITO_ENTIDAD)
        registrar_permiso(
            "entities.manage_members", "Gestionar los miembros de la entidad", AMBITO_ENTIDAD
        )
