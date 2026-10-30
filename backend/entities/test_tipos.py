from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import TipoEntidad
from .utiles_pruebas import COLABORADOR, RESPONSABLE, entidad, miembro, usuario


class TiposBase(APITestCase):
    def setUp(self) -> None:
        self.admin = usuario("jefe", admin=True)
        self.dev = usuario("dev", superuser=True)
        self.url = reverse("entity-types-list")
        self.client.force_authenticate(self.admin)

    def detalle(self, nombre: str) -> str:
        return reverse("entity-types-detail", args=[TipoEntidad.objects.get(nombre=nombre).pk])


class TiposSembradosTests(TiposBase):
    def test_vienen_proyecto_y_sucursal(self) -> None:
        nombres = {t["nombre"] for t in self.client.get(self.url).data}
        self.assertEqual(nombres, {"Proyecto", "Sucursal"})

    def test_etiquetas_y_opciones_iniciales(self) -> None:
        filas = {t["nombre"]: t for t in self.client.get(self.url).data}
        self.assertEqual(filas["Sucursal"]["nombre_plural"], "Sucursales")
        self.assertTrue(filas["Proyecto"]["admite_tareas"])
        # No hay un interruptor de "filtro" por tipo: en el móvil se puede filtrar por cualquiera.
        self.assertNotIn("es_filtro_contexto", filas["Proyecto"])
        self.assertTrue(filas["Proyecto"]["activo"])


class AccesoTiposTests(TiposBase):
    def test_sin_sesion_401(self) -> None:
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_usuario_sin_rol_ni_entidades_403(self) -> None:
        self.client.force_authenticate(usuario("recien_registrado"))
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)

    def test_un_miembro_puede_ver_los_tipos(self) -> None:
        ana = usuario("ana")
        miembro(ana, entidad(), COLABORADOR)
        self.client.force_authenticate(ana)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)

    def test_un_miembro_inactivo_ya_no_los_ve(self) -> None:
        ana = usuario("ana")
        miembro(ana, entidad(), COLABORADOR, activa=False)
        self.client.force_authenticate(ana)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)

    def test_un_miembro_no_puede_escribir(self) -> None:
        ana = usuario("ana")
        miembro(ana, entidad(), RESPONSABLE)
        self.client.force_authenticate(ana)
        body = {"nombre": "Proveedor", "nombre_plural": "Proveedores"}
        self.assertEqual(self.client.post(self.url, body).status_code, status.HTTP_403_FORBIDDEN)
        r = self.client.patch(self.detalle("Proyecto"), {"activo": False})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(self.detalle("Sucursal")).status_code, 403)

    def test_superusuario_accede(self) -> None:
        self.client.force_authenticate(self.dev)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)


class GestionTiposTests(TiposBase):
    def test_crear_un_tipo_nuevo(self) -> None:
        body = {"nombre": "Proveedor", "nombre_plural": "Proveedores", "admite_tareas": False}
        r = self.client.post(self.url, body)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["nombre"], "Proveedor")
        self.assertFalse(r.data["admite_tareas"])
        self.assertTrue(r.data["activo"])
        self.assertEqual(r.data["total_entidades"], 0)

    def test_el_nombre_es_unico_sin_importar_mayusculas(self) -> None:
        r = self.client.post(self.url, {"nombre": "PROYECTO", "nombre_plural": "X"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", r.data)

    def test_nombre_vacio_o_faltante(self) -> None:
        for body in ({"nombre": "  ", "nombre_plural": "X"}, {"nombre_plural": "X"}, {}):
            r = self.client.post(self.url, body)
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_editar_un_tipo(self) -> None:
        r = self.client.patch(
            self.detalle("Sucursal"), {"admite_tareas": False, "nombre_plural": "Locales"}
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        tipo = TipoEntidad.objects.get(nombre="Sucursal")
        self.assertEqual((tipo.admite_tareas, tipo.nombre_plural), (False, "Locales"))

    def test_renombrar_con_el_mismo_nombre_es_valido(self) -> None:
        r = self.client.patch(self.detalle("Sucursal"), {"nombre": "Sucursal"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_no_se_puede_tomar_el_nombre_de_otro_tipo(self) -> None:
        r = self.client.patch(self.detalle("Sucursal"), {"nombre": "proyecto"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_el_total_de_entidades(self) -> None:
        entidad("Alfa")
        entidad("Beta")
        filas = {t["nombre"]: t for t in self.client.get(self.url).data}
        self.assertEqual(filas["Proyecto"]["total_entidades"], 2)
        self.assertEqual(filas["Sucursal"]["total_entidades"], 0)

    def test_eliminar_un_tipo_sin_entidades(self) -> None:
        r = self.client.delete(self.detalle("Sucursal"))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(TipoEntidad.objects.filter(nombre="Sucursal").exists())

    def test_no_se_elimina_un_tipo_con_entidades(self) -> None:
        entidad("Alfa", "Proyecto")
        r = self.client.delete(self.detalle("Proyecto"))
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(TipoEntidad.objects.filter(nombre="Proyecto").exists())

    def test_un_tipo_con_entidades_se_puede_desactivar(self) -> None:
        entidad("Alfa", "Proyecto")
        r = self.client.patch(self.detalle("Proyecto"), {"activo": False})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertFalse(r.data["activo"])

    def test_no_hay_put(self) -> None:
        r = self.client.put(self.detalle("Sucursal"), {"nombre": "X", "nombre_plural": "Y"})
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
