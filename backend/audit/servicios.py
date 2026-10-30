"""Cómo se registran los eventos (D-21).

Se llama explícitamente desde los servicios, dentro de la misma transacción que el cambio, para
que no exista un cambio sin su registro. No se usan señales automáticas: no conocen al usuario
que hizo la petición ni su IP.

Este módulo no importa nada de `accounts` ni de `entities` (evita ciclos y mantiene `audit`
independiente).
"""

import ipaddress
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.conf import settings

from .models import Categoria, EventoAuditoria

# Campos cuyo valor nunca se guarda (solo se deja constancia de que cambiaron).
CAMPOS_SENSIBLES = frozenset(
    {"password", "new_password", "old_password", "token", "access", "refresh"}
)
OCULTO = "[oculto]"
_MAX_TEXTO = 2000


def _jsonable(valor: Any) -> Any:
    """Convierte un valor a algo que se pueda guardar como JSON."""
    if valor is None or isinstance(valor, bool | int | float):
        return valor
    if isinstance(valor, str):
        return valor[:_MAX_TEXTO]
    if isinstance(valor, datetime | date):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, set | frozenset):
        return sorted(_jsonable(v) for v in valor)
    if isinstance(valor, list | tuple):
        return [_jsonable(v) for v in valor]
    if isinstance(valor, dict):
        return {str(k): _jsonable(v) for k, v in valor.items()}
    return str(valor)[:_MAX_TEXTO]


def valores(instancia: Any, campos: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """Foto de los campos de un objeto. Se toma antes de cambiarlo, para poder compararlo."""
    return {campo: _jsonable(getattr(instancia, campo)) for campo in campos}


def _cambio(campo: str, antes: Any, despues: Any) -> dict[str, Any]:
    if campo in CAMPOS_SENSIBLES:
        return {"campo": campo, "antes": OCULTO, "despues": OCULTO}
    return {"campo": campo, "antes": antes, "despues": despues}


def diferencias(antes: dict[str, Any], despues: dict[str, Any]) -> list[dict[str, Any]]:
    """Lista de los campos que cambiaron, con su valor antes y después."""
    campos = list(dict.fromkeys([*antes, *despues]))
    return [
        _cambio(c, _jsonable(antes.get(c)), _jsonable(despues.get(c)))
        for c in campos
        if _jsonable(antes.get(c)) != _jsonable(despues.get(c))
    ]


def cambios_de_alta(despues: dict[str, Any]) -> list[dict[str, Any]]:
    """Cambios de un objeto recién creado: todos sus campos pasan de vacío a su valor."""
    return [_cambio(c, None, _jsonable(v)) for c, v in despues.items()]


def ip_de(request: Any) -> str | None:
    """IP de quien hizo la petición. Solo se confía en `X-Forwarded-For` si se configuró un
    proxy de confianza (`AUDIT_TRUST_PROXY`); si no, cualquiera podría falsearla. Si esa
    cabecera trae algo que no es una IP, se usa la dirección de la conexión."""
    if request is None:
        return None
    meta = getattr(request, "META", {})
    candidatas = []
    if getattr(settings, "AUDIT_TRUST_PROXY", False):
        candidatas.append(meta.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip())
    candidatas.append(meta.get("REMOTE_ADDR", ""))
    for candidata in candidatas:
        try:
            return str(ipaddress.ip_address(candidata))
        except ValueError:
            continue
    return None


def _usuario(request: Any, usuario: Any) -> Any:
    if usuario is not None:
        return usuario
    actual = getattr(request, "user", None)
    return actual if actual is not None and actual.is_authenticated else None


def registrar(
    *,
    accion: str,
    categoria: str,
    request: Any = None,
    usuario: Any = None,
    objeto: Any = None,
    entidad: Any = None,
    portafolio: Any = None,
    cambios: list[dict[str, Any]] | None = None,
    detalle: dict[str, Any] | None = None,
) -> EventoAuditoria:
    """Registra un evento.

    - `usuario`: quien lo hizo; por defecto, el de la petición. Se guarda su id y su nombre de
      usuario del momento.
    - `objeto`: lo afectado (cualquier modelo). `entidad`: la entidad a la que pertenece el evento,
      si la hay (con ella un Responsable o un Auditor ve el evento). `portafolio`: el portafolio
      del evento; si no se indica y la entidad tiene uno, se usa el de la entidad (D-29).
    - `cambios`: usar `diferencias` o `cambios_de_alta`.
    """
    if categoria not in Categoria.values:
        raise ValueError(f"Categoría inválida: {categoria!r}")
    quien = _usuario(request, usuario)
    campos: dict[str, Any] = {}
    if objeto is not None:
        meta = objeto._meta
        campos.update(
            objeto_tipo=f"{meta.app_label}.{meta.model_name}",
            objeto_id=str(objeto.pk),
            objeto_nombre=str(objeto)[:150],
        )
    if entidad is not None:
        campos.update(
            entidad_id=entidad.pk, entidad_nombre=str(getattr(entidad, "nombre", ""))[:120]
        )
    if portafolio is None and entidad is not None and getattr(entidad, "portafolio_id", None):
        portafolio = entidad.portafolio
    if portafolio is not None:
        campos.update(portafolio_id=portafolio.pk, portafolio_nombre=str(portafolio.nombre)[:120])
    return EventoAuditoria.objects.create(
        categoria=categoria,
        accion=accion,
        usuario_id=quien.pk if quien else None,
        usuario_nombre=quien.get_username()[:150] if quien else "",
        ip=ip_de(request),
        cambios=_jsonable(cambios or []),
        detalle=_jsonable(detalle or {}),
        **campos,
    )
