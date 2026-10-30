from unittest.mock import patch

from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import EventoAuditoria

from .models import Entidad, Invitacion, Membresia
from .utiles_pruebas import (
    AUDITOR,
    COLABORADOR,
    PLANIFICADOR,
    RESPONSABLE,
    dar_permiso,
    entidad,
    miembro,
    usuario,
)


def acciones() -> list[str]:
    return list(EventoAuditoria.objects.order_by("id").values_list("accion", flat=True))


class InvitacionesBase(APITestCase):
    def setUp(self) -> None:
        self.admin = usuario("jefe", admin=True)
        self.alfa = entidad("Alfa", "Proyecto")
        self.beta = entidad("Beta", "Sucursal")
        self.resp = usuario("resp")
        self.plani = usuario("plani")
        self.colab = usuario("colab")
        self.ana = usuario("ana")
        miembro(self.resp, self.alfa, RESPONSABLE)
        miembro(self.plani, self.alfa, PLANIFICADOR)
        miembro(self.colab, self.alfa, COLABORADOR)
        self.url = reverse("entity-invitations", args=[self.alfa.pk])
        self.client.force_authenticate(self.resp)

    def rol(self, nombre: str) -> int:
        return Group.objects.get(name=nombre).pk

    def invitar(self, username: str = "ana", rol: str = COLABORADOR, url: str | None = None):
        return self.client.post(url or self.url, {"username": username, "rol": self.rol(rol)})

    def responder(self, quien, invitacion_id: int, accion: str):
        self.client.force_authenticate(quien)
        return self.client.post(reverse(f"invitation-{accion}", args=[invitacion_id]))


