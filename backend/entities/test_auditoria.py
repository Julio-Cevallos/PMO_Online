import json
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import EventoAuditoria

from .models import Entidad, Membresia, TipoEntidad
from .utiles_pruebas import (
    AUDITOR,
    COLABORADOR,
    PASSWORD,
    PLANIFICADOR,
    RESPONSABLE,
    entidad,
    miembro,
    usuario,
)


def eventos(*prefijos: str):
    consulta = EventoAuditoria.objects.order_by("id")
    if prefijos:
        ids = [e.pk for e in consulta if e.accion.startswith(prefijos)]
        return consulta.filter(pk__in=ids)
    return consulta


def por_campo(evento: EventoAuditoria) -> dict:
    return {c["campo"]: (c["antes"], c["despues"]) for c in evento.cambios}


class TiposAuditadosTests(APITestCase):
    def setUp(self) -> None:
        self.admin = usuario("jefe", admin=True)
        self.client.force_authenticate(self.admin)
        self.url = reverse("entity-types-list")

    def detalle(self, nombre: str) -> str:
        return reverse("entity-types-detail", args=[TipoEntidad.objects.get(nombre=nombre).pk])

    def test_crear_un_tipo(self) -> None:
        self.client.post(self.url, {"nombre": "Proveedor", "nombre_plural": "Proveedores"})
        (e,) = eventos("tipo.crear")
        self.assertEqual(
            (e.categoria, e.usuario_nombre, e.objeto_tipo),
            ("entidad", "jefe", "entities.tipoentidad"),
        )
        self.assertEqual(por_campo(e)["nombre"], (None, "Proveedor"))

    def test_los_tipos_no_pertenecen_a_ninguna_entidad(self) -> None:
        self.client.post(self.url, {"nombre": "Proveedor", "nombre_plural": "Proveedores"})
        (e,) = eventos("tipo.crear")
        self.assertIsNone(e.entidad_id)

    def test_editar_un_tipo_registra_lo_que_cambio(self) -> None:
        self.client.patch(self.detalle("Sucursal"), {"nombre_plural": "Locales", "activo": False})
        (e,) = eventos("tipo.editar")
        self.assertEqual(
            por_campo(e), {"nombre_plural": ("Sucursales", "Locales"), "activo": (True, False)}
        )

    def test_un_cambio_que_no_cambia_nada_no_deja_evento(self) -> None:
        self.client.patch(self.detalle("Sucursal"), {"nombre": "Sucursal", "activo": True})
        self.assertEqual(eventos().count(), 0)

    def test_eliminar_un_tipo(self) -> None:
        identificador = TipoEntidad.objects.get(nombre="Sucursal").pk
        r = self.client.delete(self.detalle("Sucursal"))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        (e,) = eventos("tipo.eliminar")
        self.assertEqual((e.objeto_id, e.objeto_nombre), (str(identificador), "Sucursal"))

    def test_lo_rechazado_no_deja_evento(self) -> None:
        entidad("Alfa", "Proyecto")
        self.client.delete(self.detalle("Proyecto"))  # 409: tiene entidades
        self.client.post(self.url, {"nombre": "proyecto", "nombre_plural": "X"})  # 400: repetido
        self.client.force_authenticate(usuario("ana"))
        self.client.post(self.url, {"nombre": "Otro", "nombre_plural": "Otros"})  # 403
        self.assertEqual(eventos().count(), 0)

    def test_si_falla_el_registro_el_tipo_no_se_crea(self) -> None:
        self.client.raise_request_exception = False
        with patch("entities.auditoria.registrar", side_effect=RuntimeError("falla")):
            r = self.client.post(self.url, {"nombre": "Proveedor", "nombre_plural": "Proveedores"})
        self.assertEqual(r.status_code, 500)
        self.assertFalse(TipoEntidad.objects.filter(nombre="Proveedor").exists())


