"""Quién ve qué del historial (D-21).

| Quién                                   | Qué ve                                                           |
|-----------------------------------------|------------------------------------------------------------------|
| Superusuario                            | Todo.                                                            |
| `audit.view_system_log` (rol Admin)     | Categorías `sistema` y `entidad`: la administración, **sin**     |
|                                         | el contenido de las entidades.                                   |
| Gestor o Coordinador de un portafolio   | Categoría `entidad` del portafolio y de sus entidades (sin       |
| (`entities.view_portfolio_log`)         | contenido).                                                      |
| `audit.view_entity_log` (Responsable y  | Eventos de sus entidades (miembro activo con ese permiso), de    |
| Auditor), por entidad                   | las categorías `entidad` y `contenido`.                          |
"""

from django.db.models import Q, QuerySet
from rest_framework.permissions import BasePermission

from entities.permisos import entidades_con_permiso, entidades_de_mis_portafolios
from entities.portafolios import PERMISO_VER_HISTORIAL, portafolios_con_permiso

from .models import Categoria, EventoAuditoria

PERMISO_SISTEMA = "audit.view_system_log"
PERMISO_ENTIDAD = "audit.view_entity_log"


def eventos_visibles(user) -> QuerySet[EventoAuditoria]:
    eventos = EventoAuditoria.objects.all()
    if user.is_superuser:
        return eventos
    condicion = Q()
    if user.has_perm(PERMISO_SISTEMA):
        condicion |= Q(categoria__in=[Categoria.SISTEMA, Categoria.ENTIDAD])
    entidades = list(entidades_con_permiso(user, PERMISO_ENTIDAD))
    if entidades:
        condicion |= Q(
            categoria__in=[Categoria.ENTIDAD, Categoria.CONTENIDO], entidad_id__in=entidades
        )
    # Quien gestiona un portafolio (Gestor, Coordinador): la administración del portafolio y de
    # sus entidades, sin el contenido (como el Admin).
    portafolios = portafolios_con_permiso(user, PERMISO_VER_HISTORIAL)
    if portafolios:
        entidades_del_portafolio = list(entidades_de_mis_portafolios(user, PERMISO_VER_HISTORIAL))
        condicion |= Q(categoria=Categoria.ENTIDAD, portafolio_id__in=portafolios)
        if entidades_del_portafolio:
            condicion |= Q(categoria=Categoria.ENTIDAD, entidad_id__in=entidades_del_portafolio)
    return eventos.filter(condicion) if condicion else eventos.none()


def puede_ver_auditoria(user) -> bool:
    if not (user and user.is_authenticated):
        return False
    return (
        user.is_superuser
        or user.has_perm(PERMISO_SISTEMA)
        or entidades_con_permiso(user, PERMISO_ENTIDAD).exists()
        or bool(portafolios_con_permiso(user, PERMISO_VER_HISTORIAL))
    )


class PuedeVerAuditoria(BasePermission):
    message = "No tienes permiso para ver el historial."

    def has_permission(self, request, view) -> bool:
        return puede_ver_auditoria(request.user)
