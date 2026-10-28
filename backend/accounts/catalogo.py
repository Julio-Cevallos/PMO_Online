"""Catálogo de permisos asignables a roles (D-16).

Cada permiso declara su ámbito:
- `global`: solo lo tiene el rol Admin (o un superusuario); nunca se asigna a roles por entidad.
- `entidad`: se cumple dentro de una entidad si el rol de la membresía lo incluye.

Cada módulo registra los suyos al construirse (en `AppConfig.ready`), por ejemplo:

    registrar_permiso("planning.edit_task", "Editar tareas", AMBITO_ENTIDAD)

El permiso debe existir además como `Meta.permissions` del modelo correspondiente para que
Django cree su fila en la base de datos.
"""

from dataclasses import dataclass

from .roles import PERMISOS_GLOBALES

AMBITO_GLOBAL = "global"
AMBITO_ENTIDAD = "entidad"
_AMBITOS = (AMBITO_GLOBAL, AMBITO_ENTIDAD)


@dataclass(frozen=True)
class PermisoDef:
    codename: str  # con la app: "planning.edit_task"
    nombre: str
    ambito: str


_REGISTRO: dict[str, PermisoDef] = {}


def registrar_permiso(codename: str, nombre: str, ambito: str) -> None:
    if ambito not in _AMBITOS:
        raise ValueError(f"Ámbito inválido: {ambito!r}")
    if "." not in codename:
        raise ValueError("El permiso debe incluir la app: 'app.codename'.")
    nuevo = PermisoDef(codename, nombre, ambito)
    existente = _REGISTRO.get(codename)
    if existente is not None and existente != nuevo:
        raise ValueError(f"El permiso {codename!r} ya está registrado con otros datos.")
    _REGISTRO[codename] = nuevo


def permisos_registrados() -> list[PermisoDef]:
    return sorted(_REGISTRO.values(), key=lambda p: p.codename)


def obtener_permiso(codename: str) -> PermisoDef | None:
    return _REGISTRO.get(codename)


# Permisos globales de `accounts`.
for _codename, _nombre in PERMISOS_GLOBALES.items():
    registrar_permiso(f"accounts.{_codename}", _nombre, AMBITO_GLOBAL)