class EnviarInvitacionTests(InvitacionesBase):
    def test_se_crea_pendiente_con_quien_invita_y_el_rol(self) -> None:
        r = self.invitar()
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            (r.data["estado"], r.data["username"], r.data["rol_nombre"], r.data["entidad_nombre"]),
            ("pendiente", "ana", COLABORADOR, "Alfa"),
        )
        self.assertEqual(r.data["invitado_por_nombre"], "resp")
        self.assertIsNone(r.data["respondido_en"])
        self.assertFalse(Membresia.objects.filter(usuario=self.ana).exists())

    def test_busca_el_usuario_sin_distinguir_espacios_alrededor(self) -> None:
        self.assertEqual(self.invitar("  ana  ").status_code, 201)

    def test_usuario_inexistente_superusuario_o_desactivado_da_404(self) -> None:
        usuario("dev", superuser=True)
        inactiva = usuario("baja")
        inactiva.is_active = False
        inactiva.save()
        for nombre in ("fantasma", "dev", "baja"):
            self.assertEqual(self.invitar(nombre).status_code, 404, nombre)
        self.assertEqual(Invitacion.objects.count(), 0)

    def test_ya_es_miembro_activo_da_409(self) -> None:
        self.assertEqual(self.invitar("colab").status_code, status.HTTP_409_CONFLICT)

    def test_dos_invitaciones_pendientes_a_la_misma_entidad_da_409(self) -> None:
        self.invitar()
        self.assertEqual(self.invitar().status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Invitacion.objects.count(), 1)

    def test_se_puede_volver_a_invitar_tras_rechazar(self) -> None:
        primera = self.invitar().data["id"]
        self.responder(self.ana, primera, "reject")
        self.client.force_authenticate(self.resp)
        self.assertEqual(self.invitar().status_code, 201)

    def test_a_quien_estaba_inactivo_se_le_invita_de_nuevo(self) -> None:
        Membresia.objects.filter(usuario=self.colab).update(activa=False)
        self.assertEqual(self.invitar("colab", PLANIFICADOR).status_code, 201)

    def test_respeta_la_jerarquia_de_roles(self) -> None:
        self.assertEqual(self.invitar("ana", RESPONSABLE).status_code, 403)
        self.client.force_authenticate(self.plani)
        self.assertEqual(self.invitar().status_code, 403)  # sin permiso de gestionar miembros
        dar_permiso(PLANIFICADOR, "manage_members")
        self.assertEqual(
            self.invitar("ana", AUDITOR).status_code, 403
        )  # el Auditor solo lo da el Responsable
        self.assertEqual(self.invitar("ana", COLABORADOR).status_code, 201)

    def test_el_admin_invita_a_cualquier_rol_de_entidad(self) -> None:
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.invitar("ana", RESPONSABLE).status_code, 201)

    def test_un_rol_global_no_se_ofrece_en_invitaciones(self) -> None:
        self.client.force_authenticate(self.admin)
        r = self.client.post(self.url, {"username": "ana", "rol": self.rol("Admin")})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_en_una_entidad_ajena_o_archivada(self) -> None:
        ajena = reverse("entity-invitations", args=[self.beta.pk])
        self.assertEqual(self.invitar(url=ajena).status_code, 404)
        Entidad.objects.filter(pk=self.alfa.pk).update(estado="archivada")
        self.assertEqual(self.invitar().status_code, status.HTTP_409_CONFLICT)

    def test_solo_json_y_sin_sesion(self) -> None:
        r = self.client.post(
            self.url, {"username": "ana", "rol": self.rol(COLABORADOR)}, format="multipart"
        )
        self.assertEqual(r.status_code, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
        self.client.force_authenticate(None)
        self.assertEqual(self.invitar().status_code, status.HTTP_401_UNAUTHORIZED)


class ListarYCancelarTests(InvitacionesBase):
    def test_se_listan_las_pendientes_por_defecto(self) -> None:
        pendiente = self.invitar("ana").data["id"]
        otra = usuario("luis")
        rechazada = self.invitar("luis").data["id"]
        self.responder(otra, rechazada, "reject")
        self.client.force_authenticate(self.resp)
        ids = [i["id"] for i in self.client.get(self.url).data]
        self.assertEqual(ids, [pendiente])
        todas = {i["id"] for i in self.client.get(self.url, {"estado": "todas"}).data}
        self.assertEqual(todas, {pendiente, rechazada})
        rechazadas = [i["id"] for i in self.client.get(self.url, {"estado": "rechazada"}).data]
        self.assertEqual(rechazadas, [rechazada])

    def test_ver_la_lista_exige_poder_ver_miembros(self) -> None:
        self.client.force_authenticate(self.plani)  # el Planificador ve miembros
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.force_authenticate(self.colab)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_authenticate(self.ana)  # ni siquiera ve la entidad
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_se_cancela_y_queda_como_historial(self) -> None:
        inv = self.invitar().data["id"]
        detalle = reverse("entity-invitation-detail", args=[self.alfa.pk, inv])
        self.assertEqual(self.client.delete(detalle).status_code, status.HTTP_204_NO_CONTENT)
        invitacion = Invitacion.objects.get(pk=inv)
        self.assertEqual(invitacion.estado, "cancelada")
        self.assertIsNotNone(invitacion.respondido_en)
        self.assertEqual(self.responder(self.ana, inv, "accept").status_code, 409)
        self.client.force_authenticate(self.resp)
        self.assertEqual(self.client.delete(detalle).status_code, status.HTTP_409_CONFLICT)

    def test_no_se_cancela_la_de_un_rol_igual_o_superior_ni_sin_permiso(self) -> None:
        self.client.force_authenticate(self.admin)
        inv = self.invitar("ana", RESPONSABLE).data["id"]
        detalle = reverse("entity-invitation-detail", args=[self.alfa.pk, inv])
        self.client.force_authenticate(self.resp)
        self.assertEqual(self.client.delete(detalle).status_code, 403)
        self.client.force_authenticate(self.colab)
        self.assertEqual(self.client.delete(detalle).status_code, 403)
        self.assertEqual(Invitacion.objects.get(pk=inv).estado, "pendiente")

    def test_cancelar_una_de_otra_entidad_da_404(self) -> None:
        inv = self.invitar().data["id"]
        otra_url = reverse("entity-invitation-detail", args=[self.beta.pk, inv])
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(otra_url).status_code, 404)


