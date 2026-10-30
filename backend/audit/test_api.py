from datetime import UTC, datetime

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from entities.utiles_pruebas import (
    AUDITOR,
    COLABORADOR,
    PLANIFICADOR,
    RESPONSABLE,
    dar_permiso,
    entidad,
    miembro,
    usuario,
)

from .models import Categoria, EventoAuditoria


def evento(accion: str, categoria: str, ent=None, **extra) -> EventoAuditoria:
    datos = {"usuario_nombre": "ana", "accion": accion, "categoria": categoria}
    if ent is not None:
        datos.update(entidad_id=ent.pk, entidad_nombre=ent.nombre)
    return EventoAuditoria.objects.create(**{**datos, **extra})


class AuditoriaBase(APITestCase):
    """Dos entidades y un evento de cada categoría, para repartir quién ve qué."""

    def setUp(self) -> None:
        self.alfa = entidad("Alfa", "Proyecto")
        self.beta = entidad("Beta", "Sucursal")
        self.e_usuario = evento("usuario.crear", Categoria.SISTEMA)
        self.e_usuario_alfa = evento("usuario.crear", Categoria.SISTEMA, self.alfa)
        self.e_miembro_alfa = evento("miembro.agregar", Categoria.ENTIDAD, self.alfa)
        self.e_miembro_beta = evento("miembro.agregar", Categoria.ENTIDAD, self.beta)
        self.e_tipo = evento("tipo.crear", Categoria.ENTIDAD)  # administración sin entidad
        self.e_contenido_alfa = evento("tarea.crear", Categoria.CONTENIDO, self.alfa)
        self.e_contenido_beta = evento("tarea.crear", Categoria.CONTENIDO, self.beta)

        self.dev = usuario("dev", superuser=True)
        self.admin = usuario("jefe", admin=True)
        self.resp = usuario("resp")
        self.aud = usuario("aud")
        self.plani = usuario("plani")
        self.oper = usuario("oper")
        self.ajeno = usuario("ajeno")
        miembro(self.resp, self.alfa, RESPONSABLE)
        miembro(self.aud, self.alfa, AUDITOR)
        miembro(self.plani, self.alfa, PLANIFICADOR)
        miembro(self.oper, self.alfa, COLABORADOR)
        self.url = reverse("audit-list")

    def ids(self, user) -> set[int]:
        self.client.force_authenticate(user)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, status.HTTP_200_OK, user.username)
        return {e["id"] for e in r.data["results"]}

    def ids_de(self, *eventos: EventoAuditoria) -> set[int]:
        return {e.pk for e in eventos}


class VisibilidadTests(AuditoriaBase):
    def test_el_superusuario_ve_todo(self) -> None:
        self.assertEqual(
            self.ids(self.dev), set(EventoAuditoria.objects.values_list("id", flat=True))
        )

    def test_el_admin_ve_sistema_y_entidad_pero_no_el_contenido(self) -> None:
        esperado = self.ids_de(
            self.e_usuario,
            self.e_usuario_alfa,
            self.e_miembro_alfa,
            self.e_miembro_beta,
            self.e_tipo,
        )
        self.assertEqual(self.ids(self.admin), esperado)

    def test_responsable_y_auditor_ven_solo_el_de_sus_entidades(self) -> None:
        esperado = self.ids_de(self.e_miembro_alfa, self.e_contenido_alfa)
        self.assertEqual(self.ids(self.resp), esperado)
        self.assertEqual(self.ids(self.aud), esperado)

    def test_nunca_ven_las_categorias_de_sistema_ni_las_de_otra_entidad(self) -> None:
        visibles = self.ids(self.resp)
        self.assertNotIn(self.e_usuario_alfa.pk, visibles)  # sistema, aunque nombre su entidad
        self.assertNotIn(self.e_miembro_beta.pk, visibles)
        self.assertNotIn(self.e_contenido_beta.pk, visibles)
        self.assertNotIn(self.e_tipo.pk, visibles)  # no pertenece a ninguna entidad

    def test_sin_permiso_da_403(self) -> None:
        for quien in (self.plani, self.oper, self.ajeno):
            self.client.force_authenticate(quien)
            self.assertEqual(self.client.get(self.url).status_code, 403, quien.username)

    def test_sin_sesion_401(self) -> None:
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_dar_el_permiso_a_un_rol_le_da_acceso_a_sus_entidades(self) -> None:
        dar_permiso(PLANIFICADOR, "view_entity_log")
        self.assertEqual(
            self.ids(self.plani), self.ids_de(self.e_miembro_alfa, self.e_contenido_alfa)
        )

    def test_una_membresia_inactiva_pierde_el_acceso(self) -> None:
        self.aud.membresias.update(activa=False)
        self.client.force_authenticate(self.aud)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_quien_es_miembro_de_dos_entidades_ve_ambas(self) -> None:
        miembro(self.resp, self.beta, RESPONSABLE)
        esperado = self.ids_de(
            self.e_miembro_alfa, self.e_contenido_alfa, self.e_miembro_beta, self.e_contenido_beta
        )
        self.assertEqual(self.ids(self.resp), esperado)

    def test_el_rol_en_cada_entidad_manda(self) -> None:
        miembro(self.plani, self.beta, AUDITOR)  # Planificador en Alfa, Auditor en Beta
        self.assertEqual(
            self.ids(self.plani), self.ids_de(self.e_miembro_beta, self.e_contenido_beta)
        )

    def test_un_admin_que_ademas_es_responsable_suma_lo_de_ambos(self) -> None:
        miembro(self.admin, self.alfa, RESPONSABLE)
        visibles = self.ids(self.admin)
        self.assertIn(self.e_usuario.pk, visibles)  # como Admin
        self.assertIn(self.e_contenido_alfa.pk, visibles)  # como Responsable de Alfa
        self.assertNotIn(self.e_contenido_beta.pk, visibles)

    def test_el_detalle_respeta_el_mismo_alcance(self) -> None:
        self.client.force_authenticate(self.resp)
        propio = reverse("audit-detail", args=[self.e_miembro_alfa.pk])
        ajeno = reverse("audit-detail", args=[self.e_miembro_beta.pk])
        self.assertEqual(self.client.get(propio).status_code, 200)
        self.assertEqual(self.client.get(ajeno).status_code, 404)

    def test_el_detalle_sin_permiso_da_403(self) -> None:
        self.client.force_authenticate(self.oper)
        r = self.client.get(reverse("audit-detail", args=[self.e_miembro_alfa.pk]))
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)


