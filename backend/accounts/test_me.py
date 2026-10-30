from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .test_users_admin import crear_usuario

GLOBALES = [
    "accounts.manage_roles",
    "accounts.manage_users",
    "audit.view_system_log",
    "entities.create_entity",
    "entities.manage_entities",
    "entities.manage_types",
]


class PerfilConPermisosTests(APITestCase):
    def setUp(self) -> None:
        self.url = reverse("me")

    def test_requiere_sesion(self) -> None:
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_un_usuario_sin_rol(self) -> None:
        self.client.force_authenticate(crear_usuario("recien_registrado"))
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["username"], "recien_registrado")
        self.assertFalse(r.data["is_admin"])
        self.assertFalse(r.data["is_superuser"])
        self.assertEqual(r.data["global_permissions"], [])

    def test_el_admin_tiene_los_permisos_globales(self) -> None:
        self.client.force_authenticate(crear_usuario("jefe", admin=True))
        r = self.client.get(self.url)
        self.assertTrue(r.data["is_admin"])
        self.assertFalse(r.data["is_superuser"])
        self.assertEqual(r.data["global_permissions"], GLOBALES)

    def test_el_superusuario_tiene_todos_los_permisos_globales(self) -> None:
        self.client.force_authenticate(crear_usuario("dev", superuser=True))
        r = self.client.get(self.url)
        self.assertTrue(r.data["is_superuser"])
        self.assertEqual(r.data["global_permissions"], GLOBALES)

    def test_no_se_pueden_cambiar_el_rol_ni_los_permisos_desde_el_perfil(self) -> None:
        user = crear_usuario("ana")
        self.client.force_authenticate(user)
        r = self.client.patch(
            self.url,
            {
                "first_name": "Ana",
                "is_admin": True,
                "is_superuser": True,
                "global_permissions": GLOBALES,
            },
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["first_name"], "Ana")
        self.assertFalse(r.data["is_admin"])
        self.assertFalse(r.data["is_superuser"])
        self.assertEqual(r.data["global_permissions"], [])
        user.refresh_from_db()
        self.assertFalse(user.is_superuser or user.is_admin)

    def test_se_conservan_los_campos_de_siempre(self) -> None:
        self.client.force_authenticate(crear_usuario("ana"))
        r = self.client.get(self.url)
        for campo in ("id", "username", "email", "first_name", "last_name", "date_joined"):
            self.assertIn(campo, r.data)
        self.assertNotIn("password", r.data)
