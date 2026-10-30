"""Portafolios (D-29): grupos de entidades que varias personas gestionan en conjunto."""

from unittest.mock import patch

from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from audit.models import EventoAuditoria

from .models import Entidad, InvitacionPortafolio, MembresiaPortafolio, Portafolio, TipoEntidad
from .utiles_pruebas import (
    COLABORADOR,
    PASSWORD,
    RESPONSABLE,
    entidad,
    miembro,
    moderador,
    usuario,
)

GESTOR = "Gestor del portafolio"
COORDINADOR = "Coordinador"


class PortafolioBase(APITestCase):
    """Un portafolio «Norte» de un Moderador, con un segundo Gestor y un Coordinador."""

    def setUp(self) -> None:
        self.admin = usuario("jefe", admin=True)
        self.dev = usuario("dev", superuser=True)
        self.mod = moderador("mod")
        self.gestor2 = usuario("gestor2")
        self.coord = usuario("coord")
        self.ajeno = usuario("ajeno")
        self.tipo = TipoEntidad.objects.get(nombre="Proyecto").pk
        self.client.force_authenticate(self.mod)
        self.norte = self.crear_portafolio("Norte")
        self.sumar(self.gestor2, GESTOR)
        self.sumar(self.coord, COORDINADOR)

    def rol(self, nombre: str) -> int:
        return Group.objects.get(name=nombre).pk

    def crear_portafolio(self, nombre: str) -> Portafolio:
        r = self.client.post(reverse("portfolios-list"), {"nombre": nombre})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        return Portafolio.objects.get(pk=r.data["id"])

    def sumar(self, user: User, rol: str) -> None:
        """Suma a `user` al portafolio Norte por invitación aceptada, como lo haría la web."""
        self.client.force_authenticate(self.mod)
        r = self.client.post(
            reverse("portfolio-invitations", args=[self.norte.pk]),
            {"username": user.username, "rol": self.rol(rol)},
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.client.force_authenticate(user)
        r = self.client.post(reverse("portfolio-invitation-accept", args=[r.data["id"]]))
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.client.force_authenticate(self.mod)

    def crear_entidad(self, user: User, nombre: str, portafolio: Portafolio | None = None):
        self.client.force_authenticate(user)
        cuerpo = {"tipo": self.tipo, "nombre": nombre}
        if portafolio is not None:
            cuerpo["portafolio"] = portafolio.pk
        return self.client.post(reverse("entities-list"), cuerpo)

    def nombres(self, user: User) -> list[str]:
        self.client.force_authenticate(user)
        return sorted(
            e["nombre"] for e in self.client.get(reverse("entities-list")).data["results"]
        )


class CrearYVerPortafoliosTests(PortafolioBase):
    def test_el_moderador_crea_y_queda_como_gestor(self) -> None:
        m = MembresiaPortafolio.objects.get(usuario=self.mod, portafolio=self.norte)
        self.assertEqual((m.rol.name, m.activa), (GESTOR, True))
        self.assertFalse(self.norte.personal)

    def test_el_admin_tambien_crea(self) -> None:
        self.client.force_authenticate(self.admin)
        r = self.client.post(reverse("portfolios-list"), {"nombre": "Sur"})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_quien_no_es_admin_ni_moderador_no_crea(self) -> None:
        self.client.force_authenticate(self.coord)
        r = self.client.post(reverse("portfolios-list"), {"nombre": "Sur"})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_el_nombre_es_unico_sin_distinguir_mayusculas_y_no_vacio(self) -> None:
        self.client.force_authenticate(self.mod)
        url = reverse("portfolios-list")
        self.assertEqual(self.client.post(url, {"nombre": "norte"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"nombre": "   "}).status_code, 400)
        self.assertEqual(self.client.post(url, {}).status_code, 400)

    def test_cada_persona_ve_solo_sus_portafolios_y_el_admin_todos(self) -> None:
        otro = moderador("otro_mod")
        self.client.force_authenticate(otro)
        self.client.post(reverse("portfolios-list"), {"nombre": "Ajeno"})

        def nombres(user) -> list[str]:
            self.client.force_authenticate(user)
            return sorted(p["nombre"] for p in self.client.get(reverse("portfolios-list")).data)

        self.assertEqual(nombres(self.coord), ["Norte"])
        self.assertEqual(nombres(self.ajeno), [])
        self.assertEqual(nombres(self.admin), ["Ajeno", "Norte"])
        detalle = reverse("portfolios-detail", args=[self.norte.pk])
        self.client.force_authenticate(self.ajeno)
        self.assertEqual(self.client.get(detalle).status_code, 404)

    def test_las_capacidades_de_cada_rol(self) -> None:
        def caps(user) -> dict:
            self.client.force_authenticate(user)
            d = self.client.get(reverse("portfolios-detail", args=[self.norte.pk])).data
            return {
                c: d[c]
                for c in (
                    "puede_editar",
                    "puede_eliminar",
                    "puede_crear_entidades",
                    "puede_ver_miembros",
                    "puede_gestionar_miembros",
                    "puede_ver_historial",
                )
            }

        todo = {c: True for c in caps(self.mod)}
        self.assertEqual(caps(self.admin), todo)
        self.assertEqual(caps(self.gestor2)["puede_gestionar_miembros"], True)
        coord = caps(self.coord)
        self.assertEqual(
            coord,
            {
                "puede_editar": False,
                "puede_eliminar": False,
                "puede_crear_entidades": True,
                "puede_ver_miembros": True,
                "puede_gestionar_miembros": False,
                "puede_ver_historial": True,
            },
        )
        self.assertEqual(
            self.client.get(reverse("portfolios-detail", args=[self.norte.pk])).data["mi_rol"],
            COORDINADOR,
        )

    def test_el_total_de_entidades(self) -> None:
        self.crear_entidad(self.coord, "A", self.norte)
        self.crear_entidad(self.coord, "B", self.norte)
        self.client.force_authenticate(self.mod)
        d = self.client.get(reverse("portfolios-detail", args=[self.norte.pk])).data
        self.assertEqual(d["total_entidades"], 2)


class EditarYEliminarTests(PortafolioBase):
    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("portfolios-detail", args=[self.norte.pk])

    def test_el_gestor_edita_y_el_coordinador_no(self) -> None:
        self.client.force_authenticate(self.gestor2)
        r = self.client.patch(self.url, {"descripcion": "Zona norte"})
        self.assertEqual(r.status_code, 200)
        self.client.force_authenticate(self.coord)
        self.assertEqual(self.client.patch(self.url, {"descripcion": "x"}).status_code, 403)

    def test_se_elimina_si_esta_vacio_y_con_entidades_da_409(self) -> None:
        self.crear_entidad(self.coord, "A", self.norte)
        self.client.force_authenticate(self.mod)
        self.assertEqual(self.client.delete(self.url).status_code, status.HTTP_409_CONFLICT)
        Entidad.objects.all().delete()
        self.assertEqual(self.client.delete(self.url).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Portafolio.objects.filter(pk=self.norte.pk).exists())

    def test_el_coordinador_no_elimina(self) -> None:
        self.client.force_authenticate(self.coord)
        self.assertEqual(self.client.delete(self.url).status_code, 403)

    def test_el_personal_no_se_renombra_ni_se_elimina(self) -> None:
        self.assertEqual(self.crear_entidad(self.mod, "Mia").status_code, 201)
        personal = Portafolio.objects.get(personal=True, creado_por=self.mod)
        url = reverse("portfolios-detail", args=[personal.pk])
        self.client.force_authenticate(self.mod)
        self.assertEqual(self.client.patch(url, {"nombre": "Otro"}).status_code, 400)
        self.assertEqual(self.client.patch(url, {"descripcion": "ok"}).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_409_CONFLICT)

    def test_solo_acepta_json(self) -> None:
        self.client.force_authenticate(self.mod)
        r = self.client.post(reverse("portfolios-list"), {"nombre": "X"}, format="multipart")
        self.assertEqual(r.status_code, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)


class EntidadesDelPortafolioTests(PortafolioBase):
    def test_el_coordinador_sin_rol_global_crea_entidades_en_el_portafolio(self) -> None:
        r = self.crear_entidad(self.coord, "Obra 1", self.norte)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(
            (r.data["portafolio"], r.data["portafolio_nombre"]), (self.norte.pk, "Norte")
        )

    def test_todos_los_del_portafolio_ven_todas_sus_entidades(self) -> None:
        self.crear_entidad(self.coord, "Obra 1", self.norte)
        self.crear_entidad(self.mod, "Obra 2", self.norte)
        for user in (self.mod, self.gestor2, self.coord):
            self.assertEqual(self.nombres(user), ["Obra 1", "Obra 2"], user.username)
        self.assertEqual(self.nombres(self.ajeno), [])

    def test_sin_portafolio_el_moderador_usa_el_personal_y_se_reutiliza(self) -> None:
        self.crear_entidad(self.mod, "A")
        self.crear_entidad(self.mod, "B")
        personales = Portafolio.objects.filter(personal=True, creado_por=self.mod)
        self.assertEqual(personales.count(), 1)
        self.assertEqual(personales.get().entidades.count(), 2)
        self.assertEqual(personales.get().nombre, "Mis entidades")

    def test_el_coordinador_sin_rol_global_debe_elegir_portafolio(self) -> None:
        self.assertEqual(self.crear_entidad(self.coord, "X").status_code, 403)

    def test_no_se_crea_en_un_portafolio_ajeno_ni_inexistente(self) -> None:
        otro = moderador("otro_mod")
        self.client.force_authenticate(otro)
        ajeno = Portafolio.objects.get(pk=self.crear_portafolio_de(otro, "Otro").pk)
        self.assertEqual(self.crear_entidad(self.mod, "X", ajeno).status_code, 403)
        self.client.force_authenticate(self.mod)
        r = self.client.post(
            reverse("entities-list"), {"tipo": self.tipo, "nombre": "Y", "portafolio": 99999}
        )
        self.assertEqual(r.status_code, 400)

    def crear_portafolio_de(self, user: User, nombre: str) -> Portafolio:
        self.client.force_authenticate(user)
        r = self.client.post(reverse("portfolios-list"), {"nombre": nombre})
        return Portafolio.objects.get(pk=r.data["id"])

    def test_el_coordinador_edita_pero_no_archiva_y_el_gestor_si(self) -> None:
        e = Entidad.objects.get(pk=self.crear_entidad(self.coord, "Obra", self.norte).data["id"])
        url = reverse("entities-detail", args=[e.pk])
        self.client.force_authenticate(self.coord)
        self.assertEqual(self.client.patch(url, {"descripcion": "A"}).status_code, 200)
        self.assertEqual(self.client.patch(url, {"estado": "archivada"}).status_code, 403)
        d = self.client.get(url).data
        self.assertEqual(
            (d["puede_editar"], d["puede_archivar"], d["puede_mover"]), (True, False, False)
        )
        self.client.force_authenticate(self.gestor2)
        self.assertEqual(self.client.patch(url, {"estado": "archivada"}).status_code, 200)
        d = self.client.get(url).data
        self.assertEqual((d["puede_archivar"], d["puede_mover"]), (True, True))

    def test_el_coordinador_gestiona_los_miembros_de_las_entidades_con_cualquier_rol(self) -> None:
        e = Entidad.objects.get(pk=self.crear_entidad(self.mod, "Obra", self.norte).data["id"])
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            reverse("entity-members", args=[e.pk]),
            {"new_user": {"username": "resp", "password": PASSWORD}, "rol": self.rol(RESPONSABLE)},
        )
        self.assertEqual(r.status_code, 201, r.data)
        roles = self.client.get(reverse("entity-assignable-roles", args=[e.pk])).data
        nombres = [x["name"] for x in roles]
        self.assertIn(RESPONSABLE, nombres)
        self.assertNotIn(GESTOR, nombres)  # un rol de portafolio no se asigna a una entidad
        usuario("ana")
        r = self.client.post(
            reverse("entity-invitations", args=[e.pk]), {"username": "ana", "rol": self.rol(GESTOR)}
        )
        self.assertEqual(r.status_code, 400)

    def test_quien_no_es_del_portafolio_no_gestiona_sus_entidades(self) -> None:
        e = Entidad.objects.get(pk=self.crear_entidad(self.mod, "Obra", self.norte).data["id"])
        self.client.force_authenticate(self.ajeno)
        self.assertEqual(self.client.get(reverse("entities-detail", args=[e.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("entity-members", args=[e.pk])).status_code, 404)

    def test_ser_miembro_de_una_entidad_no_da_acceso_al_portafolio(self) -> None:
        e = entidad("Suelta", "Proyecto", self.norte)
        miembro(self.ajeno, e, COLABORADOR)
        self.client.force_authenticate(self.ajeno)
        self.assertEqual(self.client.get(reverse("portfolios-list")).data, [])
        d = self.client.get(reverse("entities-detail", args=[e.pk])).data
        self.assertFalse(d["puede_editar"])

    def test_filtro_por_portafolio(self) -> None:
        self.crear_entidad(self.mod, "En norte", self.norte)
        self.crear_entidad(self.mod, "En personal")
        r = self.client.get(reverse("entities-list"), {"portafolio": self.norte.pk})
        self.assertEqual([e["nombre"] for e in r.data["results"]], ["En norte"])

    def test_las_sugerencias_incluyen_a_los_miembros_de_las_otras_entidades_del_portafolio(
        self,
    ) -> None:
        a = Entidad.objects.get(pk=self.crear_entidad(self.coord, "A", self.norte).data["id"])
        b = Entidad.objects.get(pk=self.crear_entidad(self.coord, "B", self.norte).data["id"])
        miembro(usuario("ana"), b, COLABORADOR)
        self.client.force_authenticate(self.coord)
        r = self.client.get(reverse("entity-candidates", args=[a.pk]))
        self.assertIn("ana", [c["username"] for c in r.data])


class MoverEntidadesTests(PortafolioBase):
    def setUp(self) -> None:
        super().setUp()
        self.sur = self.crear_portafolio("Sur")
        self.e = Entidad.objects.get(pk=self.crear_entidad(self.mod, "Obra", self.norte).data["id"])
        self.url = reverse("entities-move", args=[self.e.pk])

    def mover(self, user: User, destino: Portafolio):
        self.client.force_authenticate(user)
        return self.client.post(self.url, {"portafolio": destino.pk})

    def test_el_gestor_mueve_si_puede_crear_en_el_destino(self) -> None:
        r = self.mover(self.mod, self.sur)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["portafolio"], self.sur.pk)
        self.e.refresh_from_db()
        self.assertEqual(self.e.portafolio, self.sur)

    def test_tras_mover_la_ven_los_del_destino_y_dejan_de_verla_los_del_origen(self) -> None:
        self.mover(self.mod, self.sur)
        self.assertEqual(self.nombres(self.coord), [])
        self.assertEqual(self.nombres(self.mod), ["Obra"])

    def test_el_coordinador_no_mueve(self) -> None:
        self.assertEqual(self.mover(self.coord, self.sur).status_code, 403)

    def test_sin_permiso_en_el_destino_da_403(self) -> None:
        otro = moderador("otro_mod")
        ajeno = self.crear_portafolio_de(otro, "Ajeno")
        self.assertEqual(self.mover(self.mod, ajeno).status_code, 403)
        self.e.refresh_from_db()
        self.assertEqual(self.e.portafolio, self.norte)

    def crear_portafolio_de(self, user: User, nombre: str) -> Portafolio:
        self.client.force_authenticate(user)
        r = self.client.post(reverse("portfolios-list"), {"nombre": nombre})
        return Portafolio.objects.get(pk=r.data["id"])

    def test_al_mismo_portafolio_o_a_uno_inexistente(self) -> None:
        self.assertEqual(self.mover(self.mod, self.norte).status_code, status.HTTP_409_CONFLICT)
        self.client.force_authenticate(self.mod)
        self.assertEqual(self.client.post(self.url, {"portafolio": 99999}).status_code, 400)
        self.assertEqual(self.client.post(self.url, {}).status_code, 400)

    def test_el_admin_mueve_a_cualquier_portafolio(self) -> None:
        otro = moderador("otro_mod")
        ajeno = self.crear_portafolio_de(otro, "Ajeno")
        self.assertEqual(self.mover(self.admin, ajeno).status_code, 200)

    def test_queda_en_el_historial_del_destino(self) -> None:
        self.mover(self.mod, self.sur)
        e = EventoAuditoria.objects.get(accion="entidad.mover")
        self.assertEqual(
            (e.portafolio_id, e.portafolio_nombre, e.entidad_id), (self.sur.pk, "Sur", self.e.pk)
        )
        self.assertEqual(e.cambios, [{"campo": "portafolio", "antes": "Norte", "despues": "Sur"}])
        self.assertEqual(e.detalle, {"desde": self.norte.pk, "hacia": self.sur.pk})

    def test_una_entidad_que_no_se_ve_da_404(self) -> None:
        self.assertEqual(self.mover(self.ajeno, self.sur).status_code, 404)


class MiembrosDelPortafolioTests(PortafolioBase):
    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("portfolio-members", args=[self.norte.pk])

    def miembro(self, user: User) -> MembresiaPortafolio:
        return MembresiaPortafolio.objects.get(usuario=user, portafolio=self.norte)

    def detalle(self, user: User) -> str:
        return reverse("portfolio-member-detail", args=[self.norte.pk, self.miembro(user).pk])

    def test_se_listan_y_el_coordinador_los_ve(self) -> None:
        self.client.force_authenticate(self.coord)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            sorted((m["username"], m["rol_nombre"]) for m in r.data),
            [("coord", COORDINADOR), ("gestor2", GESTOR), ("mod", GESTOR)],
        )

    def test_quien_no_es_del_portafolio_da_404(self) -> None:
        self.client.force_authenticate(self.ajeno)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_el_gestor_cambia_roles_y_desactiva(self) -> None:
        self.client.force_authenticate(self.mod)
        r = self.client.patch(self.detalle(self.coord), {"rol": self.rol(GESTOR)})
        self.assertEqual((r.status_code, r.data["rol_nombre"]), (200, GESTOR))
        self.assertEqual(self.client.delete(self.detalle(self.gestor2)).status_code, 204)
        self.assertFalse(self.miembro(self.gestor2).activa)
        r = self.client.patch(self.detalle(self.gestor2), {"activa": True})
        self.assertEqual((r.status_code, r.data["activa"]), (200, True))

    def test_el_coordinador_no_gestiona_miembros(self) -> None:
        self.client.force_authenticate(self.coord)
        self.assertEqual(
            self.client.patch(self.detalle(self.gestor2), {"activa": False}).status_code, 403
        )
        self.assertEqual(self.client.delete(self.detalle(self.mod)).status_code, 403)

    def test_nadie_modifica_su_propia_membresia(self) -> None:
        self.client.force_authenticate(self.gestor2)
        self.assertEqual(
            self.client.patch(
                self.detalle(self.gestor2), {"rol": self.rol(COORDINADOR)}
            ).status_code,
            403,
        )
        self.assertEqual(self.client.delete(self.detalle(self.gestor2)).status_code, 403)

    def test_el_portafolio_conserva_siempre_un_gestor(self) -> None:
        self.client.force_authenticate(self.mod)
        self.client.delete(self.detalle(self.gestor2))  # queda solo el Moderador
        self.client.force_authenticate(self.admin)
        r = self.client.delete(self.detalle(self.mod))
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)
        r = self.client.patch(self.detalle(self.mod), {"rol": self.rol(COORDINADOR)})
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(self.miembro(self.mod).activa)

    def test_un_rol_de_entidad_no_se_asigna_en_un_portafolio(self) -> None:
        self.client.force_authenticate(self.mod)
        r = self.client.patch(self.detalle(self.coord), {"rol": self.rol(RESPONSABLE)})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.miembro(self.coord).rol.name, COORDINADOR)

    def test_roles_asignables(self) -> None:
        self.client.force_authenticate(self.mod)
        nombres = [
            r["name"]
            for r in self.client.get(
                reverse("portfolio-assignable-roles", args=[self.norte.pk])
            ).data
        ]
        self.assertEqual(nombres, [GESTOR, COORDINADOR])
        self.client.force_authenticate(self.coord)
        r = self.client.get(reverse("portfolio-assignable-roles", args=[self.norte.pk]))
        self.assertEqual(r.status_code, 403)

    def test_un_gestor_puede_nombrar_a_otro_gestor_pero_el_coordinador_no_a_nadie(self) -> None:
        usuario("nuevo")
        self.client.force_authenticate(self.gestor2)
        r = self.client.post(
            reverse("portfolio-invitations", args=[self.norte.pk]),
            {"username": "nuevo", "rol": self.rol(GESTOR)},
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.client.force_authenticate(self.coord)
        r = self.client.post(
            reverse("portfolio-invitations", args=[self.norte.pk]),
            {"username": "ajeno", "rol": self.rol(COORDINADOR)},
        )
        self.assertEqual(r.status_code, 403)


class InvitacionesDePortafolioTests(PortafolioBase):
    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("portfolio-invitations", args=[self.norte.pk])
        self.client.force_authenticate(self.mod)

    def invitar(self, username: str = "ajeno", rol: str = COORDINADOR):
        return self.client.post(self.url, {"username": username, "rol": self.rol(rol)})

    def responder(self, quien: User, pk: int, accion: str):
        self.client.force_authenticate(quien)
        return self.client.post(reverse(f"portfolio-invitation-{accion}", args=[pk]))

    def test_se_envia_pendiente_y_no_mete_todavia(self) -> None:
        r = self.invitar()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(
            (r.data["estado"], r.data["portafolio_nombre"], r.data["rol_nombre"]),
            ("pendiente", "Norte", COORDINADOR),
        )
        self.assertFalse(MembresiaPortafolio.objects.filter(usuario=self.ajeno).exists())

    def test_la_persona_la_ve_y_acepta(self) -> None:
        inv = self.invitar().data["id"]
        self.client.force_authenticate(self.ajeno)
        mias = self.client.get(reverse("my-portfolio-invitations")).data
        self.assertEqual([i["id"] for i in mias], [inv])
        r = self.responder(self.ajeno, inv, "accept")
        self.assertEqual((r.status_code, r.data["estado"]), (200, "aceptada"))
        m = MembresiaPortafolio.objects.get(usuario=self.ajeno, portafolio=self.norte)
        self.assertEqual((m.rol.name, m.activa), (COORDINADOR, True))
        self.assertEqual(self.nombres(self.ajeno), [])  # el portafolio aún no tiene entidades
        self.client.force_authenticate(self.ajeno)
        self.assertEqual(self.client.get(reverse("my-portfolio-invitations")).data, [])

    def test_rechazar_no_crea_membresia(self) -> None:
        inv = self.invitar().data["id"]
        r = self.responder(self.ajeno, inv, "reject")
        self.assertEqual((r.status_code, r.data["estado"]), (200, "rechazada"))
        self.assertFalse(MembresiaPortafolio.objects.filter(usuario=self.ajeno).exists())

    def test_no_se_responde_dos_veces_ni_otra_persona(self) -> None:
        inv = self.invitar().data["id"]
        for otro in (self.mod, self.admin, self.coord):
            self.assertEqual(self.responder(otro, inv, "accept").status_code, 404)
        self.responder(self.ajeno, inv, "accept")
        self.assertEqual(self.responder(self.ajeno, inv, "accept").status_code, 409)
        self.assertEqual(self.responder(self.ajeno, inv, "reject").status_code, 409)

    def test_reglas_de_alta(self) -> None:
        self.client.force_authenticate(self.mod)
        self.assertEqual(self.invitar("fantasma").status_code, 404)
        usuario("baja2").__class__.objects.filter(username="baja2").update(is_active=False)
        self.assertEqual(self.invitar("baja2").status_code, 404)
        self.assertEqual(self.invitar("dev").status_code, 404)  # superusuario
        self.assertEqual(self.invitar("coord").status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.invitar("ajeno").status_code, 201)
        self.assertEqual(self.invitar("ajeno").status_code, status.HTTP_409_CONFLICT)

    def test_se_reactiva_a_quien_estaba_inactivo_al_aceptar(self) -> None:
        MembresiaPortafolio.objects.filter(usuario=self.coord).update(activa=False)
        inv = self.invitar("coord", GESTOR).data["id"]
        self.assertFalse(MembresiaPortafolio.objects.get(usuario=self.coord).activa)
        self.responder(self.coord, inv, "accept")
        m = MembresiaPortafolio.objects.get(usuario=self.coord)
        self.assertEqual((m.activa, m.rol.name), (True, GESTOR))
        self.assertEqual(MembresiaPortafolio.objects.filter(usuario=self.coord).count(), 1)

    def test_listar_y_cancelar(self) -> None:
        inv = self.invitar().data["id"]
        self.client.force_authenticate(self.coord)
        self.assertEqual([i["id"] for i in self.client.get(self.url).data], [inv])
        self.client.force_authenticate(self.ajeno)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_authenticate(self.coord)
        detalle = reverse("portfolio-invitation-detail", args=[self.norte.pk, inv])
        self.assertEqual(self.client.delete(detalle).status_code, 403)  # no gestiona
        self.client.force_authenticate(self.mod)
        self.assertEqual(self.client.delete(detalle).status_code, 204)
        self.assertEqual(InvitacionPortafolio.objects.get(pk=inv).estado, "cancelada")
        self.assertEqual(self.client.delete(detalle).status_code, 409)
        self.assertEqual(self.responder(self.ajeno, inv, "accept").status_code, 409)

    def test_un_rol_de_entidad_no_se_ofrece_en_un_portafolio(self) -> None:
        self.assertEqual(self.invitar("ajeno", RESPONSABLE).status_code, 400)

    def test_solo_json_y_sin_sesion(self) -> None:
        r = self.client.post(
            self.url, {"username": "ajeno", "rol": self.rol(COORDINADOR)}, format="multipart"
        )
        self.assertEqual(r.status_code, 415)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("my-portfolio-invitations")).status_code, 401)


