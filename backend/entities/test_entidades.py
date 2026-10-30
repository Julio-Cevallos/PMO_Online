from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Entidad, TipoEntidad
from .utiles_pruebas import (
    AUDITOR,
    COLABORADOR,
    PLANIFICADOR,
    RESPONSABLE,
    entidad,
    miembro,
    usuario,
)


class EntidadesBase(APITestCase):
    def setUp(self) -> None:
        self.admin = usuario("jefe", admin=True)
        self.dev = usuario("dev", superuser=True)
        self.url = reverse("entities-list")
        self.alfa = entidad("Alfa", "Proyecto")
        self.norte = entidad("Norte", "Sucursal")
        self.client.force_authenticate(self.admin)

    def detalle(self, ent: Entidad) -> str:
        return reverse("entities-detail", args=[ent.pk])

    def como(self, user) -> None:
        self.client.force_authenticate(user)


class CrearEntidadTests(EntidadesBase):
    def body(self, **extra) -> dict:
        tipo = TipoEntidad.objects.get(nombre="Proyecto")
        return {"tipo": tipo.pk, "nombre": "Gamma", "descripcion": "Obra nueva", **extra}

    def test_el_admin_crea_una_entidad(self) -> None:
        r = self.client.post(self.url, self.body())
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual((r.data["nombre"], r.data["tipo_nombre"]), ("Gamma", "Proyecto"))
        self.assertEqual(r.data["estado"], "activa")
        self.assertEqual(r.data["creado_por"], self.admin.pk)

    def test_el_superusuario_crea(self) -> None:
        self.como(self.dev)
        self.assertEqual(self.client.post(self.url, self.body()).status_code, 201)

    def test_nace_activa_aunque_se_pida_archivada(self) -> None:
        r = self.client.post(self.url, self.body(estado="archivada"))
        self.assertEqual(r.data["estado"], "activa")

    def test_un_responsable_no_crea_entidades(self) -> None:
        ana = usuario("ana")
        miembro(ana, self.alfa, RESPONSABLE)
        self.como(ana)
        self.assertEqual(self.client.post(self.url, self.body()).status_code, 403)

    def test_sin_sesion_o_sin_rol(self) -> None:
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.url, self.body()).status_code, 401)
        self.como(usuario("recien_registrado"))
        self.assertEqual(self.client.post(self.url, self.body()).status_code, 403)

    def test_el_nombre_es_unico_por_tipo_sin_importar_mayusculas(self) -> None:
        r = self.client.post(self.url, self.body(nombre="ALFA"))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", r.data)

    def test_el_mismo_nombre_en_otro_tipo_es_valido(self) -> None:
        sucursal = TipoEntidad.objects.get(nombre="Sucursal")
        r = self.client.post(self.url, {"tipo": sucursal.pk, "nombre": "Alfa"})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_tipo_inexistente_o_inactivo(self) -> None:
        r = self.client.post(self.url, self.body(tipo=9999))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        TipoEntidad.objects.filter(nombre="Proyecto").update(activo=False)
        r = self.client.post(self.url, self.body())
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tipo", r.data)

    def test_nombre_vacio_o_faltante(self) -> None:
        for nombre in ("", "   "):
            self.assertEqual(self.client.post(self.url, self.body(nombre=nombre)).status_code, 400)
        r = self.client.post(self.url, {"tipo": TipoEntidad.objects.first().pk})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class VisibilidadTests(EntidadesBase):
    def test_cada_persona_ve_solo_sus_entidades(self) -> None:
        ana = usuario("ana")
        miembro(ana, self.alfa, COLABORADOR)
        self.como(ana)
        nombres = {e["nombre"] for e in self.client.get(self.url).data["results"]}
        self.assertEqual(nombres, {"Alfa"})

    def test_el_admin_y_el_superusuario_ven_todas(self) -> None:
        for quien in (self.admin, self.dev):
            self.como(quien)
            nombres = {e["nombre"] for e in self.client.get(self.url).data["results"]}
            self.assertEqual(nombres, {"Alfa", "Norte"})

    def test_quien_no_es_miembro_no_ve_nada(self) -> None:
        self.como(usuario("recien_registrado"))
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["results"], [])

    def test_una_entidad_ajena_da_404(self) -> None:
        ana = usuario("ana")
        miembro(ana, self.alfa, RESPONSABLE)
        self.como(ana)
        self.assertEqual(self.client.get(self.detalle(self.norte)).status_code, 404)
        r = self.client.patch(self.detalle(self.norte), {"nombre": "Hackeada"})
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_una_membresia_inactiva_quita_la_visibilidad(self) -> None:
        ana = usuario("ana")
        miembro(ana, self.alfa, COLABORADOR, activa=False)
        self.como(ana)
        self.assertEqual(self.client.get(self.url).data["results"], [])
        self.assertEqual(self.client.get(self.detalle(self.alfa)).status_code, 404)

    def test_mi_rol(self) -> None:
        ana = usuario("ana")
        miembro(ana, self.alfa, PLANIFICADOR)
        miembro(ana, self.norte, AUDITOR)
        self.como(ana)
        filas = {e["nombre"]: e for e in self.client.get(self.url).data["results"]}
        self.assertEqual(filas["Alfa"]["mi_rol"], PLANIFICADOR)
        self.assertEqual(filas["Norte"]["mi_rol"], AUDITOR)

    def test_el_admin_no_tiene_mi_rol(self) -> None:
        filas = {e["nombre"]: e for e in self.client.get(self.url).data["results"]}
        self.assertIsNone(filas["Alfa"]["mi_rol"])

    def test_una_persona_con_dos_entidades_no_duplica_resultados(self) -> None:
        ana = usuario("ana")
        miembro(ana, self.alfa, COLABORADOR)
        miembro(ana, self.norte, COLABORADOR)
        self.como(ana)
        self.assertEqual(len(self.client.get(self.url).data["results"]), 2)

    def test_filtros_por_tipo_y_estado(self) -> None:
        Entidad.objects.filter(pk=self.norte.pk).update(estado="archivada")
        tipo = TipoEntidad.objects.get(nombre="Proyecto").pk
        self.assertEqual(len(self.client.get(self.url, {"tipo": tipo}).data["results"]), 1)
        r = self.client.get(self.url, {"estado": "archivada"})
        self.assertEqual([e["nombre"] for e in r.data["results"]], ["Norte"])


