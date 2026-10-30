from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import QuerySet
from django.http import HttpRequest

from . import auditoria
from .models import User


@admin.register(User)
class AccountsUserAdmin(UserAdmin):
    list_display = (*UserAdmin.list_display, "failed_attempts", "locked_until")
    fieldsets = (
        *UserAdmin.fieldsets,
        ("Bloqueo de inicio de sesión", {"fields": ("failed_attempts", "locked_until")}),
    )
    actions = ("desbloquear",)

    def has_module_permission(self, request: HttpRequest) -> bool:
        # /admin/ es solo para superusuarios (desarrolladores), D-16.
        return request.user.is_superuser

    @admin.action(description="Desbloquear cuentas seleccionadas")
    def desbloquear(self, request: HttpRequest, queryset: QuerySet[User]) -> None:
        for user in queryset:
            user.unlock()
            auditoria.cuenta_desbloqueada(request, user)
        self.message_user(request, f"{queryset.count()} cuenta(s) desbloqueada(s).")
