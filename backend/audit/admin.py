from django.contrib import admin
from django.http import HttpRequest

from .models import EventoAuditoria


@admin.register(EventoAuditoria)
class EventoAuditoriaAdmin(admin.ModelAdmin):
    """Solo lectura, incluso para el superusuario: el historial no se altera (D-21)."""

    list_display = ("ocurrido_en", "categoria", "accion", "usuario_nombre", "objeto_nombre", "ip")
    list_filter = ("categoria",)
    search_fields = ("accion", "usuario_nombre", "objeto_nombre")
    date_hierarchy = "ocurrido_en"

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        return request.user.is_superuser

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False