class ResponderTests(InvitacionesBase):
    def test_mis_invitaciones_son_solo_las_pendientes_propias(self) -> None:
        mia = self.invitar("ana").data["id"]
        luis = usuario("luis")
        self.invitar("luis")
        self.client.force_authenticate(self.ana)
        r = self.client.get(reverse("my-invitations"))
        self.assertEqual([i["id"] for i in r.data], [mia])
        self.assertEqual(
            (r.data[0]["entidad_nombre"], r.data[0]["tipo_nombre"]), ("Alfa", "Proyecto")
        )
        self.responder(self.ana, mia, "reject")
        self.assertEqual(self.client.get(reverse("my-invitations")).data, [])
        self.client.force_authenticate(luis)
        self.assertEqual(len(self.client.get(reverse("my-invitations")).data), 1)

    def test_aceptar_crea_la_membresia_con_el_rol_invitado(self) -> None:
        inv = self.invitar("ana", PLANIFICADOR).data["id"]
        r = self.responder(self.ana, inv, "accept")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            (r.data["estado"], r.data["respondido_en"] is not None), ("aceptada", True)
        )
        m = Membresia.objects.get(usuario=self.ana, entidad=self.alfa)
        self.assertEqual((m.rol.name, m.activa, m.creado_por), (PLANIFICADOR, True, self.resp))

    def test_aceptar_reactiva_una_membresia_inactiva_con_el_nuevo_rol(self) -> None:
        Membresia.objects.filter(usuario=self.colab).update(activa=False)
        inv = self.invitar("colab", PLANIFICADOR).data["id"]
        self.responder(self.colab, inv, "accept")
        self.assertEqual(Membresia.objects.filter(usuario=self.colab).count(), 1)
        m = Membresia.objects.get(usuario=self.colab)
        self.assertEqual((m.activa, m.rol.name), (True, PLANIFICADOR))

    def test_rechazar_no_crea_membresia(self) -> None:
        inv = self.invitar().data["id"]
        r = self.responder(self.ana, inv, "reject")
        self.assertEqual((r.status_code, r.data["estado"]), (200, "rechazada"))
        self.assertFalse(Membresia.objects.filter(usuario=self.ana).exists())

    def test_no_se_responde_dos_veces(self) -> None:
        inv = self.invitar().data["id"]
        self.responder(self.ana, inv, "accept")
        self.assertEqual(self.responder(self.ana, inv, "accept").status_code, 409)
        self.assertEqual(self.responder(self.ana, inv, "reject").status_code, 409)

    def test_solo_la_persona_invitada_responde(self) -> None:
        inv = self.invitar().data["id"]
        for otro in (self.resp, self.admin, self.colab):
            self.assertEqual(self.responder(otro, inv, "accept").status_code, 404, otro.username)
            self.assertEqual(self.responder(otro, inv, "reject").status_code, 404, otro.username)
        self.assertEqual(Invitacion.objects.get(pk=inv).estado, "pendiente")

    def test_si_la_entidad_se_archivo_no_se_puede_aceptar_pero_si_rechazar(self) -> None:
        inv = self.invitar().data["id"]
        Entidad.objects.filter(pk=self.alfa.pk).update(estado="archivada")
        self.assertEqual(self.responder(self.ana, inv, "accept").status_code, 409)
        self.assertEqual(self.responder(self.ana, inv, "reject").status_code, 200)

    def test_si_ya_es_miembro_activo_al_aceptar_da_409(self) -> None:
        Membresia.objects.filter(usuario=self.colab).update(activa=False)
        inv = self.invitar("colab", PLANIFICADOR).data["id"]
        Membresia.objects.filter(usuario=self.colab).update(
            activa=True
        )  # lo reactivaron por otra vía
        self.assertEqual(self.responder(self.colab, inv, "accept").status_code, 409)

    def test_sin_sesion_da_401(self) -> None:
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("my-invitations")).status_code, 401)
        self.assertEqual(self.client.post(reverse("invitation-accept", args=[1])).status_code, 401)