class EditarEntidadTests(EntidadesBase):
    def test_el_responsable_edita_nombre_y_descripcion(self) -> None:
        ana = usuario("ana")
        miembro(ana, self.alfa, RESPONSABLE)
        self.como(ana)
        r = self.client.patch(self.detalle(self.alfa), {"nombre": "Alfa 2", "descripcion": "Nueva"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.alfa.refresh_from_db()
        self.assertEqual((self.alfa.nombre, self.alfa.descripcion), ("Alfa 2", "Nueva"))

    def test_sin_el_permiso_de_editar_da_403(self) -> None:
        for rol in (PLANIFICADOR, COLABORADOR, AUDITOR):
            user = usuario(f"u_{rol[:3].lower()}")
            miembro(user, self.alfa, rol)
            self.como(user)
            r = self.client.patch(self.detalle(self.alfa), {"nombre": "Cambiada"})
            self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN, rol)
        self.alfa.refresh_from_db()
        self.assertEqual(self.alfa.nombre, "Alfa")

    def test_el_admin_edita(self) -> None:
        r = self.client.patch(self.detalle(self.alfa), {"nombre": "Por el admin"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_el_tipo_no_cambia(self) -> None:
        sucursal = TipoEntidad.objects.get(nombre="Sucursal")
        r = self.client.patch(self.detalle(self.alfa), {"tipo": sucursal.pk, "nombre": "Alfa"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.alfa.refresh_from_db()
        self.assertEqual(self.alfa.tipo.nombre, "Proyecto")

    def test_no_se_repite_el_nombre_al_editar(self) -> None:
        entidad("Beta", "Proyecto")
        r = self.client.patch(self.detalle(self.alfa), {"nombre": "beta"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_solo_el_admin_archiva_y_reactiva(self) -> None:
        ana = usuario("ana")
        miembro(ana, self.alfa, RESPONSABLE)
        self.como(ana)
        r = self.client.patch(self.detalle(self.alfa), {"estado": "archivada"})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.como(self.admin)
        r = self.client.patch(self.detalle(self.alfa), {"estado": "archivada"})
        self.assertEqual((r.status_code, r.data["estado"]), (200, "archivada"))
        r = self.client.patch(self.detalle(self.alfa), {"estado": "activa"})
        self.assertEqual(r.data["estado"], "activa")

    def test_un_responsable_puede_reenviar_el_mismo_estado(self) -> None:
        ana = usuario("ana")
        miembro(ana, self.alfa, RESPONSABLE)
        self.como(ana)
        r = self.client.patch(self.detalle(self.alfa), {"estado": "activa", "nombre": "Alfa X"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_estado_invalido(self) -> None:
        r = self.client.patch(self.detalle(self.alfa), {"estado": "borrada"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_hay_borrado_ni_put(self) -> None:
        self.assertEqual(self.client.delete(self.detalle(self.alfa)).status_code, 405)
        self.assertEqual(self.client.put(self.detalle(self.alfa), {}).status_code, 405)
        self.assertTrue(Entidad.objects.filter(pk=self.alfa.pk).exists())
