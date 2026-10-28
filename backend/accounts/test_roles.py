from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from . import catalogo
from .catalogo import AMBITO_ENTIDAD, AMBITO_GLOBAL, PermisoDef
from .models import User
from .roles import ROL_ADMIN, ROLES_POR_ENTIDAD
from .test_users_admin import crear_usuario

VER = "accounts.ver_plan_test"
EDITAR = "accounts.editar_plan_test"
SIN_FILA = "accounts.sin_fila_test"


class RolesBaseTestCase(APITestCase):
    """Registra permisos por entidad de prueba (hoy ningún módulo los define todavía)."""

    def setUp(self) -> None:
        contenido = ContentType.objects.get_for_model(User)
        for codigo in ("ver_plan_test", "editar_plan_test"):
            Permission.objects.get_or_create(
                content_type=contenido, codename=codigo, defaults={"name": codigo}
            )
        registro = patch.dict(
            catalogo._REGISTRO,
            {
                VER: PermisoDef(VER, "Ver plan", AMBITO_ENTIDAD),
                EDITAR: PermisoDef(EDITAR, "Editar plan", AMBITO_ENTIDAD),
                SIN_FILA: PermisoDef(SIN_FILA, "Sin fila en la BD", AMBITO_ENTIDAD),
            },
        )
        registro.start()
        self.addCleanup(registro.stop)
        self.admin = crear_usuario("jefe", admin=True)
        self.dev = crear_usuario("dev", superuser=True)
        self.client.force_authenticate(self.admin)
        self.url = reverse("roles-list")

    def detalle(self, nombre: str) -> str:
        return reverse("roles-detail", args=[Group.objects.get(name=nombre).pk])


class AccesoRolesTests(RolesBaseTestCase):
    def test_sin_sesion_401(self) -> None:
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            self.client.get(reverse("permissions")).status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_usuario_sin_rol_403(self) -> None:
        self.client.force_authenticate(crear_usuario("recien_registrado"))
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.get(reverse("permissions")).status_code, status.HTTP_403_FORBIDDEN
        )

    def test_rol_por_entidad_no_gestiona_roles(self) -> None:
        user = crear_usuario("plani")
        user.groups.add(Group.objects.get(name="Planificador"))
        self.client.force_authenticate(User.objects.get(pk=user.pk))
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)
        r = self.client.post(self.url, {"nivel": 5, "name": "Intruso"})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_superusuario_accede(self) -> None:
        self.client.force_authenticate(self.dev)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)


class CatalogoYListadoTests(RolesBaseTestCase):
    def test_catalogo_incluye_los_permisos_globales_y_los_de_entidad(self) -> None:
        filas = {p["codename"]: p for p in self.client.get(reverse("permissions")).data}
        self.assertEqual(filas["accounts.manage_users"]["ambito"], AMBITO_GLOBAL)
        self.assertEqual(filas["accounts.manage_roles"]["ambito"], AMBITO_GLOBAL)
        self.assertEqual(filas[VER]["ambito"], AMBITO_ENTIDAD)

    def test_listado_de_roles(self) -> None:
        filas = {r["name"]: r for r in self.client.get(self.url).data}
        self.assertTrue({ROL_ADMIN, *ROLES_POR_ENTIDAD} <= set(filas))
        self.assertEqual(filas[ROL_ADMIN]["scope"], "global")
        self.assertTrue(filas[ROL_ADMIN]["is_system"])
        self.assertEqual(
            filas[ROL_ADMIN]["permissions"],
            [
                "accounts.manage_roles",
                "accounts.manage_users",
                "entities.manage_entities",
                "entities.manage_types",
            ],
        )
        self.assertEqual(filas["Planificador"]["scope"], "entidad")
        self.assertEqual(filas["Planificador"]["permissions"], ["entities.view_members"])
        self.assertEqual(filas["Auditor"]["permissions"], [])

    def test_listado_hace_pocas_consultas_aunque_haya_muchos_roles(self) -> None:
        def consultas() -> int:
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(self.url)
            return len(ctx)

        consultas()  # calienta cachés (tipos de contenido, permisos del usuario)
        antes = consultas()
        for i in range(5):
            self.client.post(self.url, {"nivel": 5, "name": f"Rol {i}", "permissions": [VER]})
        self.assertEqual(consultas(), antes)


