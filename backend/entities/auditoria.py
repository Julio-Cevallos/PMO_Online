"""Eventos de auditoría de `entities` (D-21): tipos, entidades y miembros.

Todos son de categoría `entidad`. Los de entidades y miembros llevan la entidad (con ella un
Responsable o un Auditor ve el historial de la suya); los de tipos no pertenecen a ninguna entidad,
así que solo los ve el Admin.
"""

from typing import Any

from audit.models import Categoria
from audit.servicios import cambios_de_alta, diferencias, registrar, valores

CAMPOS_TIPO = ("nombre", "nombre_plural", "admite_tareas", "activo")
CAMPOS_ENTIDAD = ("nombre", "descripcion", "estado")


def _evento(request: Any, accion: str, objeto: Any, **extra: Any):
    return registrar(
        accion=accion, categoria=Categoria.ENTIDAD, request=request, objeto=objeto, **extra
    )


# ---------------------------------------------------------------- tipos


def foto_tipo(tipo: Any) -> dict[str, Any]:
    return valores(tipo, CAMPOS_TIPO)


def tipo_creado(request: Any, tipo: Any) -> None:
    _evento(request, "tipo.crear", tipo, cambios=cambios_de_alta(foto_tipo(tipo)))


def tipo_editado(request: Any, tipo: Any, antes: dict[str, Any]) -> None:
    cambios = diferencias(antes, foto_tipo(tipo))
    if cambios:
        _evento(request, "tipo.editar", tipo, cambios=cambios)


def tipo_eliminado(request: Any, tipo: Any) -> None:
    """Se llama **antes** de borrar (después el objeto pierde su id), dentro de la misma transacción."""
    _evento(request, "tipo.eliminar", tipo, cambios=cambios_de_alta(foto_tipo(tipo)))


# ---------------------------------------------------------------- entidades


def foto_entidad(entidad: Any) -> dict[str, Any]:
    return valores(entidad, CAMPOS_ENTIDAD)


def entidad_creada(request: Any, entidad: Any) -> None:
    datos = {
        "tipo": entidad.tipo.nombre,
        "portafolio": entidad.portafolio.nombre,
        **foto_entidad(entidad),
    }
    _evento(request, "entidad.crear", entidad, entidad=entidad, cambios=cambios_de_alta(datos))


def entidad_editada(request: Any, entidad: Any, antes: dict[str, Any]) -> None:
    """Archivar y reactivar tienen su propia acción; el resto (nombre, descripción) es `editar`."""
    cambios = diferencias(antes, foto_entidad(entidad))
    estado = next((c for c in cambios if c["campo"] == "estado"), None)
    if estado is not None:
        accion = "entidad.archivar" if estado["despues"] == "archivada" else "entidad.reactivar"
        _evento(request, accion, entidad, entidad=entidad, cambios=[estado])
    resto = [c for c in cambios if c["campo"] != "estado"]
    if resto:
        _evento(request, "entidad.editar", entidad, entidad=entidad, cambios=resto)


def entidad_movida(request: Any, entidad: Any, origen: Any) -> None:
    """La entidad pasó de `origen` a su portafolio actual (D-29). El evento queda en el destino."""
    _evento(
        request,
        "entidad.mover",
        entidad,
        entidad=entidad,
        cambios=[
            {"campo": "portafolio", "antes": origen.nombre, "despues": entidad.portafolio.nombre}
        ],
        detalle={"desde": origen.pk, "hacia": entidad.portafolio_id},
    )


# ---------------------------------------------------------------- miembros


def foto_miembro(membresia: Any) -> dict[str, Any]:
    return {"rol": membresia.rol.name, "activa": membresia.activa}


def _miembro(request: Any, accion: str, membresia: Any, cambios: list, detalle: dict | None = None):
    base = {"usuario": membresia.usuario.get_username(), "rol": membresia.rol.name}
    _evento(
        request,
        accion,
        membresia,
        entidad=membresia.entidad,
        cambios=cambios,
        detalle={**base, **(detalle or {})},
    )


def miembro_agregado(request: Any, membresia: Any, *, cuenta_nueva: bool) -> None:
    _miembro(
        request,
        "miembro.agregar",
        membresia,
        cambios_de_alta(foto_miembro(membresia)),
        {"cuenta_nueva": cuenta_nueva},
    )


def miembro_reactivado_al_agregar(request: Any, membresia: Any, antes: dict[str, Any]) -> None:
    """Se vuelve a agregar a quien ya había sido miembro: se reactiva con el rol que se indicó."""
    _miembro(
        request,
        "miembro.reactivar",
        membresia,
        diferencias(antes, foto_miembro(membresia)),
        {"al_agregar": True},
    )


def miembro_editado(request: Any, membresia: Any, antes: dict[str, Any]) -> None:
    """Un evento por tipo de cambio: activar o desactivar, y cambio de rol."""
    cambios = diferencias(antes, foto_miembro(membresia))
    activa = next((c for c in cambios if c["campo"] == "activa"), None)
    if activa is not None:
        accion = "miembro.reactivar" if activa["despues"] else "miembro.desactivar"
        _miembro(request, accion, membresia, [activa])
    rol = next((c for c in cambios if c["campo"] == "rol"), None)
    if rol is not None:
        _miembro(request, "miembro.cambiar_rol", membresia, [rol])