class AuditoriaDeInvitacionesTests(InvitacionesBase):
    def test_enviar_aceptar_rechazar_y_cancelar_dejan_evento_en_la_entidad(self) -> None:
        a = self.invitar("ana").data["id"]
        luis = usuario("luis")
        l = self.invitar("luis").data["id"]
        usuario("marta")
        m = self.invitar("marta").data["id"]
        self.responder(self.ana, a, "accept")
        self.responder(luis, l, "reject")
        self.client.force_authenticate(self.resp)
        self.client.delete(reverse("entity-invitation-detail", args=[self.alfa.pk, m]))
        self.assertEqual(
            acciones(),
            [
                "invitacion.enviar",
                "invitacion.enviar",
                "invitacion.enviar",
                "invitacion.aceptar",
                "miembro.agregar",
                "invitacion.rechazar",
                "invitacion.cancelar",
            ],
        )
        for e in EventoAuditoria.objects.all():
            self.assertEqual((e.categoria, e.entidad_id), ("entidad", self.alfa.pk))
        enviar = EventoAuditoria.objects.filter(accion="invitacion.enviar").order_by("id").first()
        self.assertEqual(enviar.usuario_nombre, "resp")
        self.assertEqual(enviar.detalle, {"usuario": "ana", "rol": COLABORADOR})
        aceptar = EventoAuditoria.objects.get(accion="invitacion.aceptar")
        self.assertEqual(aceptar.usuario_nombre, "ana")  # quien acepta es la autora
        self.assertEqual(
            aceptar.cambios, [{"campo": "estado", "antes": "pendiente", "despues": "aceptada"}]
        )

    def test_aceptar_a_quien_estaba_inactivo_registra_la_reactivacion(self) -> None:
        Membresia.objects.filter(usuario=self.colab).update(activa=False)
        inv = self.invitar("colab", PLANIFICADOR).data["id"]
        self.responder(self.colab, inv, "accept")
        self.assertIn("miembro.reactivar", acciones())
        self.assertNotIn("miembro.agregar", acciones())

    def test_lo_rechazado_no_deja_evento(self) -> None:
        self.invitar("fantasma")  # 404
        self.invitar("colab")  # 409
        self.invitar("ana", RESPONSABLE)  # 403
        self.assertEqual(acciones(), [])

    def test_el_responsable_y_el_auditor_de_la_entidad_ven_las_invitaciones(self) -> None:
        self.invitar("ana")
        aud = usuario("aud")
        miembro(aud, self.alfa, AUDITOR)
        for quien in (self.resp, aud, self.admin):
            self.client.force_authenticate(quien)
            lista = [e["accion"] for e in self.client.get(reverse("audit-list")).data["results"]]
            self.assertIn("invitacion.enviar", lista, quien.username)

    def test_si_falla_el_registro_no_se_crea_la_invitacion(self) -> None:
        self.client.raise_request_exception = False
        with patch("entities.auditoria.registrar", side_effect=RuntimeError("falla")):
            r = self.invitar()
        self.assertEqual(r.status_code, 500)
        self.assertEqual(Invitacion.objects.count(), 0)

    def test_si_falla_el_registro_al_aceptar_no_queda_miembro_ni_respuesta(self) -> None:
        inv = self.invitar().data["id"]
        self.client.raise_request_exception = False
        with patch("entities.auditoria.registrar", side_effect=RuntimeError("falla")):
            r = self.responder(self.ana, inv, "accept")
        self.assertEqual(r.status_code, 500)
        self.assertFalse(Membresia.objects.filter(usuario=self.ana).exists())
        self.assertEqual(Invitacion.objects.get(pk=inv).estado, "pendiente")
