from datetime import timedelta

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
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

    def test_clave_longitud_maxima(self) -> None:
        clave = "Zk9#" * 32
        r = self.client.post(self.url, {**self.payload, "password": clave})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

        r = self.client.post(
            self.url,
            {**self.payload, "username": "otra", "email": "o@example.com", "password": clave + "a"},
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", r.data)

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

    def test_registro_no_otorga_privilegios(self) -> None:
        """D-10: quien se registra no es admin ni staff, aunque lo pida en el cuerpo."""
        r = self.client.post(self.url, {**self.payload, "is_staff": True, "is_superuser": True})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="ana")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.groups.exists())

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

    def test_clave_nueva_longitud_maxima(self) -> None:
        self.client.force_authenticate(self.user)
        clave = "Zk9#" * 32
        r = self.client.post(self.url, {"old_password": PASSWORD, "new_password": clave + "a"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("new_password", r.data)

        r = self.client.post(self.url, {"old_password": PASSWORD, "new_password": clave})
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)


class LoginLockoutTests(APITestCase):
    """HU-21: 3 intentos fallidos bloquean la cuenta 15 minutos."""

    def setUp(self) -> None:
        self.url = reverse("token_obtain_pair")
        self.user = User.objects.create_user("ana", "ana@example.com", PASSWORD)

    def intentar(self, password: str = "mala", username: str = "ana"):
        return self.client.post(self.url, {"username": username, "password": password})

    def bloquear(self) -> None:
        for _ in range(3):
            self.intentar()

    def test_dos_fallos_no_bloquean(self) -> None:
        for _ in range(2):
            self.assertEqual(self.intentar().status_code, status.HTTP_401_UNAUTHORIZED)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_attempts, 2)
        self.assertFalse(self.user.is_locked)
        self.assertEqual(self.intentar(PASSWORD).status_code, status.HTTP_200_OK)

    def test_tercer_fallo_bloquea_por_15_minutos(self) -> None:
        self.intentar()
        self.intentar()
        r = self.intentar()
        self.assertEqual(r.status_code, status.HTTP_423_LOCKED)
        self.assertIn("bloqueada", r.data["detail"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_locked)
        esperado = timezone.now() + timedelta(minutes=15)
        self.assertLess(abs((self.user.locked_until - esperado).total_seconds()), 5)

    def test_cuenta_bloqueada_rechaza_la_clave_correcta(self) -> None:
        self.bloquear()
        r = self.intentar(PASSWORD)
        self.assertEqual(r.status_code, status.HTTP_423_LOCKED)
        self.assertNotIn("access", r.data)

    def test_intentos_con_la_cuenta_bloqueada_no_extienden_el_bloqueo(self) -> None:
        self.bloquear()
        self.user.refresh_from_db()
        hasta = self.user.locked_until
        self.intentar()
        self.user.refresh_from_db()
        self.assertEqual(self.user.locked_until, hasta)

    def test_exito_reinicia_el_contador(self) -> None:
        self.intentar()
        self.intentar()
        self.assertEqual(self.intentar(PASSWORD).status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_attempts, 0)
        # Después del éxito se vuelve a tener el cupo completo.
        self.intentar()
        self.intentar()
        self.assertEqual(self.intentar(PASSWORD).status_code, status.HTTP_200_OK)

    def test_bloqueo_vencido_permite_entrar(self) -> None:
        self.bloquear()
        User.objects.filter(pk=self.user.pk).update(
            locked_until=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(self.intentar(PASSWORD).status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual((self.user.failed_attempts, self.user.locked_until), (0, None))

    def test_bloqueo_vencido_empieza_el_conteo_de_cero(self) -> None:
        self.bloquear()
        User.objects.filter(pk=self.user.pk).update(
            locked_until=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(self.intentar().status_code, status.HTTP_401_UNAUTHORIZED)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_attempts, 1)
        self.assertFalse(self.user.is_locked)

    def test_desbloqueo_manual(self) -> None:
        self.bloquear()
        self.user.refresh_from_db()
        self.user.unlock()
        self.assertEqual(self.intentar(PASSWORD).status_code, status.HTTP_200_OK)

    def test_el_bloqueo_no_afecta_a_otros_usuarios(self) -> None:
        User.objects.create_user("luis", "luis@example.com", PASSWORD)
        self.bloquear()
        self.assertEqual(self.intentar(PASSWORD, "luis").status_code, status.HTTP_200_OK)

    def test_usuario_inexistente_da_401_sin_error(self) -> None:
        for _ in range(5):
            r = self.intentar(username="fantasma")
            self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_usuario_inactivo_no_acumula_intentos(self) -> None:
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        for _ in range(4):
            self.assertEqual(self.intentar().status_code, status.HTTP_401_UNAUTHORIZED)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_attempts, 0)

    @override_settings(LOGIN_MAX_ATTEMPTS=2, LOGIN_LOCKOUT_MINUTES=1)
    def test_limite_y_duracion_configurables(self) -> None:
        self.assertEqual(self.intentar().status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.intentar().status_code, status.HTTP_423_LOCKED)
        self.user.refresh_from_db()
        esperado = timezone.now() + timedelta(minutes=1)
        self.assertLess(abs((self.user.locked_until - esperado).total_seconds()), 5)

    def test_refresh_token_no_se_ve_afectado(self) -> None:
        tokens = self.intentar(PASSWORD).data
        self.bloquear()
        r = self.client.post(reverse("token_refresh"), {"refresh": tokens["refresh"]})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