class EntidadesAuditadasTests(APITestCase):
    def setUp(self) -> None:
        self.admin = usuario("jefe", admin=True)
        self.resp = usuario("resp")
        self.plani = usuario("plani")
        self.alfa = entidad("Alfa", "Proyecto")
        miembro(self.resp, self.alfa, RESPONSABLE)
        miembro(self.plani, self.alfa, PLANIFICADOR)
        self.detalle = reverse("entities-detail", args=[self.alfa.pk])

    def test_crear_una_entidad(self) -> None:
        self.client.force_authenticate(self.admin)
        tipo = TipoEntidad.objects.get(nombre="Sucursal")
        r = self.client.post(reverse("entities-list"), {"tipo": tipo.pk, "nombre": "Norte"})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        (e,) = eventos("entidad.crear")
        self.assertEqual(
            (e.categoria, e.usuario_nombre, e.entidad_id), ("entidad", "jefe", r.data["id"])
        )
        self.assertEqual((e.entidad_nombre, e.objeto_nombre), ("Norte", "Sucursal: Norte"))
        self.assertEqual(por_campo(e)["tipo"], (None, "Sucursal"))

    def test_el_responsable_edita_y_queda_como_autor(self) -> None:
        self.client.force_authenticate(self.resp)
        self.client.patch(self.detalle, {"nombre": "Alfa 2", "descripcion": "Nueva"})
        (e,) = eventos("entidad.editar")
        self.assertEqual((e.usuario_nombre, e.entidad_id), ("resp", self.alfa.pk))
        self.assertEqual(por_campo(e), {"nombre": ("Alfa", "Alfa 2"), "descripcion": ("", "Nueva")})

    def test_archivar_y_reactivar_tienen_su_propia_accion(self) -> None:
        self.client.force_authenticate(self.admin)
        self.client.patch(self.detalle, {"estado": "archivada"})
        self.client.patch(self.detalle, {"estado": "activa"})
        (archivar,) = eventos("entidad.archivar")
        (reactivar,) = eventos("entidad.reactivar")
        self.assertEqual(por_campo(archivar), {"estado": ("activa", "archivada")})
        self.assertEqual(por_campo(reactivar), {"estado": ("archivada", "activa")})
        self.assertEqual(eventos("entidad.editar").count(), 0)

    def test_un_cambio_mixto_genera_un_evento_por_tipo(self) -> None:
        self.client.force_authenticate(self.admin)
        self.client.patch(self.detalle, {"estado": "archivada", "descripcion": "Cerrada"})
        self.assertEqual(eventos("entidad.archivar").count(), 1)
        (e,) = eventos("entidad.editar")
        self.assertEqual(list(por_campo(e)), ["descripcion"])

    def test_lo_rechazado_no_deja_evento(self) -> None:
        self.client.force_authenticate(self.plani)
        self.client.patch(self.detalle, {"nombre": "Hackeada"})  # 403: sin permiso de editar
        self.client.force_authenticate(self.resp)
        self.client.patch(self.detalle, {"estado": "archivada"})  # 403: solo el Admin archiva
        self.client.patch(self.detalle, {"nombre": ""})  # 400
        tipo = TipoEntidad.objects.get(nombre="Proyecto")
        self.client.post(reverse("entities-list"), {"tipo": tipo.pk, "nombre": "Nueva"})  # 403
        self.assertEqual(eventos().count(), 0)

    def test_si_falla_el_registro_el_cambio_se_deshace(self) -> None:
        self.client.force_authenticate(self.resp)
        self.client.raise_request_exception = False
        with patch("entities.auditoria.registrar", side_effect=RuntimeError("falla")):
            r = self.client.patch(self.detalle, {"nombre": "Alfa 2"})
        self.assertEqual(r.status_code, 500)
        self.alfa.refresh_from_db()
        self.assertEqual(self.alfa.nombre, "Alfa")


