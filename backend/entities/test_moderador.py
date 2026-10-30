"""Rol global Moderador (D-28): crea entidades y es dueño de las que crea, nada más."""

from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from accounts.roles import ROL_MODERADOR
from audit.models import EventoAuditoria

from .models import Entidad, Invitacion, Membresia, TipoEntidad
from .permisos import capacidades, puede_gestionar_miembros, puede_ver_historial
from .utiles_pruebas import (
    COLABORADOR,
    PASSWORD,
    RESPONSABLE,
    entidad,
    miembro,
    moderador,
    usuario,
)


class ModeradorBase(APITestCase):
    def setUp(self) -> None:
        self.admin = usuario("jefe", admin=True)
        self.dev = usuario("dev", superuser=True)
        self.mod = moderador("mod")
        self.otro_mod = moderador("otro_mod")
        self.tipo = TipoEntidad.objects.get(nombre="Proyecto").pk
        self.ajena = entidad("Ajena", "Proyecto")  # la creó "alguien" (sin dueño)
        self.client.force_authenticate(self.mod)
        self.propia = self.crear("Propia")

    def crear(self, nombre: str) -> Entidad:
        r = self.client.post(reverse("entities-list"), {"tipo": self.tipo, "nombre": nombre})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        return Entidad.objects.get(pk=r.data["id"])

    def rol(self, nombre: str) -> int:
        return Group.objects.get(name=nombre).pk

    def nombres(self, user) -> list[str]:
        self.client.force_authenticate(user)
        return [e["nombre"] for e in self.client.get(reverse("entities-list")).data["results"]]


