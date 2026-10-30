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
    # Dueño de la entidad (D-29): quien tenga un rol en el portafolio la gestiona según ese rol.
    portafolio = models.ForeignKey("Portafolio", on_delete=models.PROTECT, related_name="entidades")
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
            ("create_entity", "Crear entidades propias (Moderador)"),
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


class Invitacion(models.Model):
    """Invitación a unirse a una entidad con un rol (D-27).

    Agregar una cuenta que ya existe no la mete directo: se le invita y ella acepta o rechaza.
    Al aceptar se crea (o reactiva) su `Membresia` con el rol de la invitación. Las respondidas o
    canceladas se conservan como historial.
    """

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ACEPTADA = "aceptada", "Aceptada"
        RECHAZADA = "rechazada", "Rechazada"
        CANCELADA = "cancelada", "Cancelada"

    entidad = models.ForeignKey(Entidad, on_delete=models.CASCADE, related_name="invitaciones")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="invitaciones"
    )
    # PROTECT: no se puede borrar un rol que esté en una invitación.
    rol = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="+")
    invitado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    creado_en = models.DateTimeField(auto_now_add=True)
    respondido_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "invitación"
        verbose_name_plural = "invitaciones"
        ordering = ["-creado_en", "-id"]
        constraints = [
            # Una sola invitación pendiente por persona y entidad.
            models.UniqueConstraint(
                fields=["usuario", "entidad"],
                condition=models.Q(estado="pendiente"),
                name="invitacion_pendiente_unica",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.usuario} a {self.entidad} como {self.rol.name}"

    @property
    def pendiente(self) -> bool:
        return self.estado == self.Estado.PENDIENTE


class Portafolio(models.Model):
    """Grupo de entidades que varias personas gestionan en conjunto (D-29).

    Es el dueño de sus entidades: quien tenga un rol en él (Gestor, Coordinador…) las gestiona según
    los permisos de ese rol. Cada persona con permiso de crear entidades tiene un portafolio
    **personal** (`personal=True`, «Mis entidades») donde caen las que crea sin elegir otro.
    """

    nombre = models.CharField("nombre", max_length=120)
    descripcion = models.TextField("descripción", blank=True)
    personal = models.BooleanField(default=False)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "portafolio"
        verbose_name_plural = "portafolios"
        ordering = ["-personal", "nombre"]
        default_permissions = ()
        constraints = [
            # Los portafolios compartidos no repiten nombre; los personales sí («Mis entidades»).
            models.UniqueConstraint(
                Lower("nombre"),
                condition=models.Q(personal=False),
                name="portafolio_nombre_unico_ci",
            ),
        ]
        permissions = [
            # Por portafolio (se asignan a roles de portafolio; ver `portafolios.py`)
            ("view_portfolio", "Ver el portafolio y todas sus entidades"),
            ("edit_portfolio", "Editar los datos del portafolio y eliminarlo si está vacío"),
            ("create_portfolio_entities", "Crear entidades en el portafolio"),
            ("edit_portfolio_entities", "Editar los datos de las entidades del portafolio"),
            (
                "manage_portfolio_entity_members",
                "Gestionar los miembros de las entidades del portafolio",
            ),
            ("archive_portfolio_entities", "Archivar y reactivar entidades del portafolio"),
            ("move_portfolio_entities", "Mover entidades del portafolio a otro portafolio"),
            ("manage_portfolio_members", "Gestionar los miembros del portafolio"),
            ("view_portfolio_log", "Ver el historial del portafolio y de sus entidades"),
        ]

    def __str__(self) -> str:
        return self.nombre


class MembresiaPortafolio(models.Model):
    """Una persona en un portafolio con **un solo rol** de portafolio. Quitarla la desactiva."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membresias_portafolio"
    )
    portafolio = models.ForeignKey(Portafolio, on_delete=models.CASCADE, related_name="membresias")
    # PROTECT: no se puede borrar un rol que esté en uso.
    rol = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="membresias_portafolio")
    activa = models.BooleanField(default=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "membresía de portafolio"
        verbose_name_plural = "membresías de portafolio"
        ordering = ["portafolio", "usuario__username"]
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "portafolio"], name="membresia_portafolio_unica"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.usuario} en {self.portafolio} como {self.rol.name}"


class InvitacionPortafolio(models.Model):
    """Invitación a unirse a un portafolio con un rol (D-29, flujo de D-27).

    Al aceptar se crea (o reactiva) la `MembresiaPortafolio`. Las respondidas o canceladas se
    conservan como historial.
    """

    Estado = Invitacion.Estado

    portafolio = models.ForeignKey(
        Portafolio, on_delete=models.CASCADE, related_name="invitaciones"
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="invitaciones_portafolio"
    )
    rol = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="+")
    invitado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    creado_en = models.DateTimeField(auto_now_add=True)
    respondido_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "invitación a portafolio"
        verbose_name_plural = "invitaciones a portafolio"
        ordering = ["-creado_en", "-id"]
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "portafolio"],
                condition=models.Q(estado="pendiente"),
                name="invitacion_portafolio_pendiente_unica",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.usuario} a {self.portafolio} como {self.rol.name}"

    @property
    def pendiente(self) -> bool:
        return self.estado == self.Estado.PENDIENTE
