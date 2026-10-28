from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    name = "accounts"

    def ready(self) -> None:
        from . import catalogo  # noqa: F401  (registra los permisos de accounts)
        from .roles import sincronizar_roles_del_sistema

        # Después de migrar (y de que Django cree los permisos) se aseguran los roles del sistema.
        post_migrate.connect(sincronizar_roles_del_sistema, sender=self)