class AuditoriaDePortafoliosTests(PortafolioBase):
    def acciones(self, user: User, **filtros) -> list[str] | None:
        self.client.force_authenticate(user)
        r = self.client.get(reverse("audit-list"), filtros)
        if r.status_code == status.HTTP_403_FORBIDDEN:
            return None
        return [e["accion"] for e in r.data["results"]]

    def test_se_registran_creacion_edicion_miembros_e_invitaciones(self) -> None:
        self.client.force_authenticate(self.mod)
        self.client.patch(reverse("portfolios-detail", args=[self.norte.pk]), {"descripcion": "Z"})
        acciones = list(EventoAuditoria.objects.order_by("id").values_list("accion", flat=True))
        self.assertEqual(
            acciones,
            [
                "portafolio.crear",
                "portafolio.invitacion_enviar",
                "portafolio.invitacion_aceptar",
                "portafolio.miembro_agregar",
                "portafolio.invitacion_enviar",
                "portafolio.invitacion_aceptar",
                "portafolio.miembro_agregar",
                "portafolio.editar",
            ],
        )
        for e in EventoAuditoria.objects.all():
            self.assertEqual(
                (e.categoria, e.portafolio_id, e.portafolio_nombre),
                ("entidad", self.norte.pk, "Norte"),
            )

    def test_las_entidades_llevan_el_portafolio_en_sus_eventos(self) -> None:
        self.client.force_authenticate(self.coord)
        self.client.post(
            reverse("entities-list"),
            {"tipo": self.tipo, "nombre": "A", "portafolio": self.norte.pk},
        )
        e = EventoAuditoria.objects.get(accion="entidad.crear")
        self.assertEqual((e.portafolio_id, e.usuario_nombre), (self.norte.pk, "coord"))

    def test_los_del_portafolio_ven_su_historial_y_los_demas_no(self) -> None:
        self.crear_entidad(self.coord, "A", self.norte)
        for user in (self.mod, self.gestor2, self.coord):
            visibles = self.acciones(user)
            self.assertIn("entidad.crear", visibles, user.username)
            self.assertIn("portafolio.crear", visibles, user.username)
            self.assertNotIn("usuario.crear", visibles)
        self.assertIsNone(self.acciones(self.ajeno))
        self.assertIn("portafolio.crear", self.acciones(self.admin))

    def test_otro_portafolio_no_ve_los_eventos_de_este(self) -> None:
        otro = moderador("otro_mod")
        self.client.force_authenticate(otro)
        self.client.post(reverse("portfolios-list"), {"nombre": "Otro"})
        mios = self.acciones(otro)
        self.assertEqual(mios, ["portafolio.crear"])

    def test_se_filtra_por_portafolio(self) -> None:
        self.client.force_authenticate(self.admin)
        self.client.post(reverse("portfolios-list"), {"nombre": "Sur"})
        r = self.client.get(reverse("audit-list"), {"portafolio": self.norte.pk})
        self.assertTrue(r.data["results"])
        self.assertEqual({e["portafolio_id"] for e in r.data["results"]}, {self.norte.pk})

    def test_lo_rechazado_no_deja_evento(self) -> None:
        antes = EventoAuditoria.objects.count()
        self.client.force_authenticate(self.coord)
        self.client.patch(
            reverse("portfolios-detail", args=[self.norte.pk]), {"descripcion": "x"}
        )  # 403
        self.client.post(
            reverse("portfolio-invitations", args=[self.norte.pk]),
            {"username": "ajeno", "rol": self.rol(COORDINADOR)},
        )  # 403
        self.assertEqual(EventoAuditoria.objects.count(), antes)

    def test_si_falla_el_registro_no_se_crea_el_portafolio(self) -> None:
        self.client.raise_request_exception = False
        self.client.force_authenticate(self.mod)
        with patch("entities.auditoria.registrar", side_effect=RuntimeError("falla")):
            r = self.client.post(reverse("portfolios-list"), {"nombre": "Fallido"})
        self.assertEqual(r.status_code, 500)
        self.assertFalse(Portafolio.objects.filter(nombre="Fallido").exists())


