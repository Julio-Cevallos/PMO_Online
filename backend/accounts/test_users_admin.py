from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .catalogo import permisos_registrados
from .models import User
from .roles import PERMISOS_GLOBALES, ROL_ADMIN, ROLES_POR_ENTIDAD

PASSWORD = "Clave-Segura-2026"


def crear_usuario(username: str, *, admin: bool = False, superuser: bool = False) -> User:
    if superuser:
        return User.objects.create_superuser(username, f"{username}@example.com", PASSWORD)
    user = User.objects.create_user(username, f"{username}@example.com", PASSWORD)
    if admin:
        user.groups.add(Group.objects.get(name=ROL_ADMIN))
    # Se vuelve a leer para no arrastrar la caché de permisos de la instancia.
    return User.objects.get(pk=user.pk)


class RolesDelSistemaTests(APITestCase):
    def test_existen_los_roles_iniciales(self) -> None:
        nombres = set(Group.objects.values_list("name", flat=True))
        self.assertTrue({ROL_ADMIN, *ROLES_POR_ENTIDAD} <= nombres)

    def test_admin_tiene_los_permisos_globales(self) -> None:
        codenames = set(
            Group.objects.get(name=ROL_ADMIN).permissions.values_list("codename", flat=True)
        )
        esperados = {
            d.codename.partition(".")[2] for d in permisos_registrados() if d.ambito == "global"
        }
        self.assertEqual(codenames, esperados)
        self.assertTrue(set(PERMISOS_GLOBALES) < esperados)  # incluye los de otros módulos

    def test_permisos_iniciales_de_los_roles_por_entidad(self) -> None:
        esperados = {
            "Responsable de entidad": {"edit_entity", "view_members", "manage_members"},
            "Planificador": {"view_members"},
            "Operario de campo": set(),
            "Auditor": set(),
        }
        self.assertEqual(set(esperados), set(ROLES_POR_ENTIDAD))
        for nombre, codenames in esperados.items():
            reales = set(
                Group.objects.get(name=nombre).permissions.values_list("codename", flat=True)
            )
            self.assertEqual(reales, codenames, nombre)

    def test_los_permisos_globales_existen_en_el_catalogo(self) -> None:
        for codename in PERMISOS_GLOBALES:
            self.assertTrue(
                Permission.objects.filter(
                    content_type__app_label="accounts", codename=codename
                ).exists()
            )


class AccesoGestionUsuariosTests(APITestCase):
    def setUp(self) -> None:
        self.url = reverse("users-list")

    def test_sin_sesion_401(self) -> None:
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_usuario_sin_rol_403(self) -> None:
        self.client.force_authenticate(crear_usuario("recien_registrado"))
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)

    def test_rol_por_entidad_no_da_acceso_global(self) -> None:
        user = crear_usuario("plani")
        user.groups.add(Group.objects.get(name="Planificador"))
        self.client.force_authenticate(User.objects.get(pk=user.pk))
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_accede(self) -> None:
        self.client.force_authenticate(crear_usuario("jefe", admin=True))
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)

    def test_superusuario_accede(self) -> None:
        self.client.force_authenticate(crear_usuario("dev", superuser=True))
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)