class CrearYVerTests(ModeradorBase):
    def test_el_moderador_crea_y_queda_como_dueno(self) -> None:
        self.assertEqual(self.propia.creado_por, self.mod)
        self.assertTrue(puede_gestionar_miembros(self.mod, self.propia))
        self.assertEqual(self.propia.portafolio.nombre, "Mis entidades")
        self.assertTrue(self.propia.portafolio.personal)

    def test_solo_ve_las_que_creo(self) -> None:
        self.assertEqual(self.nombres(self.mod), ["Propia"])
        self.client.force_authenticate(self.mod)
        r = self.client.get(reverse("entities-detail", args=[self.ajena.pk]))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_un_moderador_no_ve_las_de_otro_moderador_pero_el_admin_ve_todas(self) -> None:
        self.assertEqual(self.nombres(self.otro_mod), [])
        self.assertEqual(sorted(self.nombres(self.admin)), ["Ajena", "Propia"])
        self.assertEqual(sorted(self.nombres(self.dev)), ["Ajena", "Propia"])

    def test_tambien_ve_aquellas_donde_es_miembro_sin_ser_dueno(self) -> None:
        miembro(self.mod, self.ajena, COLABORADOR)
        self.assertEqual(sorted(self.nombres(self.mod)), ["Ajena", "Propia"])

    def test_los_filtros_de_la_lista_siguen_funcionando(self) -> None:
        self.client.force_authenticate(self.mod)
        sucursal = TipoEntidad.objects.get(nombre="Sucursal").pk
        self.client.post(reverse("entities-list"), {"tipo": sucursal, "nombre": "Sur"})
        r = self.client.get(reverse("entities-list"), {"tipo": sucursal})
        self.assertEqual([e["nombre"] for e in r.data["results"]], ["Sur"])

    def test_una_entidad_donde_es_dueno_y_miembro_no_se_repite(self) -> None:
        miembro(self.mod, self.propia, COLABORADOR)
        self.assertEqual(self.nombres(self.mod), ["Propia"])

    def test_quien_no_es_moderador_ni_admin_no_crea(self) -> None:
        self.client.force_authenticate(usuario("ana"))
        r = self.client.post(reverse("entities-list"), {"tipo": self.tipo, "nombre": "X"})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_sin_el_rol_global_conserva_su_portafolio_pero_no_crea_nuevas(self) -> None:
        # Los roles de portafolio no dependen del rol global (D-29): sigue siendo Gestor.
        self.mod.groups.remove(Group.objects.get(name=ROL_MODERADOR))
        mod = User.objects.get(pk=self.mod.pk)
        self.assertEqual(self.nombres(mod), ["Propia"])
        self.assertTrue(puede_gestionar_miembros(mod, self.propia))
        r = self.client.post(reverse("entities-list"), {"tipo": self.tipo, "nombre": "Nueva"})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_ve_los_tipos_pero_no_los_gestiona(self) -> None:
        self.client.force_authenticate(self.mod)
        self.assertEqual(self.client.get(reverse("entity-types-list")).status_code, 200)
        r = self.client.post(reverse("entity-types-list"), {"nombre": "Z", "nombre_plural": "Zs"})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_gestiona_usuarios_ni_roles_ni_ve_la_auditoria_global(self) -> None:
        self.client.force_authenticate(self.mod)
        self.assertEqual(self.client.get(reverse("users-list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("roles-list")).status_code, 403)
        acciones = {e["accion"] for e in self.client.get(reverse("audit-list")).data["results"]}
        self.assertEqual(acciones, {"portafolio.crear", "entidad.crear"})


class CapacidadesYAlcanceTests(ModeradorBase):
    def detalle(self, ent: Entidad) -> dict:
        self.client.force_authenticate(self.mod)
        return self.client.get(reverse("entities-detail", args=[ent.pk])).data

    def test_en_la_propia_tiene_todas_las_capacidades(self) -> None:
        d = self.detalle(self.propia)
        for campo in (
            "puede_editar",
            "puede_ver_miembros",
            "puede_gestionar_miembros",
            "puede_ver_historial",
            "puede_archivar",
        ):
            self.assertTrue(d[campo], campo)

    def test_en_una_ajena_donde_es_miembro_solo_tiene_las_de_su_rol(self) -> None:
        miembro(self.mod, self.ajena, COLABORADOR)
        d = self.detalle(self.ajena)
        for campo in (
            "puede_editar",
            "puede_ver_miembros",
            "puede_gestionar_miembros",
            "puede_ver_historial",
            "puede_archivar",
        ):
            self.assertFalse(d[campo], campo)

    def test_las_capacidades_coinciden_con_las_reglas(self) -> None:
        miembro(self.mod, self.ajena, COLABORADOR)
        info = {"rol": COLABORADOR, "permisos": set()}
        for ent, membresia in ((self.propia, None), (self.ajena, info)):
            api = self.detalle(ent)
            calculado = capacidades(self.mod, membresia, ent)
            self.assertEqual(api["puede_archivar"], calculado["archivar"])
            self.assertEqual(api["puede_ver_historial"], puede_ver_historial(self.mod, ent))
            self.assertEqual(api["puede_ver_historial"], calculado["ver_historial"])

    def test_edita_y_archiva_lo_suyo_pero_no_lo_ajeno(self) -> None:
        self.client.force_authenticate(self.mod)
        url = reverse("entities-detail", args=[self.propia.pk])
        self.assertEqual(self.client.patch(url, {"descripcion": "Obra"}).status_code, 200)
        self.assertEqual(self.client.patch(url, {"estado": "archivada"}).status_code, 200)
        self.assertEqual(self.client.patch(url, {"estado": "activa"}).status_code, 200)
        miembro(self.mod, self.ajena, RESPONSABLE)
        ajena = reverse("entities-detail", args=[self.ajena.pk])
        self.assertEqual(self.client.patch(ajena, {"estado": "archivada"}).status_code, 403)

    def test_no_se_puede_crear_dos_con_el_mismo_nombre_y_tipo(self) -> None:
        r = self.client.post(reverse("entities-list"), {"tipo": self.tipo, "nombre": "propia"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class GestionDeMiembrosTests(ModeradorBase):
    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("entity-members", args=[self.propia.pk])
        self.inv = reverse("entity-invitations", args=[self.propia.pk])

    def test_crea_la_cuenta_del_responsable_con_cualquier_rol_de_entidad(self) -> None:
        r = self.client.post(
            self.url,
            {"new_user": {"username": "resp", "password": PASSWORD}, "rol": self.rol(RESPONSABLE)},
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(r.data["rol_nombre"], RESPONSABLE)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_invita_a_una_cuenta_existente_como_responsable(self) -> None:
        usuario("ana")
        r = self.client.post(self.inv, {"username": "ana", "rol": self.rol(RESPONSABLE)})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)

    def test_ve_los_roles_asignables_y_cambia_y_desactiva_miembros(self) -> None:
        ana = usuario("ana")
        m = miembro(ana, self.propia, COLABORADOR)
        roles = self.client.get(reverse("entity-assignable-roles", args=[self.propia.pk]))
        self.assertEqual(roles.status_code, 200)
        nombres = [r["name"] for r in roles.data]
        self.assertIn(RESPONSABLE, nombres)
        self.assertNotIn(ROL_MODERADOR, nombres)
        detalle = reverse("entity-member-detail", args=[self.propia.pk, m.pk])
        self.assertEqual(
            self.client.patch(detalle, {"rol": self.rol(RESPONSABLE)}).status_code, 200
        )
        self.assertEqual(self.client.delete(detalle).status_code, 204)

    def test_no_gestiona_miembros_de_una_entidad_ajena(self) -> None:
        url = reverse("entity-members", args=[self.ajena.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.post(
                reverse("entity-invitations", args=[self.ajena.pk]),
                {"username": "x", "rol": self.rol(COLABORADOR)},
            ).status_code,
            404,
        )

    def test_el_rol_moderador_no_se_asigna_dentro_de_una_entidad(self) -> None:
        usuario("ana")
        r = self.client.post(self.inv, {"username": "ana", "rol": self.rol(ROL_MODERADOR)})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Invitacion.objects.count(), 0)

    def test_las_sugerencias_incluyen_a_los_miembros_de_sus_otras_entidades(self) -> None:
        otra = self.crear("Otra")
        ana = usuario("ana")
        miembro(ana, otra, COLABORADOR)
        usuario("lejana")  # no está en ninguna de sus entidades
        r = self.client.get(reverse("entity-candidates", args=[self.propia.pk]))
        self.assertEqual([c["username"] for c in r.data], ["ana"])

    def test_en_una_entidad_archivada_no_se_invita(self) -> None:
        Entidad.objects.filter(pk=self.propia.pk).update(estado="archivada")
        usuario("ana")
        r = self.client.post(self.inv, {"username": "ana", "rol": self.rol(COLABORADOR)})
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)


class HistorialDelDuenoTests(ModeradorBase):
    def acciones(self, user, **filtros) -> list[str] | None:
        """Acciones visibles, o `None` si no tiene acceso al historial (403)."""
        self.client.force_authenticate(user)
        r = self.client.get(reverse("audit-list"), filtros)
        if r.status_code == status.HTTP_403_FORBIDDEN:
            return None
        self.assertEqual(r.status_code, 200)
        return [e["accion"] for e in r.data["results"]]

    def test_ve_la_administracion_de_sus_entidades_y_nada_mas(self) -> None:
        self.client.force_authenticate(self.mod)
        self.client.patch(reverse("entities-detail", args=[self.propia.pk]), {"descripcion": "A"})
        self.client.post(
            reverse("entity-members", args=[self.propia.pk]),
            {"new_user": {"username": "nueva", "password": PASSWORD}, "rol": self.rol(COLABORADOR)},
        )
        acciones = self.acciones(self.mod)
        self.assertEqual(
            sorted(acciones),
            ["entidad.crear", "entidad.editar", "miembro.agregar", "portafolio.crear"],
        )
        # La creación de la cuenta es un evento de sistema: no es suyo.
        self.assertNotIn("usuario.crear", acciones)
        self.assertIn("usuario.crear", self.acciones(self.admin))

    def test_otro_moderador_no_ve_los_eventos_de_ajenas(self) -> None:
        self.assertIsNone(self.acciones(self.otro_mod))

    def test_no_ve_los_eventos_de_una_entidad_ajena_aunque_sea_miembro(self) -> None:
        miembro(self.mod, self.ajena, COLABORADOR)
        from audit.servicios import registrar

        registrar(
            accion="entidad.editar", categoria="entidad", entidad=self.ajena, usuario=self.admin
        )
        self.assertEqual(sorted(self.acciones(self.mod)), ["entidad.crear", "portafolio.crear"])
        self.assertEqual(EventoAuditoria.objects.filter(entidad_id=self.ajena.pk).count(), 1)

    def test_sin_el_rol_global_conserva_el_historial_de_su_portafolio(self) -> None:
        self.mod.groups.remove(Group.objects.get(name=ROL_MODERADOR))
        self.assertEqual(
            sorted(self.acciones(User.objects.get(pk=self.mod.pk))),
            ["entidad.crear", "portafolio.crear"],
        )


class AsignarElRolTests(APITestCase):
    def setUp(self) -> None:
        self.admin = usuario("jefe", admin=True)
        self.dev = usuario("dev", superuser=True)
        self.ana = usuario("ana")

    def asignar(self, quien, valor: bool):
        self.client.force_authenticate(quien)
        return self.client.patch(
            reverse("users-detail", args=[self.ana.pk]), {"is_moderator": valor}
        )

    def acciones(self) -> list[str]:
        return list(EventoAuditoria.objects.order_by("id").values_list("accion", flat=True))

    def test_un_admin_puede_dar_y_quitar_moderador(self) -> None:
        r = self.asignar(self.admin, True)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["is_moderator"])
        self.assertTrue(User.objects.get(pk=self.ana.pk).is_moderator)
        self.assertFalse(self.asignar(self.admin, False).data["is_moderator"])
        self.assertEqual(self.acciones(), ["usuario.dar_moderador", "usuario.quitar_moderador"])

    def test_el_superusuario_tambien(self) -> None:
        self.assertEqual(self.asignar(self.dev, True).status_code, 200)

    def test_un_moderador_no_asigna_roles_a_nadie(self) -> None:
        self.assertEqual(self.asignar(moderador("mod"), True).status_code, 403)
        self.assertFalse(User.objects.get(pk=self.ana.pk).is_moderator)

    def test_dar_moderador_no_da_admin_y_viceversa(self) -> None:
        self.asignar(self.admin, True)
        ana = User.objects.get(pk=self.ana.pk)
        self.assertEqual((ana.is_moderator, ana.is_admin), (True, False))
        self.client.force_authenticate(self.admin)
        r = self.client.patch(reverse("users-detail", args=[self.ana.pk]), {"is_admin": True})
        self.assertEqual(r.status_code, 403)  # solo un superusuario da Admin

    def test_crear_una_cuenta_ya_como_moderador(self) -> None:
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            reverse("users-list"), {"username": "nuevo", "password": PASSWORD, "is_moderator": True}
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["is_moderator"])
        self.assertEqual(self.acciones(), ["usuario.crear", "usuario.dar_moderador"])

    def test_el_perfil_propio_indica_si_es_moderador_y_puede_crear(self) -> None:
        mod = moderador("mod")
        self.client.force_authenticate(mod)
        r = self.client.get(reverse("me"))
        self.assertTrue(r.data["is_moderator"])
        self.assertEqual(r.data["global_permissions"], ["entities.create_entity"])

    def test_editar_otros_datos_no_toca_el_rol(self) -> None:
        self.asignar(self.admin, True)
        self.client.force_authenticate(self.admin)
        r = self.client.patch(reverse("users-detail", args=[self.ana.pk]), {"first_name": "Ana"})
        self.assertTrue(r.data["is_moderator"])

    def test_el_rol_moderador_es_del_sistema(self) -> None:
        self.client.force_authenticate(self.dev)
        pk = Group.objects.get(name=ROL_MODERADOR).pk
        self.assertEqual(
            self.client.patch(reverse("roles-detail", args=[pk]), {"permissions": []}).status_code,
            403,
        )
        self.assertEqual(self.client.delete(reverse("roles-detail", args=[pk])).status_code, 403)
        self.assertEqual(Membresia.objects.count(), 0)