class RolesDePortafolioTests(APITestCase):
    def setUp(self) -> None:
        self.admin = usuario("jefe", admin=True)
        self.client.force_authenticate(self.admin)
        self.url = reverse("roles-list")

    def test_los_roles_del_sistema_de_portafolio(self) -> None:
        filas = {r["name"]: r for r in self.client.get(self.url).data}
        gestor, coord = filas[GESTOR], filas[COORDINADOR]
        self.assertEqual((gestor["scope"], coord["scope"]), ("portafolio", "portafolio"))
        self.assertTrue(gestor["is_system"] and coord["is_system"])
        self.assertEqual((gestor["nivel"], coord["nivel"]), (40, 30))
        self.assertEqual(len(gestor["permissions"]), 9)
        self.assertEqual(
            coord["permissions"],
            [
                "entities.create_portfolio_entities",
                "entities.edit_portfolio_entities",
                "entities.manage_portfolio_entity_members",
                "entities.view_portfolio",
                "entities.view_portfolio_log",
            ],
        )
        self.assertEqual(filas[RESPONSABLE]["scope"], "entidad")

    def test_el_admin_ajusta_los_permisos_del_coordinador(self) -> None:
        pk = Group.objects.get(name=COORDINADOR).pk
        permisos = ["entities.view_portfolio", "entities.archive_portfolio_entities"]
        r = self.client.patch(reverse("roles-detail", args=[pk]), {"permissions": permisos})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["permissions"], sorted(permisos))

    def test_un_permiso_de_entidad_no_va_en_un_rol_de_portafolio_y_viceversa(self) -> None:
        pk = Group.objects.get(name=COORDINADOR).pk
        r = self.client.patch(
            reverse("roles-detail", args=[pk]), {"permissions": ["entities.edit_entity"]}
        )
        self.assertEqual(r.status_code, 400)
        pk = Group.objects.get(name=RESPONSABLE).pk
        r = self.client.patch(
            reverse("roles-detail", args=[pk]), {"permissions": ["entities.view_portfolio"]}
        )
        self.assertEqual(r.status_code, 400)

    def test_un_permiso_global_nunca_va_en_un_rol(self) -> None:
        pk = Group.objects.get(name=COORDINADOR).pk
        r = self.client.patch(
            reverse("roles-detail", args=[pk]), {"permissions": ["accounts.manage_users"]}
        )
        self.assertEqual(r.status_code, 400)

    def test_se_puede_crear_un_rol_de_portafolio_nuevo(self) -> None:
        r = self.client.post(
            self.url,
            {
                "name": "Observador",
                "ambito": "portafolio",
                "nivel": 10,
                "permissions": ["entities.view_portfolio"],
            },
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["scope"], "portafolio")
        # Queda disponible para los portafolios, no para las entidades.
        self.client.force_authenticate(self.admin)
        norte = Portafolio.objects.create(nombre="N")
        roles = [
            x["name"]
            for x in self.client.get(reverse("portfolio-assignable-roles", args=[norte.pk])).data
        ]
        self.assertIn("Observador", roles)

    def test_por_defecto_un_rol_nuevo_es_de_entidad_y_el_ambito_no_cambia(self) -> None:
        r = self.client.post(self.url, {"name": "Visitante", "nivel": 5})
        self.assertEqual((r.status_code, r.data["scope"]), (201, "entidad"))
        r = self.client.patch(
            reverse("roles-detail", args=[r.data["id"]]), {"ambito": "portafolio"}
        )
        self.assertEqual(r.status_code, 400)

    def test_los_roles_del_sistema_de_portafolio_no_se_renombran_ni_eliminan(self) -> None:
        pk = Group.objects.get(name=GESTOR).pk
        self.assertEqual(
            self.client.patch(reverse("roles-detail", args=[pk]), {"name": "Otro"}).status_code, 400
        )
        self.assertEqual(self.client.delete(reverse("roles-detail", args=[pk])).status_code, 403)
