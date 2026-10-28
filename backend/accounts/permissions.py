from rest_framework.permissions import BasePermission


def requiere_permiso(permiso: str) -> type[BasePermission]:
    """Clase de permiso DRF: exige sesión y que el usuario tenga `permiso` (ej. 'accounts.manage_users').

    `has_perm` ya devuelve True para un superusuario y considera los permisos de sus roles
    (equivale a una política `[Authorize(Policy = ...)]` de ASP.NET).
    """

    class Permiso(BasePermission):
        message = "No tienes permiso para realizar esta acción."

        def has_permission(self, request, view) -> bool:
            user = request.user
            return bool(user and user.is_authenticated and user.has_perm(permiso))

    Permiso.__name__ = f"Requiere_{permiso.replace('.', '_')}"
    return Permiso
