from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.db.models.functions import Lower


class TipoEntidad(models.Model):
    """Categoría de entidad (Proyecto, Sucursal, Proveedor…). Es un dato, no una clase (D-03).

    El formulario base del tipo se agregará cuando exista el módulo `forms`.
    """

    nombre = models.CharField("nombre", max_length=80)
    nombre_plural = models.CharField("nombre en plural", max_length=80)
    admite_tareas = models.BooleanField("admite tareas y Gantt", default=True)
    es_filtro_contexto = models.BooleanField(
        "sirve de filtro de contexto en el móvil", default=False
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "tipo de entidad"
        verbose_name_plural = "tipos de entidad"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(Lower("nombre"), name="tipoentidad_nombre_unico_ci"),
        ]
        # Permiso global: solo el Admin (D-16, D-19).
        permissions = [("manage_types", "Gestionar tipos de entidad")]

    def __str__(self) -> str:
        return self.nombre


class Entidad(models.Model):
    """Un Proyecto, una Sucursal, un Proveedor… concretos. No se borra: se archiva."""

    class Estado(models.TextChoices):
        ACTIVA = "activa", "Activa"
        ARCHIVADA = "archivada", "Archivada"

    tipo = models.ForeignKey(TipoEntidad, on_delete=models.PROTECT, related_name="entidades")
    nombre = models.CharField("nombre", max_length=120)
    descripcion = models.TextField("descripción", blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVA)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "entidad"
        verbose_name_plural = "entidades"
        ordering = ["tipo__nombre", "nombre"]
        constraints = [
            models.UniqueConstraint(
                Lower("nombre"), "tipo", name="entidad_nombre_unico_por_tipo_ci"
            ),
        ]
        permissions = [
            # Global (Admin)
            ("manage_entities", "Crear y archivar entidades"),
            # Por entidad (se asignan a roles)
            ("edit_entity", "Editar los datos de la entidad"),
            ("view_members", "Ver los miembros de la entidad"),
            ("manage_members", "Gestionar los miembros de la entidad"),
        ]

    def __str__(self) -> str:
        return f"{self.tipo.nombre}: {self.nombre}"

    @property
    def archivada(self) -> bool:
        return self.estado == self.Estado.ARCHIVADA


class Membresia(models.Model):
    """Una persona en una entidad con **un solo rol** (D-19). Quitarla la desactiva."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membresias"
    )
    entidad = models.ForeignKey(Entidad, on_delete=models.CASCADE, related_name="membresias")
    # PROTECT: no se puede borrar un rol que esté en uso.
    rol = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="membresias")
    activa = models.BooleanField(default=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "membresía"
        verbose_name_plural = "membresías"
        ordering = ["entidad", "usuario__username"]
        constraints = [
            models.UniqueConstraint(fields=["usuario", "entidad"], name="membresia_unica"),
        ]

    def __str__(self) -> str:
        return f"{self.usuario} en {self.entidad} como {self.rol.name}"