class SoloLecturaTests(AuditoriaBase):
    def test_no_hay_escritura_ni_para_el_superusuario(self) -> None:
        self.client.force_authenticate(self.dev)
        detalle = reverse("audit-detail", args=[self.e_usuario.pk])
        self.assertEqual(self.client.post(self.url, {"accion": "x"}).status_code, 405)
        self.assertEqual(self.client.patch(detalle, {"accion": "x"}).status_code, 405)
        self.assertEqual(self.client.put(detalle, {"accion": "x"}).status_code, 405)
        self.assertEqual(self.client.delete(detalle).status_code, 405)
        self.assertEqual(EventoAuditoria.objects.get(pk=self.e_usuario.pk).accion, "usuario.crear")


class ContenidoYFiltrosTests(AuditoriaBase):
    def setUp(self) -> None:
        super().setUp()
        self.client.force_authenticate(self.dev)

    def buscar(self, **filtros) -> set[int]:
        r = self.client.get(self.url, filtros)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        return {e["id"] for e in r.data["results"]}

    def test_los_campos_del_evento(self) -> None:
        creado = evento(
            "entidad.editar",
            Categoria.ENTIDAD,
            self.alfa,
            usuario_id=7,
            ip="10.0.0.9",
            objeto_tipo="entities.entidad",
            objeto_id="3",
            objeto_nombre="Alfa",
            cambios=[{"campo": "nombre", "antes": "A", "despues": "B"}],
            detalle={"origen": "web"},
        )
        fila = self.client.get(reverse("audit-detail", args=[creado.pk])).data
        self.assertEqual(fila["categoria_nombre"], "Entidad")
        self.assertEqual(fila["usuario_id"], 7)
        self.assertEqual(fila["ip"], "10.0.0.9")
        self.assertEqual(fila["entidad_nombre"], "Alfa")
        self.assertEqual(fila["cambios"], [{"campo": "nombre", "antes": "A", "despues": "B"}])
        self.assertEqual(fila["detalle"], {"origen": "web"})

    def test_los_mas_recientes_primero(self) -> None:
        orden = [e["id"] for e in self.client.get(self.url).data["results"]]
        self.assertEqual(orden, sorted(orden, reverse=True))

    def test_esta_paginado(self) -> None:
        r = self.client.get(self.url)
        self.assertEqual(r.data["count"], 7)
        self.assertIn("results", r.data)

    def test_filtrar_por_categoria(self) -> None:
        self.assertEqual(
            self.buscar(categoria="contenido"),
            self.ids_de(self.e_contenido_alfa, self.e_contenido_beta),
        )

    def test_filtrar_por_entidad(self) -> None:
        self.assertEqual(
            self.buscar(entidad=self.beta.pk),
            self.ids_de(self.e_miembro_beta, self.e_contenido_beta),
        )

    def test_filtrar_por_accion_con_prefijo(self) -> None:
        self.assertEqual(
            self.buscar(accion="usuario."), self.ids_de(self.e_usuario, self.e_usuario_alfa)
        )
        self.assertEqual(self.buscar(accion="tipo.crear"), self.ids_de(self.e_tipo))

    def test_filtrar_por_usuario(self) -> None:
        otro = evento("usuario.editar", Categoria.SISTEMA, usuario_id=99)
        self.assertEqual(self.buscar(usuario=99), self.ids_de(otro))

    def test_filtrar_por_objeto(self) -> None:
        marcado = evento("rol.editar", Categoria.SISTEMA, objeto_tipo="auth.group", objeto_id="5")
        self.assertEqual(self.buscar(objeto_tipo="auth.group", objeto_id="5"), self.ids_de(marcado))

    def test_filtrar_por_fechas(self) -> None:
        viejo = evento(
            "usuario.crear", Categoria.SISTEMA, ocurrido_en=datetime(2026, 1, 15, 12, tzinfo=UTC)
        )
        self.assertEqual(self.buscar(hasta="2026-01-31"), self.ids_de(viejo))
        self.assertEqual(self.buscar(desde="2026-01-15", hasta="2026-01-15"), self.ids_de(viejo))
        self.assertNotIn(viejo.pk, self.buscar(desde="2026-02-01"))

    def test_los_filtros_no_amplian_lo_que_se_ve(self) -> None:
        self.client.force_authenticate(self.resp)
        # Pide la categoría de sistema y la entidad de otra persona: no obtiene nada.
        self.assertEqual(self.buscar(categoria="sistema"), set())
        self.assertEqual(self.buscar(entidad=self.beta.pk), set())

    def test_filtro_invalido(self) -> None:
        r = self.client.get(self.url, {"desde": "no-es-fecha"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
