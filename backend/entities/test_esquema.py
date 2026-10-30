from django.urls import reverse
from rest_framework.test import APITestCase


class EsquemaDeMiembrosTests(APITestCase):
    """La web genera sus tipos desde el esquema OpenAPI: debe describir bien estas peticiones."""

    def setUp(self) -> None:
        r = self.client.get(reverse("schema"), {"format": "json"})
        self.assertEqual(r.status_code, 200)
        self.rutas = r.json()["paths"]

    def test_agregar_un_miembro_usa_el_esquema_de_entrada(self) -> None:
        post = self.rutas["/api/entities/{entidad_id}/members/"]["post"]
        ref = post["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        self.assertTrue(ref.endswith("/MiembroCrearRequest"), ref)

    def test_listar_miembros_declara_el_filtro_activa(self) -> None:
        get = self.rutas["/api/entities/{entidad_id}/members/"]["get"]
        nombres = {p["name"] for p in get.get("parameters", [])}
        self.assertIn("activa", nombres)

    def test_cambiar_un_miembro_usa_el_esquema_de_edicion(self) -> None:
        patch = self.rutas["/api/entities/{entidad_id}/members/{id}/"]["patch"]
        ref = patch["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        self.assertTrue(ref.endswith("/PatchedMiembroEditarRequest"), ref)

    def test_roles_asignables_describe_una_lista(self) -> None:
        get = self.rutas["/api/entities/{entidad_id}/assignable-roles/"]["get"]
        esquema = get["responses"]["200"]["content"]["application/json"]["schema"]
        self.assertEqual(esquema["type"], "array")