# ---------------------------------------------------------------- invitaciones (D-27)


def _invitacion(request: Any, accion: str, invitacion: Any, cambios: list) -> None:
    _evento(
        request,
        accion,
        invitacion,
        entidad=invitacion.entidad,
        cambios=cambios,
        detalle={"usuario": invitacion.usuario.get_username(), "rol": invitacion.rol.name},
    )


def invitacion_enviada(request: Any, invitacion: Any) -> None:
    _invitacion(
        request,
        "invitacion.enviar",
        invitacion,
        cambios_de_alta({"usuario": invitacion.usuario.get_username(), "rol": invitacion.rol.name}),
    )


def invitacion_respondida(request: Any, invitacion: Any, accion: str) -> None:
    """`accion`: `invitacion.aceptar`, `invitacion.rechazar` o `invitacion.cancelar`."""
    _invitacion(
        request,
        accion,
        invitacion,
        [{"campo": "estado", "antes": "pendiente", "despues": invitacion.estado}],
    )


# ---------------------------------------------------------------- portafolios (D-29)

CAMPOS_PORTAFOLIO = ("nombre", "descripcion")


def foto_portafolio(portafolio: Any) -> dict[str, Any]:
    return valores(portafolio, CAMPOS_PORTAFOLIO)


def portafolio_creado(request: Any, portafolio: Any) -> None:
    datos = {**foto_portafolio(portafolio), "personal": portafolio.personal}
    _evento(
        request,
        "portafolio.crear",
        portafolio,
        portafolio=portafolio,
        cambios=cambios_de_alta(datos),
    )


def portafolio_editado(request: Any, portafolio: Any, antes: dict[str, Any]) -> None:
    cambios = diferencias(antes, foto_portafolio(portafolio))
    if cambios:
        _evento(request, "portafolio.editar", portafolio, portafolio=portafolio, cambios=cambios)


def portafolio_eliminado(request: Any, portafolio: Any) -> None:
    """Se llama **antes** de borrar, dentro de la misma transacción."""
    _evento(
        request,
        "portafolio.eliminar",
        portafolio,
        portafolio=portafolio,
        cambios=cambios_de_alta(foto_portafolio(portafolio)),
    )


def foto_miembro_portafolio(membresia: Any) -> dict[str, Any]:
    return {"rol": membresia.rol.name, "activa": membresia.activa}


def _miembro_portafolio(
    request: Any, accion: str, membresia: Any, cambios: list, detalle: dict | None = None
) -> None:
    base = {"usuario": membresia.usuario.get_username(), "rol": membresia.rol.name}
    _evento(
        request,
        accion,
        membresia,
        portafolio=membresia.portafolio,
        cambios=cambios,
        detalle={**base, **(detalle or {})},
    )


def miembro_portafolio_agregado(request: Any, membresia: Any) -> None:
    _miembro_portafolio(
        request,
        "portafolio.miembro_agregar",
        membresia,
        cambios_de_alta(foto_miembro_portafolio(membresia)),
    )


def miembro_portafolio_reactivado_al_aceptar(
    request: Any, membresia: Any, antes: dict[str, Any]
) -> None:
    _miembro_portafolio(
        request,
        "portafolio.miembro_reactivar",
        membresia,
        diferencias(antes, foto_miembro_portafolio(membresia)),
        {"al_aceptar": True},
    )


def miembro_portafolio_editado(request: Any, membresia: Any, antes: dict[str, Any]) -> None:
    """Un evento por tipo de cambio: activar o desactivar, y cambio de rol."""
    cambios = diferencias(antes, foto_miembro_portafolio(membresia))
    activa = next((c for c in cambios if c["campo"] == "activa"), None)
    if activa is not None:
        accion = (
            "portafolio.miembro_reactivar" if activa["despues"] else "portafolio.miembro_desactivar"
        )
        _miembro_portafolio(request, accion, membresia, [activa])
    rol = next((c for c in cambios if c["campo"] == "rol"), None)
    if rol is not None:
        _miembro_portafolio(request, "portafolio.miembro_cambiar_rol", membresia, [rol])


def invitacion_portafolio_enviada(request: Any, invitacion: Any) -> None:
    _evento(
        request,
        "portafolio.invitacion_enviar",
        invitacion,
        portafolio=invitacion.portafolio,
        cambios=cambios_de_alta(
            {"usuario": invitacion.usuario.get_username(), "rol": invitacion.rol.name}
        ),
        detalle={"usuario": invitacion.usuario.get_username(), "rol": invitacion.rol.name},
    )


def invitacion_portafolio_respondida(request: Any, invitacion: Any, accion: str) -> None:
    """`accion`: `portafolio.invitacion_aceptar`, `_rechazar` o `_cancelar`."""
    _evento(
        request,
        accion,
        invitacion,
        portafolio=invitacion.portafolio,
        cambios=[{"campo": "estado", "antes": "pendiente", "despues": invitacion.estado}],
        detalle={"usuario": invitacion.usuario.get_username(), "rol": invitacion.rol.name},
    )