class CrearRolTests(RolesBaseTestCase):
    def test_crear_rol_con_permisos_de_entidad(self) -> None:
        r = self.client.post(
            self.url, {"nivel": 5, "name": "Supervisor", "permissions": [VER, EDITAR]}
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["name"], "Supervisor")
        self.assertEqual(r.data["scope"], "entidad")
        self.assertFalse(r.data["is_system"])
        self.assertEqual(r.data["permissions"], sorted([VER, EDITAR]))

    def test_crear_sin_permisos(self) -> None:
        r = self.client.post(self.url, {"nivel": 5, "name": "Observador"})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["permissions"], [])

    def test_el_nombre_se_limpia(self) -> None:
        r = self.client.post(self.url, {"nivel": 5, "name": "  Supervisor  "})
        self.assertEqual(r.data["name"], "Supervisor")

    def test_permiso_global_no_se_asigna_a_un_rol_por_entidad(self) -> None:
        for global_ in ("accounts.manage_users", "accounts.manage_roles"):
            r = self.client.post(self.url, {"nivel": 5, "name": "Colado", "permissions": [global_]})
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("global", str(r.data["permissions"]))
        self.assertFalse(Group.objects.filter(name="Colado").exists())

    def test_permiso_de_django_fuera_del_catalogo_se_rechaza(self) -> None:
        r = self.client.post(
            self.url, {"nivel": 5, "name": "Colado", "permissions": ["accounts.add_user"]}
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("catálogo", str(r.data["permissions"]))

    def test_permiso_inexistente_se_rechaza(self) -> None:
        r = self.client.post(self.url, {"nivel": 5, "name": "Colado", "permissions": ["nada.nada"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_permiso_registrado_pero_sin_fila_en_la_bd(self) -> None:
        r = self.client.post(self.url, {"nivel": 5, "name": "Colado", "permissions": [SIN_FILA]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("migrar", str(r.data["permissions"]))

    def test_si_un_permiso_falla_no_se_crea_el_rol(self) -> None:
        r = self.client.post(
            self.url, {"nivel": 5, "name": "Mixto", "permissions": [VER, "accounts.manage_users"]}
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Group.objects.filter(name="Mixto").exists())

    def test_permisos_con_formato_incorrecto(self) -> None:
        for malo in ("accounts.ver_plan_test", [1, 2], {"a": 1}):
            r = self.client.post(self.url, {"nivel": 5, "name": "Rol malo", "permissions": malo})
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_permisos_repetidos_se_unifican(self) -> None:
        r = self.client.post(self.url, {"nivel": 5, "name": "Rep", "permissions": [VER, VER]})
        self.assertEqual(r.data["permissions"], [VER])

    def test_nombre_repetido_sin_importar_mayusculas(self) -> None:
        self.client.post(self.url, {"nivel": 5, "name": "Supervisor"})
        r = self.client.post(self.url, {"nivel": 5, "name": "SUPERVISOR"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", r.data)

    def test_no_se_puede_crear_otro_admin(self) -> None:
        for nombre in ("Admin", "admin", "ADMIN"):
            r = self.client.post(self.url, {"nivel": 5, "name": nombre})
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nombre_vacio(self) -> None:
        for nombre in ("", "   "):
            r = self.client.post(self.url, {"nivel": 5, "name": nombre})
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_el_rol_creado_no_da_acceso_global(self) -> None:
        self.client.post(self.url, {"nivel": 5, "name": "Supervisor", "permissions": [VER]})
        user = crear_usuario("sup")
        user.groups.add(Group.objects.get(name="Supervisor"))
        self.client.force_authenticate(User.objects.get(pk=user.pk))
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(reverse("users-list")).status_code, 403)


class EditarRolTests(RolesBaseTestCase):
    def test_reemplazar_permisos_de_un_rol_del_sistema(self) -> None:
        r = self.client.patch(self.detalle("Planificador"), {"permissions": [VER, EDITAR]})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["permissions"], sorted([VER, EDITAR]))
        r = self.client.patch(self.detalle("Planificador"), {"permissions": [VER]})
        self.assertEqual(r.data["permissions"], [VER])
        r = self.client.patch(self.detalle("Planificador"), {"permissions": []})
        self.assertEqual(r.data["permissions"], [])

    def test_editar_solo_el_nombre_conserva_los_permisos(self) -> None:
        self.client.post(self.url, {"nivel": 5, "name": "Supervisor", "permissions": [VER]})
        r = self.client.patch(self.detalle("Supervisor"), {"name": "Jefe de zona"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual((r.data["name"], r.data["permissions"]), ("Jefe de zona", [VER]))

    def test_no_se_asigna_un_permiso_global_editando(self) -> None:
        r = self.client.patch(
            self.detalle("Planificador"), {"permissions": ["accounts.manage_roles"]}
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        # No cambió: sigue con su permiso inicial.
        self.assertEqual(Group.objects.get(name="Planificador").permissions.count(), 1)

    def test_roles_del_sistema_no_se_renombran(self) -> None:
        r = self.client.patch(self.detalle("Auditor"), {"name": "Otro nombre"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Group.objects.filter(name="Auditor").exists())

    def test_renombrar_con_el_mismo_nombre_es_valido(self) -> None:
        r = self.client.patch(self.detalle("Auditor"), {"name": "Auditor", "permissions": [VER]})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_no_se_puede_tomar_el_nombre_de_otro_rol(self) -> None:
        self.client.post(self.url, {"nivel": 5, "name": "Supervisor"})
        r = self.client.patch(self.detalle("Supervisor"), {"name": "auditor"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_el_rol_admin_no_se_modifica_ni_por_un_superusuario(self) -> None:
        for quien in (self.admin, self.dev):
            self.client.force_authenticate(quien)
            r = self.client.patch(self.detalle(ROL_ADMIN), {"permissions": []})
            self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
            r = self.client.patch(self.detalle(ROL_ADMIN), {"name": "Otro"})
            self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Group.objects.get(name=ROL_ADMIN).permissions.count(), 4)

    def test_no_hay_put(self) -> None:
        r = self.client.put(self.detalle("Auditor"), {"name": "Auditor"})
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class EliminarRolTests(RolesBaseTestCase):
    def test_eliminar_un_rol_creado(self) -> None:
        self.client.post(self.url, {"nivel": 5, "name": "Supervisor", "permissions": [VER]})
        r = self.client.delete(self.detalle("Supervisor"))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Group.objects.filter(name="Supervisor").exists())

    def test_no_se_eliminan_los_roles_del_sistema(self) -> None:
        for nombre in (ROL_ADMIN, *ROLES_POR_ENTIDAD):
            r = self.client.delete(self.detalle(nombre))
            self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
            self.assertTrue(Group.objects.filter(name=nombre).exists())

    def test_eliminar_un_rol_inexistente(self) -> None:
        r = self.client.delete(reverse("roles-detail", args=[999999]))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


@override_settings()
class ReglasDelRegistroTests(APITestCase):
    def test_registrar_ambito_invalido(self) -> None:
        with self.assertRaises(ValueError):
            catalogo.registrar_permiso("app.algo", "Algo", "otro")

    def test_registrar_sin_app(self) -> None:
        with self.assertRaises(ValueError):
            catalogo.registrar_permiso("algo", "Algo", AMBITO_ENTIDAD)

    def test_registrar_dos_veces_igual_es_idempotente(self) -> None:
        catalogo.registrar_permiso(
            "accounts.manage_users", "Gestionar usuarios del sistema", "global"
        )

    def test_registrar_dos_veces_distinto_falla(self) -> None:
        with self.assertRaises(ValueError):
            catalogo.registrar_permiso("accounts.manage_users", "Otro nombre", AMBITO_ENTIDAD)
