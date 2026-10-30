from django.contrib import admin
from django.contrib.auth.models import Group
from django.db import DatabaseError, connection, transaction
from django.test import RequestFactory, TestCase

from accounts.catalogo import AMBITO_ENTIDAD, AMBITO_GLOBAL, obtener_permiso
from entities.utiles_pruebas import AUDITOR, COLABORADOR, PLANIFICADOR, RESPONSABLE, usuario

from .admin import EventoAuditoriaAdmin
from .models import Categoria, EventoAuditoria, RegistroInmutableError


def crear_evento(**extra) -> EventoAuditoria:
    datos = {"categoria": Categoria.SISTEMA, "accion": "usuario.crear", "usuario_nombre": "ana"}
    return EventoAuditoria.objects.create(**{**datos, **extra})


class SoloInsercionEnLaAplicacionTests(TestCase):
    def test_se_puede_insertar(self) -> None:
        evento = crear_evento(cambios=[{"campo": "email", "antes": None, "despues": "a@b.c"}])
        evento.refresh_from_db()
        self.assertEqual(evento.cambios[0]["despues"], "a@b.c")

    def test_guardar_un_evento_existente_se_rechaza(self) -> None:
        evento = crear_evento()
        evento.accion = "usuario.otra"
        with self.assertRaises(RegistroInmutableError):
            evento.save()
        evento.refresh_from_db()
        self.assertEqual(evento.accion, "usuario.crear")

    def test_borrar_un_evento_se_rechaza(self) -> None:
        evento = crear_evento()
        with self.assertRaises(RegistroInmutableError):
            evento.delete()
        self.assertTrue(EventoAuditoria.objects.filter(pk=evento.pk).exists())

    def test_las_operaciones_en_bloque_se_rechazan(self) -> None:
        evento = crear_evento()
        with self.assertRaises(RegistroInmutableError):
            EventoAuditoria.objects.all().update(accion="x")
        with self.assertRaises(RegistroInmutableError):
            EventoAuditoria.objects.all().delete()
        evento.accion = "x"
        with self.assertRaises(RegistroInmutableError):
            EventoAuditoria.objects.bulk_update([evento], ["accion"])
        self.assertEqual(EventoAuditoria.objects.get(pk=evento.pk).accion, "usuario.crear")

    def test_se_puede_insertar_en_bloque(self) -> None:
        EventoAuditoria.objects.bulk_create([EventoAuditoria(categoria="sistema", accion="a.b")])
        self.assertTrue(EventoAuditoria.objects.filter(accion="a.b").exists())


class TriggerDeLaBaseDeDatosTests(TestCase):
    """Aunque se salte la aplicación (SQL directo), PostgreSQL rechaza cambiar o borrar."""

    def sql(self, consulta: str, *params) -> None:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(consulta, params)

    def test_el_trigger_rechaza_update(self) -> None:
        evento = crear_evento()
        with self.assertRaises(DatabaseError) as contexto:
            self.sql(
                "UPDATE audit_eventoauditoria SET accion = 'hackeada' WHERE id = %s", evento.pk
            )
        self.assertIn("solo inserción", str(contexto.exception))
        self.assertEqual(EventoAuditoria.objects.get(pk=evento.pk).accion, "usuario.crear")

    def test_el_trigger_rechaza_delete(self) -> None:
        evento = crear_evento()
        with self.assertRaises(DatabaseError):
            self.sql("DELETE FROM audit_eventoauditoria WHERE id = %s", evento.pk)
        self.assertTrue(EventoAuditoria.objects.filter(pk=evento.pk).exists())

    def test_el_trigger_rechaza_cambios_masivos(self) -> None:
        crear_evento()
        crear_evento(accion="usuario.editar")
        with self.assertRaises(DatabaseError):
            self.sql("DELETE FROM audit_eventoauditoria")
        with self.assertRaises(DatabaseError):
            self.sql("UPDATE audit_eventoauditoria SET usuario_nombre = 'nadie'")
        self.assertEqual(EventoAuditoria.objects.count(), 2)

    def test_insertar_sigue_funcionando(self) -> None:
        self.sql(
            "INSERT INTO audit_eventoauditoria "
            "(ocurrido_en, categoria, accion, usuario_nombre, entidad_nombre, portafolio_nombre,"
            " objeto_tipo, objeto_id, objeto_nombre, cambios, detalle) "
            "VALUES (now(), 'sistema', 'a.b', '', '', '', '', '', '', '[]', '{}')"
        )
        self.assertTrue(EventoAuditoria.objects.filter(accion="a.b").exists())


class AdminDeDjangoSoloLecturaTests(TestCase):
    def setUp(self) -> None:
        self.modelo = EventoAuditoriaAdmin(EventoAuditoria, admin.site)

    def peticion(self, user):
        peticion = RequestFactory().get("/admin/")
        peticion.user = user
        return peticion

    def test_ni_el_superusuario_puede_agregar_cambiar_o_borrar(self) -> None:
        dev = usuario("dev", superuser=True)
        peticion = self.peticion(dev)
        self.assertFalse(self.modelo.has_add_permission(peticion))
        self.assertFalse(self.modelo.has_change_permission(peticion))
        self.assertFalse(self.modelo.has_delete_permission(peticion))

    def test_solo_el_superusuario_lo_ve(self) -> None:
        self.assertTrue(
            self.modelo.has_view_permission(self.peticion(usuario("dev", superuser=True)))
        )
        self.assertTrue(
            self.modelo.has_module_permission(self.peticion(usuario("dev2", superuser=True)))
        )
        staff = usuario("staff")
        self.assertFalse(self.modelo.has_view_permission(self.peticion(staff)))
        self.assertFalse(self.modelo.has_module_permission(self.peticion(staff)))


class PermisosInicialesTests(TestCase):
    def permisos_de(self, rol: str) -> set[str]:
        grupo = Group.objects.get(name=rol)
        return {
            f"{p.content_type.app_label}.{p.codename}"
            for p in grupo.permissions.select_related("content_type")
        }

    def test_el_admin_ve_el_historial_de_administracion(self) -> None:
        self.assertIn("audit.view_system_log", self.permisos_de("Admin"))
        self.assertNotIn("audit.view_entity_log", self.permisos_de("Admin"))

    def test_responsable_y_auditor_ven_el_de_sus_entidades(self) -> None:
        for rol in (RESPONSABLE, AUDITOR):
            self.assertIn("audit.view_entity_log", self.permisos_de(rol), rol)

    def test_planificador_y_operario_no_ven_el_historial(self) -> None:
        for rol in (PLANIFICADOR, COLABORADOR):
            self.assertFalse({p for p in self.permisos_de(rol) if p.startswith("audit.")}, rol)

    def test_el_catalogo_conoce_los_dos_permisos(self) -> None:
        self.assertEqual(obtener_permiso("audit.view_system_log").ambito, AMBITO_GLOBAL)
        self.assertEqual(obtener_permiso("audit.view_entity_log").ambito, AMBITO_ENTIDAD)

    def test_no_hay_permisos_de_agregar_cambiar_o_borrar(self) -> None:
        from django.contrib.auth.models import Permission

        codenames = set(
            Permission.objects.filter(content_type__app_label="audit").values_list(
                "codename", flat=True
            )
        )
        self.assertEqual(codenames, {"view_system_log", "view_entity_log"})
