from django.apps import AppConfig


class AuditConfig(AppConfig):
    name = "audit"
    verbose_name = "Auditoría"

    def ready(self) -> None:
        from accounts.catalogo import AMBITO_ENTIDAD, AMBITO_GLOBAL, registrar_permiso

        registrar_permiso(
            "audit.view_system_log", "Ver el historial de administración", AMBITO_GLOBAL
        )
        registrar_permiso("audit.view_entity_log", "Ver el historial de la entidad", AMBITO_ENTIDAD)
