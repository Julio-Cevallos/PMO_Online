"""Eventos de auditoría de `accounts` (D-21): usuarios, sesiones, bloqueos y roles.

Todos son de categoría `sistema`: los ve el Admin (y el superusuario), no quienes solo son miembros de
una entidad. Las contraseñas nunca se guardan: solo queda constancia de que cambiaron.
"""

from typing import Any

from audit.models import Categoria
from audit.servicios import cambios_de_alta, diferencias, registrar, valores

CAMPOS_USUARIO = ("username", "email", "first_name", "last_name", "is_active")


def _evento(request: Any, accion: str, objeto: Any, **extra: Any):
    return registrar(
        accion=accion, categoria=Categoria.SISTEMA, request=request, objeto=objeto, **extra
    )


# ---------------------------------------------------------------- usuarios y sesiones


def foto_usuario(user: Any) -> dict[str, Any]:
    """Los datos de una cuenta que se auditan (sin contraseña), para comparar antes y después."""
    return {
        **valores(user, CAMPOS_USUARIO),
        "is_admin": user.is_admin,
        "is_moderator": user.is_moderator,
    }


def inicio_sesion(request: Any, user: Any) -> None:
    _evento(request, "usuario.iniciar_sesion", user, usuario=user)


def cuenta_bloqueada(request: Any, user: Any) -> None:
    detalle = {"intentos": user.failed_attempts, "bloqueado_hasta": user.locked_until}
    _evento(request, "usuario.bloquear", user, usuario=user, detalle=detalle)


def cuenta_desbloqueada(request: Any, user: Any) -> None:
    """La desbloquea otra persona (un Admin o un superusuario): ella es quien queda como autora."""
    _evento(request, "usuario.desbloquear", user)


def clave_cambiada(request: Any, user: Any) -> None:
    _evento(
        request,
        "usuario.cambiar_clave",
        user,
        usuario=user,
        cambios=cambios_de_alta({"password": "(no se guarda)"}),
    )


def usuario_registrado(request: Any, user: Any) -> None:
    """Alta por el registro público: no hay sesión, así que la propia cuenta es la autora."""
    _evento(
        request,
        "usuario.registrar",
        user,
        usuario=user,
        cambios=cambios_de_alta(foto_usuario(user)),
    )


def usuario_creado(request: Any, user: Any, *, desde_entidad: Any = None) -> None:
    """Alta por un Admin o desde una entidad. Si nace con el rol Admin, también queda ese evento."""
    detalle = {"entidad": desde_entidad.pk} if desde_entidad is not None else {}
    _evento(
        request,
        "usuario.crear",
        user,
        cambios=cambios_de_alta(foto_usuario(user)),
        detalle=detalle,
    )
    if user.is_admin:
        _evento(
            request,
            "usuario.dar_admin",
            user,
            cambios=[{"campo": "is_admin", "antes": False, "despues": True}],
        )
    if user.is_moderator:
        _evento(
            request,
            "usuario.dar_moderador",
            user,
            cambios=[{"campo": "is_moderator", "antes": False, "despues": True}],
        )


def usuario_editado(request: Any, user: Any, antes: dict[str, Any]) -> None:
    """Un evento por cada tipo de cambio: rol Admin, activar o desactivar, y el resto de los datos."""
    cambios = diferencias(antes, foto_usuario(user))
    por_campo = {c["campo"]: c for c in cambios}
    if "is_admin" in por_campo:
        accion = "usuario.dar_admin" if por_campo["is_admin"]["despues"] else "usuario.quitar_admin"
        _evento(request, accion, user, cambios=[por_campo["is_admin"]])
    if "is_moderator" in por_campo:
        accion = (
            "usuario.dar_moderador"
            if por_campo["is_moderator"]["despues"]
            else "usuario.quitar_moderador"
        )
        _evento(request, accion, user, cambios=[por_campo["is_moderator"]])
    if "is_active" in por_campo:
        accion = "usuario.reactivar" if por_campo["is_active"]["despues"] else "usuario.desactivar"
        _evento(request, accion, user, cambios=[por_campo["is_active"]])
    resto = [c for c in cambios if c["campo"] not in ("is_admin", "is_moderator", "is_active")]
    if resto:
        _evento(request, "usuario.editar", user, cambios=resto)


def perfil_editado(request: Any, user: Any, antes: dict[str, Any]) -> None:
    """Una persona edita su propio perfil."""
    cambios = diferencias(antes, foto_usuario(user))
    if cambios:
        _evento(request, "usuario.editar_perfil", user, usuario=user, cambios=cambios)


# ---------------------------------------------------------------- roles


def foto_rol(grupo: Any) -> dict[str, Any]:
    perfil = getattr(grupo, "perfil", None)
    return {
        "nombre": grupo.name,
        "nivel": perfil.nivel if perfil else None,
        "nivel_minimo_para_asignar": perfil.nivel_minimo_para_asignar if perfil else None,
        "permisos": sorted(
            f"{p.content_type.app_label}.{p.codename}" for p in grupo.permissions.all()
        ),
    }


def rol_creado(request: Any, grupo: Any) -> None:
    _evento(request, "rol.crear", grupo, cambios=cambios_de_alta(foto_rol(grupo)))


def rol_editado(request: Any, grupo: Any, antes: dict[str, Any]) -> None:
    cambios = diferencias(antes, foto_rol(grupo))
    if cambios:
        _evento(request, "rol.editar", grupo, cambios=cambios)


def rol_eliminado(request: Any, grupo: Any) -> None:
    """Se llama **antes** de borrar (después el objeto pierde su id), dentro de la misma transacción."""
    _evento(request, "rol.eliminar", grupo, cambios=cambios_de_alta(foto_rol(grupo)))
