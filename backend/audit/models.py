from django.db import models
from django.utils import timezone


class RegistroInmutableError(Exception):
    """Se intentó modificar o borrar un evento de auditoría, que es de solo inserción."""


class Categoria(models.TextChoices):
    """Reparte la visibilidad del historial (D-21)."""

    SISTEMA = "sistema", "Sistema"  # usuarios, roles, inicios de sesión y bloqueos
    ENTIDAD = "entidad", "Entidad"  # tipos, entidades y miembros
    CONTENIDO = "contenido", "Contenido"  # formularios y tareas (llegarán después)


class EventoQuerySet(models.QuerySet):
    """Impide actualizar o borrar en bloque: el historial solo se inserta."""

    def update(self, **kwargs):
        raise RegistroInmutableError("El registro de auditoría es de solo inserción.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise RegistroInmutableError("El registro de auditoría es de solo inserción.")

    def delete(self):
        raise RegistroInmutableError("El registro de auditoría es de solo inserción.")


class EventoAuditoria(models.Model):
    """Un hecho que quedó registrado: quién, cuándo, desde dónde, qué y qué cambió (D-21).

    No tiene llaves foráneas a propósito: guarda ids y el nombre del momento, así borrar o
    renombrar un usuario o una entidad nunca altera el historial. Además de lo que rechaza este
    modelo, un trigger de PostgreSQL (migración 0002) bloquea `UPDATE` y `DELETE`.
    """

    ocurrido_en = models.DateTimeField(default=timezone.now, db_index=True)
    categoria = models.CharField(max_length=10, choices=Categoria.choices, db_index=True)
    # Código con puntos: "usuario.bloquear", "miembro.cambiar_rol"…
    accion = models.CharField(max_length=60, db_index=True)

    usuario_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    usuario_nombre = models.CharField(max_length=150, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    entidad_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    entidad_nombre = models.CharField(max_length=120, blank=True)

    # Portafolio al que pertenece el evento (D-29): con él quienes gestionan el portafolio lo ven.
    portafolio_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    portafolio_nombre = models.CharField(max_length=120, blank=True)

    objeto_tipo = models.CharField(max_length=60, blank=True)
    objeto_id = models.CharField(max_length=64, blank=True)
    objeto_nombre = models.CharField(max_length=150, blank=True)

    # Lista de {"campo", "antes", "despues"}. Las contraseñas y tokens nunca se guardan.
    cambios = models.JSONField(default=list, blank=True)
    detalle = models.JSONField(default=dict, blank=True)

    objects = EventoQuerySet.as_manager()

    class Meta:
        verbose_name = "evento de auditoría"
        verbose_name_plural = "eventos de auditoría"
        ordering = ["-ocurrido_en", "-id"]
        default_permissions = ()  # nadie agrega, cambia ni borra: solo se consulta
        permissions = [
            # Global (Admin): administración del sistema y de las entidades, sin su contenido.
            ("view_system_log", "Ver el historial de administración"),
            # Por entidad (Responsable y Auditor): el historial de sus entidades.
            ("view_entity_log", "Ver el historial de la entidad"),
        ]
        indexes = [
            models.Index(fields=["objeto_tipo", "objeto_id"], name="audit_objeto_idx"),
            models.Index(fields=["entidad_id", "ocurrido_en"], name="audit_entidad_fecha_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.ocurrido_en:%Y-%m-%d %H:%M:%S} {self.accion} ({self.usuario_nombre or 'sistema'})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RegistroInmutableError("Un evento de auditoría no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RegistroInmutableError("Un evento de auditoría no se puede borrar.")
