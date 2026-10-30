import json
from unittest.mock import patch

from django.contrib.admin.sites import site
from django.contrib.auth.models import Group
from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import EventoAuditoria
from entities.utiles_pruebas import COLABORADOR, entidad, miembro

from .admin import AccountsUserAdmin
from .models import PerfilRol, User
from .test_users_admin import PASSWORD, crear_usuario

NUEVA = "Otra-Clave-Segura-2027"


def eventos(*prefijos: str):
    """Eventos cuya acción empieza por alguno de los prefijos (todos, si no se indica)."""
    consulta = EventoAuditoria.objects.order_by("id")
    if prefijos:
        ids = [e.pk for e in consulta if e.accion.startswith(prefijos)]
        return consulta.filter(pk__in=ids)
    return consulta


class AuditoriaBase(APITestCase):
    def login(self, username: str, password: str = PASSWORD):
        return self.client.post(
            reverse("token_obtain_pair"), {"username": username, "password": password}
        )


class SesionesTests(AuditoriaBase):
    def setUp(self) -> None:
        self.ana = crear_usuario("ana")

    def test_el_inicio_de_sesion_correcto_queda_registrado(self) -> None:
        self.assertEqual(self.login("ana").status_code, status.HTTP_200_OK)
        (e,) = eventos("usuario.iniciar_sesion")
        self.assertEqual(
            (e.categoria, e.usuario_id, e.usuario_nombre), ("sistema", self.ana.pk, "ana")
        )
        self.assertEqual((e.objeto_tipo, e.objeto_id), ("accounts.user", str(self.ana.pk)))
        self.assertEqual(e.ip, "127.0.0.1")

    def test_los_intentos_fallidos_no_se_registran_uno_a_uno(self) -> None:
        self.login("ana", "mala")
        self.login("ana", "mala")
        self.assertEqual(eventos().count(), 0)

    def test_un_inicio_de_sesion_fallido_no_deja_evento_aunque_el_usuario_no_exista(self) -> None:
        self.assertEqual(self.login("fantasma", "x").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(eventos().count(), 0)

    def test_el_tercer_fallo_registra_el_bloqueo(self) -> None:
        for _ in range(3):
            self.login("ana", "mala")
        (e,) = eventos("usuario.bloquear")
        self.assertEqual((e.usuario_nombre, e.objeto_id), ("ana", str(self.ana.pk)))
        self.assertEqual(e.detalle["intentos"], 3)
        self.assertIn("bloqueado_hasta", e.detalle)
        self.assertEqual(eventos("usuario.iniciar_sesion").count(), 0)

    def test_los_intentos_con_la_cuenta_bloqueada_no_suman_eventos(self) -> None:
        for _ in range(3):
            self.login("ana", "mala")
        self.assertEqual(self.login("ana").status_code, status.HTTP_423_LOCKED)
        self.assertEqual(eventos().count(), 1)

    def test_el_admin_desbloquea_y_queda_como_autor(self) -> None:
        admin = crear_usuario("jefe", admin=True)
        for _ in range(3):
            self.login("ana", "mala")
        self.client.force_authenticate(admin)
        r = self.client.post(reverse("users-unlock", args=[self.ana.pk]))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        (e,) = eventos("usuario.desbloquear")
        self.assertEqual((e.usuario_nombre, e.objeto_nombre), ("jefe", "ana"))

    def test_desbloquear_desde_django_admin_tambien_se_registra(self) -> None:
        dev = crear_usuario("dev", superuser=True)
        peticion = RequestFactory().post("/admin/")
        peticion.user = dev
        modelo = AccountsUserAdmin(User, site)
        with patch.object(AccountsUserAdmin, "message_user"):
            modelo.desbloquear(peticion, User.objects.filter(pk=self.ana.pk))
        (e,) = eventos("usuario.desbloquear")
        self.assertEqual((e.usuario_nombre, e.objeto_nombre), ("dev", "ana"))

    def test_el_cambio_de_clave_se_registra_sin_guardar_las_claves(self) -> None:
        self.client.force_authenticate(self.ana)
        r = self.client.post(
            reverse("password_change"), {"old_password": PASSWORD, "new_password": NUEVA}
        )
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        (e,) = eventos("usuario.cambiar_clave")
        self.assertEqual(e.usuario_nombre, "ana")
        guardado = json.dumps([e.cambios, e.detalle])
        self.assertNotIn(PASSWORD, guardado)
        self.assertNotIn(NUEVA, guardado)
        self.assertEqual(e.cambios[0]["campo"], "password")

    def test_un_cambio_de_clave_rechazado_no_deja_evento(self) -> None:
        self.client.force_authenticate(self.ana)
        for cuerpo in (
            {"old_password": "mala", "new_password": NUEVA},
            {"old_password": PASSWORD, "new_password": "12345678"},
        ):
            self.client.post(reverse("password_change"), cuerpo)
        self.assertEqual(eventos().count(), 0)

    def test_si_falla_el_registro_la_clave_no_cambia(self) -> None:
        self.client.force_authenticate(self.ana)
        self.client.raise_request_exception = False
        with patch("accounts.auditoria.registrar", side_effect=RuntimeError("falla")):
            r = self.client.post(
                reverse("password_change"), {"old_password": PASSWORD, "new_password": NUEVA}
            )
        self.assertEqual(r.status_code, 500)
        self.ana.refresh_from_db()
        self.assertTrue(self.ana.check_password(PASSWORD))


class AltaDeUsuariosTests(AuditoriaBase):
    def test_el_registro_publico_queda_registrado_a_nombre_de_la_nueva_cuenta(self) -> None:
        r = self.client.post(
            reverse("register"),
            {"username": "nuevo", "email": "n@example.com", "password": PASSWORD},
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        (e,) = eventos("usuario.registrar")
        self.assertEqual((e.usuario_nombre, e.objeto_nombre), ("nuevo", "nuevo"))
        campos = {c["campo"]: c["despues"] for c in e.cambios}
        self.assertEqual(campos["username"], "nuevo")
        self.assertEqual(campos["email"], "n@example.com")
        self.assertNotIn("password", campos)
        self.assertNotIn(PASSWORD, json.dumps(e.cambios))

    def test_un_registro_invalido_no_deja_evento(self) -> None:
        self.client.post(reverse("register"), {"username": "x", "password": "123"})
        self.assertEqual(eventos().count(), 0)

    def test_el_admin_crea_un_usuario(self) -> None:
        admin = crear_usuario("jefe", admin=True)
        self.client.force_authenticate(admin)
        r = self.client.post(
            reverse("users-list"),
            {"username": "ana", "email": "ana@example.com", "password": PASSWORD},
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        (e,) = eventos("usuario.crear")
        self.assertEqual((e.usuario_nombre, e.objeto_nombre), ("jefe", "ana"))
        self.assertEqual(eventos("usuario.dar_admin").count(), 0)
        self.assertNotIn(PASSWORD, json.dumps(e.cambios))

    def test_crear_un_admin_registra_tambien_el_rol(self) -> None:
        dev = crear_usuario("dev", superuser=True)
        self.client.force_authenticate(dev)
        self.client.post(
            reverse("users-list"),
            {"username": "nueva_admin", "password": PASSWORD, "is_admin": True},
        )
        self.assertEqual(eventos("usuario.crear").count(), 1)
        (e,) = eventos("usuario.dar_admin")
        self.assertEqual((e.usuario_nombre, e.objeto_nombre), ("dev", "nueva_admin"))

    def test_un_alta_rechazada_no_deja_evento(self) -> None:
        admin = crear_usuario("jefe", admin=True)
        self.client.force_authenticate(admin)
        self.client.post(reverse("users-list"), {"username": "ana", "password": "12345678"})
        self.client.post(
            reverse("users-list"), {"username": "ana", "password": PASSWORD, "is_admin": True}
        )
        self.assertEqual(eventos("usuario.").count(), 0)

    def test_si_falla_el_registro_no_se_crea_el_usuario(self) -> None:
        admin = crear_usuario("jefe", admin=True)
        self.client.force_authenticate(admin)
        self.client.raise_request_exception = False
        with patch("accounts.auditoria.registrar", side_effect=RuntimeError("falla")):
            r = self.client.post(reverse("users-list"), {"username": "ana", "password": PASSWORD})
        self.assertEqual(r.status_code, 500)
        self.assertFalse(User.objects.filter(username="ana").exists())

    def test_el_registro_publico_se_deshace_si_falla_el_evento(self) -> None:
        self.client.raise_request_exception = False
        with patch("accounts.auditoria.registrar", side_effect=RuntimeError("falla")):
            r = self.client.post(reverse("register"), {"username": "ana", "password": PASSWORD})
        self.assertEqual(r.status_code, 500)
        self.assertFalse(User.objects.filter(username="ana").exists())


class EdicionDeUsuariosTests(AuditoriaBase):
    def setUp(self) -> None:
        self.admin = crear_usuario("jefe", admin=True)
        self.dev = crear_usuario("dev", superuser=True)
        self.luis = crear_usuario("luis")
        self.client.force_authenticate(self.admin)
        self.url = reverse("users-detail", args=[self.luis.pk])

    def test_editar_datos_registra_solo_lo_que_cambio(self) -> None:
        self.client.patch(self.url, {"first_name": "Luis", "email": "nuevo@example.com"})
        (e,) = eventos("usuario.editar")
        self.assertEqual((e.usuario_nombre, e.objeto_nombre), ("jefe", "luis"))
        self.assertEqual(
            {c["campo"]: (c["antes"], c["despues"]) for c in e.cambios},
            {"first_name": ("", "Luis"), "email": ("luis@example.com", "nuevo@example.com")},
        )

    def test_desactivar_y_reactivar(self) -> None:
        self.client.patch(self.url, {"is_active": False})
        self.client.patch(self.url, {"is_active": True})
        self.assertEqual(eventos("usuario.desactivar").count(), 1)
        self.assertEqual(eventos("usuario.reactivar").count(), 1)
        self.assertEqual(eventos("usuario.editar").count(), 0)

    def test_un_cambio_mixto_genera_un_evento_por_tipo(self) -> None:
        self.client.patch(self.url, {"is_active": False, "last_name": "Perez"})
        self.assertEqual(eventos("usuario.desactivar").count(), 1)
        (e,) = eventos("usuario.editar")
        self.assertEqual([c["campo"] for c in e.cambios], ["last_name"])

    def test_sin_cambios_reales_no_hay_evento(self) -> None:
        self.client.patch(self.url, {"first_name": "", "is_active": True})
        self.assertEqual(eventos().count(), 0)

    def test_dar_y_quitar_el_rol_admin(self) -> None:
        self.client.force_authenticate(self.dev)
        self.client.patch(self.url, {"is_admin": True})
        self.client.patch(self.url, {"is_admin": False})
        (dar,) = eventos("usuario.dar_admin")
        (quitar,) = eventos("usuario.quitar_admin")
        self.assertEqual((dar.usuario_nombre, quitar.usuario_nombre), ("dev", "dev"))
        self.assertEqual((dar.cambios[0]["antes"], dar.cambios[0]["despues"]), (False, True))

    def test_un_cambio_rechazado_no_deja_evento(self) -> None:
        self.client.patch(self.url, {"is_admin": True})  # el Admin no puede: 403
        self.client.patch(self.url, {"password": "Otra-Clave-Segura-2027"})  # 400
        self.client.patch(reverse("users-detail", args=[self.dev.pk]), {"is_active": False})  # 404
        self.assertEqual(eventos().count(), 0)

    def test_editar_el_propio_perfil(self) -> None:
        self.client.force_authenticate(self.luis)
        self.client.patch(reverse("me"), {"first_name": "Luis"})
        (e,) = eventos("usuario.editar_perfil")
        self.assertEqual((e.usuario_nombre, e.objeto_nombre), ("luis", "luis"))
        self.assertEqual([c["campo"] for c in e.cambios], ["first_name"])

    def test_editar_el_perfil_sin_cambios_no_deja_evento(self) -> None:
        self.client.force_authenticate(self.luis)
        self.client.patch(reverse("me"), {"first_name": ""})
        self.assertEqual(eventos().count(), 0)


class RolesTests(AuditoriaBase):
    def setUp(self) -> None:
        self.admin = crear_usuario("jefe", admin=True)
        self.client.force_authenticate(self.admin)
        self.url = reverse("roles-list")

    def detalle(self, nombre: str) -> str:
        return reverse("roles-detail", args=[Group.objects.get(name=nombre).pk])

    def test_crear_un_rol(self) -> None:
        self.client.post(self.url, {"name": "Supervisor", "nivel": 25})
        (e,) = eventos("rol.crear")
        self.assertEqual(
            (e.usuario_nombre, e.objeto_tipo, e.objeto_nombre), ("jefe", "auth.group", "Supervisor")
        )
        campos = {c["campo"]: c["despues"] for c in e.cambios}
        self.assertEqual(
            (campos["nombre"], campos["nivel"], campos["nivel_minimo_para_asignar"]),
            ("Supervisor", 25, 26),
        )
        self.assertEqual(campos["permisos"], [])

    def test_editar_un_rol_registra_lo_que_cambio(self) -> None:
        self.client.post(self.url, {"name": "Supervisor", "nivel": 25})
        self.client.patch(self.detalle("Supervisor"), {"name": "Jefe de zona", "nivel": 27})
        (e,) = eventos("rol.editar")
        cambios = {c["campo"]: (c["antes"], c["despues"]) for c in e.cambios}
        self.assertEqual(cambios["nombre"], ("Supervisor", "Jefe de zona"))
        self.assertEqual(cambios["nivel"], (25, 27))
        self.assertEqual(cambios["nivel_minimo_para_asignar"], (26, 28))
        self.assertNotIn("permisos", cambios)

    def test_los_permisos_que_se_agregan_o_quitan_quedan_registrados(self) -> None:
        # `entities.view_members` ya existe en el catálogo como permiso por entidad.
        self.client.patch(self.detalle("Colaborador"), {"permissions": ["entities.view_members"]})
        (e,) = eventos("rol.editar")
        (cambio,) = [c for c in e.cambios if c["campo"] == "permisos"]
        self.assertEqual((cambio["antes"], cambio["despues"]), ([], ["entities.view_members"]))

    def test_un_cambio_que_no_cambia_nada_no_deja_evento(self) -> None:
        self.client.patch(self.detalle("Planificador"), {"name": "Planificador"})
        self.assertEqual(eventos().count(), 0)

    def test_eliminar_un_rol(self) -> None:
        self.client.post(self.url, {"name": "Supervisor", "nivel": 25})
        identificador = Group.objects.get(name="Supervisor").pk
        r = self.client.delete(self.detalle("Supervisor"))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        (e,) = eventos("rol.eliminar")
        self.assertEqual((e.objeto_id, e.objeto_nombre), (str(identificador), "Supervisor"))
        self.assertEqual(e.usuario_nombre, "jefe")

    def test_un_rol_en_uso_no_se_borra_y_no_deja_evento(self) -> None:
        grupo = Group.objects.create(name="Supervisor")
        PerfilRol.objects.create(grupo=grupo, nivel=35, nivel_minimo_para_asignar=36)
        miembro(crear_usuario("sup"), entidad("Alfa"), "Supervisor")
        r = self.client.delete(reverse("roles-detail", args=[grupo.pk]))
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(eventos("rol.eliminar").count(), 0)

    def test_las_acciones_rechazadas_no_dejan_evento(self) -> None:
        self.client.post(self.url, {"name": "Admin", "nivel": 5})  # 400
        self.client.patch(self.detalle("Admin"), {"permissions": []})  # 403
        self.client.delete(self.detalle("Planificador"))  # 403, rol del sistema
        self.client.delete(self.detalle("Admin"))  # 403
        self.assertEqual(eventos().count(), 0)

    def test_si_falla_el_registro_el_rol_no_se_crea(self) -> None:
        self.client.raise_request_exception = False
        with patch("accounts.auditoria.registrar", side_effect=RuntimeError("falla")):
            r = self.client.post(self.url, {"name": "Supervisor", "nivel": 25})
        self.assertEqual(r.status_code, 500)
        self.assertFalse(Group.objects.filter(name="Supervisor").exists())

    def test_si_falla_el_registro_el_rol_no_se_borra(self) -> None:
        self.client.post(self.url, {"name": "Supervisor", "nivel": 25})
        self.client.raise_request_exception = False
        with patch("accounts.auditoria.registrar", side_effect=RuntimeError("falla")):
            r = self.client.delete(self.detalle("Supervisor"))
        self.assertEqual(r.status_code, 500)
        self.assertTrue(Group.objects.filter(name="Supervisor").exists())


class OperarioNoEsAuditoriaTests(AuditoriaBase):
    def test_miembros_y_roles_de_prueba_no_ensucian_el_historial(self) -> None:
        """Crear datos de prueba directamente (sin pasar por la API) no genera eventos."""
        miembro(crear_usuario("ana"), entidad("Alfa"), COLABORADOR)
        self.assertEqual(eventos().count(), 0)
