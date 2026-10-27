from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User

PASSWORD = "Clave-Segura-2026"


class RegisterTests(APITestCase):
    payload = {"username": "ana", "email": "Ana@Example.com", "password": PASSWORD}

    def setUp(self) -> None:
        self.url = reverse("register")

    def test_registro_exitoso_normaliza_correo_y_no_devuelve_clave(self) -> None:
        r = self.client.post(self.url, self.payload)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("password", r.data)
        user = User.objects.get(username="ana")
        self.assertEqual(user.email, "ana@example.com")
        self.assertTrue(user.check_password(PASSWORD))

    def test_correo_duplicado_sin_importar_mayusculas(self) -> None:
        self.client.post(self.url, self.payload)
        r = self.client.post(
            self.url, {**self.payload, "username": "otra", "email": "ANA@example.com"}
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", r.data)

    def test_username_duplicado(self) -> None:
        self.client.post(self.url, self.payload)
        r = self.client.post(self.url, {**self.payload, "email": "otro@example.com"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", r.data)

    def test_clave_debil_rechazada(self) -> None:
        r = self.client.post(self.url, {**self.payload, "password": "12345678"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", r.data)
        self.assertEqual(User.objects.count(), 0)

    def test_faltan_campos(self) -> None:
        r = self.client.post(self.url, {})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(r.data), {"username", "password"})

    def test_registro_sin_correo(self) -> None:
        r = self.client.post(self.url, {"username": "sin_correo", "password": PASSWORD})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(User.objects.get(username="sin_correo").email)

    def test_varios_usuarios_sin_correo(self) -> None:
        for nombre in ("uno", "dos"):
            r = self.client.post(self.url, {"username": nombre, "email": "", "password": PASSWORD})
            self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.filter(email__isnull=True).count(), 2)

    def test_correo_con_formato_invalido(self) -> None:
        r = self.client.post(self.url, {**self.payload, "email": "no-es-correo"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", r.data)


class LoginTests(APITestCase):
    def test_registro_y_luego_login_jwt(self) -> None:
        self.client.post(
            reverse("register"),
            {"username": "ana", "email": "ana@example.com", "password": PASSWORD},
        )
        r = self.client.post(
            reverse("token_obtain_pair"), {"username": "ana", "password": PASSWORD}
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("access", r.data)
        self.assertIn("refresh", r.data)

    def test_login_clave_incorrecta(self) -> None:
        User.objects.create_user("ana", "ana@example.com", PASSWORD)
        r = self.client.post(reverse("token_obtain_pair"), {"username": "ana", "password": "mala"})
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token(self) -> None:
        User.objects.create_user("ana", "ana@example.com", PASSWORD)
        tokens = self.client.post(
            reverse("token_obtain_pair"), {"username": "ana", "password": PASSWORD}
        ).data
        r = self.client.post(reverse("token_refresh"), {"refresh": tokens["refresh"]})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("access", r.data)


class MeTests(APITestCase):
    def setUp(self) -> None:
        self.url = reverse("me")
        self.user = User.objects.create_user("ana", "ana@example.com", PASSWORD)

    def test_requiere_autenticacion(self) -> None:
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_obtener_perfil_con_jwt(self) -> None:
        access = self.client.post(
            reverse("token_obtain_pair"), {"username": "ana", "password": PASSWORD}
        ).data["access"]
        r = self.client.get(self.url, HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["username"], "ana")
        self.assertNotIn("password", r.data)

    def test_editar_nombre(self) -> None:
        self.client.force_authenticate(self.user)
        r = self.client.patch(self.url, {"first_name": "Ana", "last_name": "Pérez"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name), ("Ana", "Pérez"))

    def test_no_se_puede_cambiar_username_ni_clave(self) -> None:
        self.client.force_authenticate(self.user)
        self.client.patch(self.url, {"username": "hacker", "password": "Otra-Clave-123"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "ana")
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_correo_en_uso_por_otro(self) -> None:
        User.objects.create_user("luis", "luis@example.com", PASSWORD)
        self.client.force_authenticate(self.user)
        r = self.client.patch(self.url, {"email": "LUIS@example.com"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_conservar_mi_propio_correo(self) -> None:
        self.client.force_authenticate(self.user)
        r = self.client.patch(self.url, {"email": "ana@example.com"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)


class LogoutTests(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("ana", "ana@example.com", PASSWORD)
        self.tokens = self.client.post(
            reverse("token_obtain_pair"), {"username": "ana", "password": PASSWORD}
        ).data

    def test_logout_invalida_el_refresh_token(self) -> None:
        r = self.client.post(reverse("logout"), {"refresh": self.tokens["refresh"]})
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        r = self.client.post(reverse("token_refresh"), {"refresh": self.tokens["refresh"]})
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_con_token_invalido(self) -> None:
        r = self.client.post(reverse("logout"), {"refresh": "no-es-un-token"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_sin_token(self) -> None:
        r = self.client.post(reverse("logout"), {})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class ChangePasswordTests(APITestCase):
    NEW_PASSWORD = "Otra-Clave-Segura-2027"

    def setUp(self) -> None:
        self.url = reverse("password_change")
        self.user = User.objects.create_user("ana", "ana@example.com", PASSWORD)

    def test_requiere_autenticacion(self) -> None:
        r = self.client.post(
            self.url, {"old_password": PASSWORD, "new_password": self.NEW_PASSWORD}
        )
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cambio_exitoso(self) -> None:
        self.client.force_authenticate(self.user)
        r = self.client.post(
            self.url, {"old_password": PASSWORD, "new_password": self.NEW_PASSWORD}
        )
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.NEW_PASSWORD))

    def test_login_con_la_clave_nueva(self) -> None:
        self.client.force_authenticate(self.user)
        self.client.post(self.url, {"old_password": PASSWORD, "new_password": self.NEW_PASSWORD})
        self.client.force_authenticate(None)
        viejo = self.client.post(
            reverse("token_obtain_pair"), {"username": "ana", "password": PASSWORD}
        )
        nuevo = self.client.post(
            reverse("token_obtain_pair"), {"username": "ana", "password": self.NEW_PASSWORD}
        )
        self.assertEqual(viejo.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(nuevo.status_code, status.HTTP_200_OK)

    def test_clave_actual_incorrecta(self) -> None:
        self.client.force_authenticate(self.user)
        r = self.client.post(self.url, {"old_password": "mala", "new_password": self.NEW_PASSWORD})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("old_password", r.data)

    def test_clave_nueva_debil(self) -> None:
        self.client.force_authenticate(self.user)
        r = self.client.post(self.url, {"old_password": PASSWORD, "new_password": "12345678"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("new_password", r.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))