class MiembrosAuditadosTests(APITestCase):
    def setUp(self) -> None:
        self.admin = usuario("jefe", admin=True)
        self.resp = usuario("resp")
        self.oper = usuario("oper")
        self.alfa = entidad("Alfa", "Proyecto")
        self.m_resp = miembro(self.resp, self.alfa, RESPONSABLE)
        self.m_oper = miembro(self.oper, self.alfa, COLABORADOR)
        self.url = reverse("entity-members", args=[self.alfa.pk])
        self.client.force_authenticate(self.resp)

    def rol(self, nombre: str) -> int:
        return Group.objects.get(name=nombre).pk

    def detalle(self, m: Membresia) -> str:
        return reverse("entity-member-detail", args=[self.alfa.pk, m.pk])

    def test_crear_una_cuenta_registra_la_cuenta_y_el_miembro(self) -> None:
        r = self.client.post(
            self.url,
            {"new_user": {"username": "nueva", "password": PASSWORD}, "rol": self.rol(COLABORADOR)},
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        (cuenta,) = eventos("usuario.crear")
        (agregado,) = eventos("miembro.agregar")
        self.assertEqual((cuenta.categoria, cuenta.usuario_nombre), ("sistema", "resp"))
        self.assertEqual(cuenta.detalle, {"entidad": self.alfa.pk})
        self.assertTrue(agregado.detalle["cuenta_nueva"])
        self.assertNotIn(PASSWORD, json.dumps([cuenta.cambios, cuenta.detalle, agregado.cambios]))

    def test_cambiar_el_rol(self) -> None:
        self.client.patch(self.detalle(self.m_oper), {"rol": self.rol(PLANIFICADOR)})
        (e,) = eventos("miembro.cambiar_rol")
        self.assertEqual(por_campo(e), {"rol": (COLABORADOR, PLANIFICADOR)})
        self.assertEqual((e.entidad_id, e.usuario_nombre), (self.alfa.pk, "resp"))
        self.assertEqual(e.detalle["usuario"], "oper")

    def test_desactivar_y_reactivar(self) -> None:
        self.client.delete(self.detalle(self.m_oper))
        self.client.patch(self.detalle(self.m_oper), {"activa": True})
        (desactivar,) = eventos("miembro.desactivar")
        (reactivar,) = eventos("miembro.reactivar")
        self.assertEqual(por_campo(desactivar), {"activa": (True, False)})
        self.assertEqual(por_campo(reactivar), {"activa": (False, True)})
        self.assertEqual(eventos("miembro.cambiar_rol").count(), 0)

    def test_cambiar_el_rol_y_reactivar_a_la_vez_deja_un_evento_de_cada_uno(self) -> None:
        self.client.delete(self.detalle(self.m_oper))
        self.client.patch(self.detalle(self.m_oper), {"activa": True, "rol": self.rol(AUDITOR)})
        self.assertEqual(eventos("miembro.reactivar").count(), 1)
        self.assertEqual(eventos("miembro.cambiar_rol").count(), 1)

    def test_un_cambio_que_no_cambia_nada_no_deja_evento(self) -> None:
        self.client.patch(self.detalle(self.m_oper), {"rol": self.rol(COLABORADOR), "activa": True})
        self.assertEqual(eventos().count(), 0)

    def test_lo_rechazado_no_deja_evento(self) -> None:
        usuario("ana")
        self.client.post(self.url, {"username": "ana", "rol": self.rol(RESPONSABLE)})  # 403: nivel
        self.client.post(self.url, {"username": "fantasma", "rol": self.rol(COLABORADOR)})  # 404
        self.client.post(
            self.url, {"username": "oper", "rol": self.rol(COLABORADOR)}
        )  # 409: ya es miembro
        self.client.patch(self.detalle(self.m_resp), {"activa": False})  # 403: su propia membresía
        self.client.post(
            self.url,
            {"new_user": {"username": "otra", "password": "123"}, "rol": self.rol(COLABORADOR)},
        )  # 400: clave débil
        self.assertEqual(eventos().count(), 0)

    def test_si_falla_el_registro_no_queda_el_miembro_ni_la_cuenta(self) -> None:
        self.client.raise_request_exception = False
        with patch("entities.auditoria.registrar", side_effect=RuntimeError("falla")):
            r = self.client.post(
                self.url,
                {
                    "new_user": {"username": "nueva", "password": PASSWORD},
                    "rol": self.rol(COLABORADOR),
                },
            )
        self.assertEqual(r.status_code, 500)
        self.assertEqual(usuario_existe("nueva"), False)
        self.assertEqual(Membresia.objects.filter(entidad=self.alfa).count(), 2)

    def test_si_falla_el_registro_el_cambio_de_rol_se_deshace(self) -> None:
        self.client.raise_request_exception = False
        with patch("entities.auditoria.registrar", side_effect=RuntimeError("falla")):
            r = self.client.patch(self.detalle(self.m_oper), {"rol": self.rol(PLANIFICADOR)})
        self.assertEqual(r.status_code, 500)
        self.m_oper.refresh_from_db()
        self.assertEqual(self.m_oper.rol.name, COLABORADOR)


def usuario_existe(nombre: str) -> bool:
    from accounts.models import User

    return User.objects.filter(username=nombre).exists()


class QuienVeElHistorialDeLaEntidadTests(APITestCase):
    """De punta a punta: lo que se hace en una entidad lo ve su gente, no la de otra."""

    def setUp(self) -> None:
        self.admin = usuario("jefe", admin=True)
        self.resp = usuario("resp")
        self.aud = usuario("aud")
        self.ajeno = usuario("ajeno")
        self.alfa = entidad("Alfa", "Proyecto")
        self.beta = entidad("Beta", "Sucursal")
        miembro(self.resp, self.alfa, RESPONSABLE)
        miembro(self.aud, self.alfa, AUDITOR)
        miembro(self.ajeno, self.beta, RESPONSABLE)
        # El Responsable de Alfa trabaja: crea una cuenta y la agrega.
        self.client.force_authenticate(self.resp)
        self.client.post(
            reverse("entity-members", args=[self.alfa.pk]),
            {
                "new_user": {"username": "nueva", "password": PASSWORD},
                "rol": Group.objects.get(name=COLABORADOR).pk,
            },
        )
        self.client.patch(reverse("entities-detail", args=[self.alfa.pk]), {"descripcion": "Obra"})

    def acciones(self, user) -> list[str]:
        self.client.force_authenticate(user)
        r = self.client.get(reverse("audit-list"))
        self.assertEqual(r.status_code, 200, user.username)
        return [e["accion"] for e in r.data["results"]]

    def test_el_responsable_y_el_auditor_ven_los_eventos_de_su_entidad(self) -> None:
        esperado = {"miembro.agregar", "entidad.editar"}
        self.assertEqual(set(self.acciones(self.resp)), esperado)
        self.assertEqual(set(self.acciones(self.aud)), esperado)

    def test_no_ven_la_creacion_de_la_cuenta_porque_es_de_sistema(self) -> None:
        self.assertNotIn("usuario.crear", self.acciones(self.aud))

    def test_otra_entidad_no_ve_nada_de_esta(self) -> None:
        self.assertEqual(self.acciones(self.ajeno), [])

    def test_el_admin_ve_la_administracion_incluida_la_cuenta_creada(self) -> None:
        self.assertEqual(
            set(self.acciones(self.admin)), {"usuario.crear", "miembro.agregar", "entidad.editar"}
        )

    def test_se_puede_filtrar_por_entidad(self) -> None:
        self.client.force_authenticate(self.admin)
        r = self.client.get(reverse("audit-list"), {"entidad": self.alfa.pk})
        self.assertEqual(
            {e["accion"] for e in r.data["results"]}, {"miembro.agregar", "entidad.editar"}
        )
        r = self.client.get(reverse("audit-list"), {"entidad": self.beta.pk})
        self.assertEqual(r.data["results"], [])

    def test_los_eventos_no_se_pueden_alterar_desde_la_api(self) -> None:
        self.client.force_authenticate(self.admin)
        evento = EventoAuditoria.objects.first()
        detalle = reverse("audit-detail", args=[evento.pk])
        self.assertEqual(self.client.delete(detalle).status_code, 405)
        self.assertEqual(Entidad.objects.filter(pk=self.alfa.pk).count(), 1)