class GestionUsuariosTests(APITestCase):
    def setUp(self) -> None:
        self.admin = crear_usuario("jefe", admin=True)
        self.dev = crear_usuario("dev", superuser=True)
        self.client.force_authenticate(self.admin)
        self.url = reverse("users-list")
        self.nuevo = {"username": "ana", "email": "Ana@Example.com", "password": PASSWORD}

    def detalle(self, user: User) -> str:
        return reverse("users-detail", args=[user.pk])

    # --- listado ---
    def test_admin_no_ve_superusuarios(self) -> None:
        nombres = {u["username"] for u in self.client.get(self.url).data["results"]}
        self.assertIn("jefe", nombres)
        self.assertNotIn("dev", nombres)

    def test_superusuario_ve_todos(self) -> None:
        self.client.force_authenticate(self.dev)
        nombres = {u["username"] for u in self.client.get(self.url).data["results"]}
        self.assertTrue({"jefe", "dev"} <= nombres)

    def test_listado_indica_si_es_admin(self) -> None:
        crear_usuario("normal")
        filas = {u["username"]: u for u in self.client.get(self.url).data["results"]}
        self.assertTrue(filas["jefe"]["is_admin"])
        self.assertFalse(filas["normal"]["is_admin"])

    def test_filtrar_por_activos(self) -> None:
        inactivo = crear_usuario("baja")
        User.objects.filter(pk=inactivo.pk).update(is_active=False)
        r = self.client.get(self.url, {"is_active": "false"})
        self.assertEqual([u["username"] for u in r.data["results"]], ["baja"])

    def test_listado_no_expone_claves(self) -> None:
        for fila in self.client.get(self.url).data["results"]:
            self.assertNotIn("password", fila)

    # --- crear ---
    def test_admin_crea_usuario_normal(self) -> None:
        r = self.client.post(self.url, self.nuevo)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="ana")
        self.assertEqual(user.email, "ana@example.com")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotIn("password", r.data)
        self.assertFalse(r.data["is_admin"])

    def test_el_usuario_creado_puede_iniciar_sesion(self) -> None:
        self.client.post(self.url, self.nuevo)
        self.client.force_authenticate(None)
        r = self.client.post(
            reverse("token_obtain_pair"), {"username": "ana", "password": PASSWORD}
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_crear_exige_clave(self) -> None:
        r = self.client.post(self.url, {"username": "ana"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", r.data)

    def test_crear_rechaza_clave_debil(self) -> None:
        r = self.client.post(self.url, {**self.nuevo, "password": "12345678"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="ana").exists())

    def test_crear_con_correo_repetido(self) -> None:
        crear_usuario("otro")
        r = self.client.post(self.url, {**self.nuevo, "email": "otro@example.com"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_no_puede_crear_admins(self) -> None:
        r = self.client.post(self.url, {**self.nuevo, "is_admin": True})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(User.objects.filter(username="ana").exists())

    def test_superusuario_crea_admins(self) -> None:
        self.client.force_authenticate(self.dev)
        r = self.client.post(self.url, {**self.nuevo, "is_admin": True})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.get(username="ana").is_admin)

    def test_no_se_pueden_dar_privilegios_de_django(self) -> None:
        for quien in (self.admin, self.dev):
            self.client.force_authenticate(quien)
            nombre = f"intento_{quien.username}"
            r = self.client.post(
                self.url,
                {
                    **self.nuevo,
                    "username": nombre,
                    "email": "",
                    "is_staff": True,
                    "is_superuser": True,
                },
            )
            self.assertEqual(r.status_code, status.HTTP_201_CREATED)
            user = User.objects.get(username=nombre)
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)

    def test_solo_acepta_json(self) -> None:
        """En multipart un booleano ausente valdría false (cuenta inactiva): se rechaza."""
        r = self.client.post(self.url, self.nuevo, format="multipart")
        self.assertEqual(r.status_code, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
        self.assertFalse(User.objects.filter(username="ana").exists())

    # --- editar ---
    def test_editar_datos_y_desactivar(self) -> None:
        user = crear_usuario("luis")
        r = self.client.patch(
            self.detalle(user), {"first_name": "Luis", "is_active": False, "username": "otro"}
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual((user.first_name, user.is_active, user.username), ("Luis", False, "luis"))

    def test_no_se_cambia_la_clave_desde_aqui(self) -> None:
        user = crear_usuario("luis")
        r = self.client.patch(self.detalle(user), {"password": "Otra-Clave-Segura-2027"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        user.refresh_from_db()
        self.assertTrue(user.check_password(PASSWORD))

    def test_no_se_dan_privilegios_editando(self) -> None:
        user = crear_usuario("luis")
        self.client.patch(self.detalle(user), {"is_staff": True, "is_superuser": True})
        user.refresh_from_db()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_admin_no_puede_quitar_ni_dar_admin(self) -> None:
        otro_admin = crear_usuario("otro_admin", admin=True)
        r = self.client.patch(self.detalle(otro_admin), {"is_admin": False})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(User.objects.get(pk=otro_admin.pk).is_admin)
        normal = crear_usuario("normal")
        r = self.client.patch(self.detalle(normal), {"is_admin": True})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_puede_reenviar_el_mismo_valor_de_is_admin(self) -> None:
        normal = crear_usuario("normal")
        r = self.client.patch(self.detalle(normal), {"is_admin": False, "first_name": "N"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_superusuario_da_y_quita_admin(self) -> None:
        self.client.force_authenticate(self.dev)
        normal = crear_usuario("normal")
        self.client.patch(self.detalle(normal), {"is_admin": True})
        self.assertTrue(User.objects.get(pk=normal.pk).is_admin)
        self.client.patch(self.detalle(normal), {"is_admin": False})
        self.assertFalse(User.objects.get(pk=normal.pk).is_admin)

    def test_admin_no_se_desactiva_a_si_mismo(self) -> None:
        r = self.client.patch(self.detalle(self.admin), {"is_active": False})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(User.objects.get(pk=self.admin.pk).is_active)

    def test_admin_no_puede_tocar_superusuarios(self) -> None:
        self.assertEqual(self.client.get(self.detalle(self.dev)).status_code, 404)
        r = self.client.patch(self.detalle(self.dev), {"is_active": False})
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(User.objects.get(pk=self.dev.pk).is_active)

    def test_no_hay_borrado(self) -> None:
        user = crear_usuario("luis")
        r = self.client.delete(self.detalle(user))
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

    # --- desbloqueo ---
    def bloquear(self, user: User) -> None:
        self.client.force_authenticate(None)
        for _ in range(3):
            self.client.post(
                reverse("token_obtain_pair"), {"username": user.username, "password": "x"}
            )
        self.client.force_authenticate(self.admin)

    def test_admin_desbloquea_una_cuenta(self) -> None:
        user = crear_usuario("luis")
        self.bloquear(user)
        self.assertTrue(User.objects.get(pk=user.pk).is_locked)
        r = self.client.post(reverse("users-unlock", args=[user.pk]))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        user.refresh_from_db()
        self.assertEqual((user.failed_attempts, user.locked_until), (0, None))
        self.client.force_authenticate(None)
        r = self.client.post(
            reverse("token_obtain_pair"), {"username": "luis", "password": PASSWORD}
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_el_listado_muestra_el_bloqueo(self) -> None:
        user = crear_usuario("luis")
        self.bloquear(user)
        filas = {u["username"]: u for u in self.client.get(self.url).data["results"]}
        self.assertTrue(filas["luis"]["is_locked"])
        self.assertEqual(filas["luis"]["failed_attempts"], 3)

    def test_sin_permiso_no_puede_desbloquear(self) -> None:
        user = crear_usuario("luis")
        self.client.force_authenticate(crear_usuario("curioso"))
        r = self.client.post(reverse("users-unlock", args=[user.pk]))
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_no_desbloquea_superusuarios(self) -> None:
        r = self.client.post(reverse("users-unlock", args=[self.dev.pk]))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class RegistroPublicoTests(APITestCase):
    def test_quien_se_registra_no_tiene_rol_ni_acceso_global(self) -> None:
        self.client.post(
            reverse("register"),
            {"username": "ana", "email": "a@example.com", "password": PASSWORD},
        )
        user = User.objects.get(username="ana")
        self.assertFalse(user.groups.exists())
        self.assertFalse(user.is_admin)
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(reverse("users-list")).status_code, 403)
