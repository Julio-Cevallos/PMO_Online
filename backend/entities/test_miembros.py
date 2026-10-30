from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import PerfilRol, User
from accounts.roles import ROL_ADMIN

from .models import Entidad, Membresia
from .utiles_pruebas import (
    AUDITOR,
    COLABORADOR,
    PASSWORD,
    PLANIFICADOR,
    RESPONSABLE,
    dar_permiso,
    entidad,
    miembro,
    usuario,
)


class MiembrosBase(APITestCase):
    """Entidad Alfa con un miembro de cada rol, más un Admin y un superusuario."""

    def setUp(self) -> None:
        self.admin = usuario("jefe", admin=True)
        self.dev = usuario("dev", superuser=True)
        self.alfa = entidad("Alfa", "Proyecto")
        self.otra = entidad("Norte", "Sucursal")
        self.resp = usuario("resp")
        self.plani = usuario("plani")
        self.oper = usuario("oper")
        self.aud = usuario("aud")
        self.m_resp = miembro(self.resp, self.alfa, RESPONSABLE)
        self.m_plani = miembro(self.plani, self.alfa, PLANIFICADOR)
        self.m_oper = miembro(self.oper, self.alfa, COLABORADOR)
        self.m_aud = miembro(self.aud, self.alfa, AUDITOR)
        self.url = reverse("entity-members", args=[self.alfa.pk])
        self.client.force_authenticate(self.admin)

    def como(self, user: User) -> None:
        self.client.force_authenticate(user)

    def rol_id(self, nombre: str) -> int:
        return Group.objects.get(name=nombre).pk

    def detalle(self, m: Membresia, ent: Entidad | None = None) -> str:
        return reverse("entity-member-detail", args=[(ent or self.alfa).pk, m.pk])

    def agregar(self, username: str, rol: str):
        """Invita a una cuenta existente (D-27): el alta directa ya no existe para ellas."""
        url = reverse("entity-invitations", args=[self.alfa.pk])
        return self.client.post(url, {"username": username, "rol": self.rol_id(rol)})

    def crear_cuenta(self, rol: str, **extra):
        nuevo = {"username": "nueva", "password": PASSWORD, "email": "nueva@example.com", **extra}
        return self.client.post(self.url, {"new_user": nuevo, "rol": self.rol_id(rol)})


class ListarMiembrosTests(MiembrosBase):
    def test_quien_gestiona_o_ve_miembros_puede_listarlos(self) -> None:
        for quien in (self.admin, self.dev, self.resp, self.plani):
            self.como(quien)
            r = self.client.get(self.url)
            self.assertEqual(r.status_code, status.HTTP_200_OK, quien.username)
            self.assertEqual(len(r.data), 4)

    def test_operario_y_auditor_no_ven_la_lista(self) -> None:
        for quien in (self.oper, self.aud):
            self.como(quien)
            self.assertEqual(self.client.get(self.url).status_code, 403, quien.username)

    def test_quien_no_es_miembro_recibe_404(self) -> None:
        for quien in (usuario("ajeno"), usuario("recien_registrado")):
            self.como(quien)
            self.assertEqual(self.client.get(self.url).status_code, status.HTTP_404_NOT_FOUND)

    def test_un_responsable_no_ve_los_miembros_de_otra_entidad(self) -> None:
        self.como(self.resp)
        r = self.client.get(reverse("entity-members", args=[self.otra.pk]))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_sin_sesion_401(self) -> None:
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_los_datos_del_miembro(self) -> None:
        fila = {m["username"]: m for m in self.client.get(self.url).data}["aud"]
        self.assertEqual((fila["rol_nombre"], fila["nivel"], fila["activa"]), (AUDITOR, 20, True))
        self.assertNotIn("password", fila)

    def test_por_defecto_solo_activos(self) -> None:
        Membresia.objects.filter(pk=self.m_oper.pk).update(activa=False)
        nombres = {m["username"] for m in self.client.get(self.url).data}
        self.assertNotIn("oper", nombres)
        inactivos = {m["username"] for m in self.client.get(self.url, {"activa": "false"}).data}
        self.assertEqual(inactivos, {"oper"})
        todos = self.client.get(self.url, {"activa": "todas"}).data
        self.assertEqual(len(todos), 4)

    def test_no_se_listan_los_de_otra_entidad(self) -> None:
        miembro(usuario("otro"), self.otra, COLABORADOR)
        nombres = {m["username"] for m in self.client.get(self.url).data}
        self.assertNotIn("otro", nombres)


class JerarquiaAlAgregarTests(MiembrosBase):
    """D-18: nivel estrictamente menor al propio y regla especial del Auditor."""

    def setUp(self) -> None:
        super().setUp()
        for nombre in ("nuevo1", "nuevo2", "nuevo3", "nuevo4"):
            usuario(nombre)

    def test_el_responsable_agrega_planificadores_auditores_y_operarios(self) -> None:
        self.como(self.resp)
        for i, rol in enumerate((PLANIFICADOR, AUDITOR, COLABORADOR), start=1):
            r = self.agregar(f"nuevo{i}", rol)
            self.assertEqual(r.status_code, status.HTTP_201_CREATED, rol)
            self.assertEqual(r.data["rol_nombre"], rol)

    def test_el_responsable_no_agrega_otro_responsable(self) -> None:
        self.como(self.resp)
        r = self.agregar("nuevo1", RESPONSABLE)
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Membresia.objects.filter(usuario__username="nuevo1").exists())

    def test_el_planificador_por_defecto_no_gestiona_miembros(self) -> None:
        self.como(self.plani)
        r = self.agregar("nuevo1", COLABORADOR)
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_con_el_permiso_el_planificador_solo_agrega_operarios(self) -> None:
        dar_permiso(PLANIFICADOR, "manage_members")
        self.como(self.plani)
        self.assertEqual(self.agregar("nuevo1", COLABORADOR).status_code, 201)
        # No puede Auditor (excepción de D-18), ni su mismo nivel, ni uno mayor.
        self.assertEqual(self.agregar("nuevo2", AUDITOR).status_code, 403)
        self.assertEqual(self.agregar("nuevo2", PLANIFICADOR).status_code, 403)
        self.assertEqual(self.agregar("nuevo2", RESPONSABLE).status_code, 403)
        self.assertEqual(list(Membresia.objects.filter(usuario__username="nuevo2")), [])

    def test_el_operario_no_agrega_a_nadie_ni_con_el_permiso(self) -> None:
        dar_permiso(COLABORADOR, "manage_members")
        self.como(self.oper)
        for rol in (COLABORADOR, AUDITOR, PLANIFICADOR, RESPONSABLE):
            self.assertEqual(self.agregar("nuevo1", rol).status_code, 403, rol)

    def test_el_auditor_con_el_permiso_solo_agrega_roles_de_menor_nivel(self) -> None:
        dar_permiso(AUDITOR, "manage_members")
        self.como(self.aud)
        self.assertEqual(self.agregar("nuevo1", COLABORADOR).status_code, 201)
        for rol in (AUDITOR, PLANIFICADOR, RESPONSABLE):
            self.assertEqual(self.agregar("nuevo2", rol).status_code, 403, rol)

    def test_sin_el_permiso_el_auditor_no_agrega_a_nadie(self) -> None:
        self.como(self.aud)
        self.assertEqual(self.agregar("nuevo1", COLABORADOR).status_code, 403)

    def test_el_admin_agrega_cualquier_rol_de_entidad(self) -> None:
        for i, rol in enumerate((RESPONSABLE, PLANIFICADOR, AUDITOR, COLABORADOR), start=1):
            self.assertEqual(self.agregar(f"nuevo{i}", rol).status_code, 201, rol)

    def test_el_superusuario_agrega_cualquier_rol_de_entidad(self) -> None:
        self.como(self.dev)
        self.assertEqual(self.agregar("nuevo1", RESPONSABLE).status_code, 201)

    def test_el_rol_admin_no_se_asigna_a_una_entidad(self) -> None:
        for quien in (self.admin, self.resp):
            self.como(quien)
            r = self.agregar("nuevo1", ROL_ADMIN)
            self.assertIn(r.status_code, (400, 403), quien.username)
        self.assertFalse(Membresia.objects.filter(usuario__username="nuevo1").exists())

    def test_un_rol_sin_perfil_no_se_asigna(self) -> None:
        Group.objects.create(name="Heredado")
        r = self.agregar("nuevo1", "Heredado")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("rol", r.data)

    def test_un_rol_nuevo_sigue_la_jerarquia(self) -> None:
        grupo = Group.objects.create(name="Supervisor")
        PerfilRol.objects.create(grupo=grupo, nivel=35, nivel_minimo_para_asignar=36)
        self.como(self.resp)
        self.assertEqual(self.agregar("nuevo1", "Supervisor").status_code, 201)

    def test_el_nivel_del_auditor_se_puede_bajar_para_que_otros_lo_asignen(self) -> None:
        dar_permiso(PLANIFICADOR, "manage_members")
        PerfilRol.objects.filter(grupo__name=AUDITOR).update(nivel_minimo_para_asignar=30)
        self.como(self.plani)
        self.assertEqual(self.agregar("nuevo1", AUDITOR).status_code, 201)


class CrearCuentasTests(MiembrosBase):
    def test_el_responsable_crea_una_cuenta_con_su_rol(self) -> None:
        self.como(self.resp)
        r = self.crear_cuenta(COLABORADOR)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="nueva")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(user.email, "nueva@example.com")
        self.assertFalse(user.is_staff or user.is_superuser or user.is_admin)
        m = Membresia.objects.get(usuario=user, entidad=self.alfa)
        self.assertEqual((m.rol.name, m.activa, m.creado_por), (COLABORADOR, True, self.resp))
        self.assertNotIn("password", r.data)

    def test_la_cuenta_creada_puede_iniciar_sesion(self) -> None:
        self.como(self.resp)
        self.crear_cuenta(COLABORADOR)
        self.client.force_authenticate(None)
        r = self.client.post(
            reverse("token_obtain_pair"), {"username": "nueva", "password": PASSWORD}
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_la_cuenta_nueva_solo_ve_su_entidad(self) -> None:
        self.como(self.resp)
        self.crear_cuenta(COLABORADOR)
        self.como(User.objects.get(username="nueva"))
        nombres = {e["nombre"] for e in self.client.get(reverse("entities-list")).data["results"]}
        self.assertEqual(nombres, {"Alfa"})

    def test_no_se_puede_crear_una_cuenta_con_un_rol_igual_o_superior(self) -> None:
        self.como(self.resp)
        self.assertEqual(self.crear_cuenta(RESPONSABLE).status_code, 403)
        self.assertFalse(User.objects.filter(username="nueva").exists())

    def test_clave_debil(self) -> None:
        self.como(self.resp)
        r = self.crear_cuenta(COLABORADOR, password="12345678")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("new_user", r.data)
        self.assertFalse(User.objects.filter(username="nueva").exists())

    def test_usuario_o_correo_repetido(self) -> None:
        self.como(self.resp)
        self.assertEqual(self.crear_cuenta(COLABORADOR, username="oper").status_code, 400)
        self.assertEqual(self.crear_cuenta(COLABORADOR, email="OPER@example.com").status_code, 400)

    def test_si_falla_no_queda_la_cuenta_a_medias(self) -> None:
        self.como(self.resp)
        self.crear_cuenta(RESPONSABLE)  # 403 por jerarquía
        self.crear_cuenta(COLABORADOR, password="123")  # 400 por clave
        self.assertFalse(User.objects.filter(username="nueva").exists())

    def test_no_se_dan_privilegios_de_django(self) -> None:
        self.como(self.resp)
        r = self.crear_cuenta(COLABORADOR, is_staff=True, is_superuser=True)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="nueva")
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_este_endpoint_solo_crea_cuentas_nuevas(self) -> None:
        r = self.client.post(self.url, {"rol": self.rol_id(COLABORADOR)})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        # Una cuenta que ya existe se invita (D-27): aquí no se acepta `username`.
        r = self.client.post(self.url, {"username": "oper", "rol": self.rol_id(COLABORADOR)})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="x").exists())

    def test_falta_el_rol_o_no_existe(self) -> None:
        self.assertEqual(self.client.post(self.url, {"username": "oper"}).status_code, 400)
        r = self.client.post(self.url, {"username": "oper", "rol": 99999})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class AgregarCuentaExistenteTests(MiembrosBase):
    def setUp(self) -> None:
        super().setUp()
        self.ana = usuario("ana")
        self.como(self.resp)

    def aceptar(self, invitacion_id: int, quien) -> None:
        self.como(quien)
        r = self.client.post(reverse("invitation-accept", args=[invitacion_id]))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.como(self.resp)

    def test_agregar_una_cuenta_existente_la_invita_sin_meterla_todavia(self) -> None:
        r = self.agregar("ana", COLABORADOR)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual((r.data["username"], r.data["estado"]), ("ana", "pendiente"))
        self.assertFalse(Membresia.objects.filter(usuario=self.ana).exists())

    def test_una_persona_puede_estar_en_varias_entidades_con_roles_distintos(self) -> None:
        miembro(self.ana, self.otra, AUDITOR)
        r = self.agregar("ana", COLABORADOR)
        self.assertEqual(r.status_code, 201)
        self.aceptar(r.data["id"], self.ana)
        roles = set(Membresia.objects.filter(usuario=self.ana).values_list("rol__name", flat=True))
        self.assertEqual(roles, {AUDITOR, COLABORADOR})

    def test_usuario_inexistente(self) -> None:
        r = self.agregar("fantasma", COLABORADOR)
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_un_superusuario_no_se_puede_sumar(self) -> None:
        self.assertEqual(self.agregar("dev", COLABORADOR).status_code, 404)

    def test_una_cuenta_inactiva_no_se_puede_sumar(self) -> None:
        User.objects.filter(pk=self.ana.pk).update(is_active=False)
        self.assertEqual(self.agregar("ana", COLABORADOR).status_code, 404)

    def test_ya_es_miembro_da_409(self) -> None:
        r = self.agregar("oper", COLABORADOR)
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)

    def test_una_membresia_inactiva_se_reactiva_con_el_nuevo_rol_al_aceptar(self) -> None:
        Membresia.objects.filter(pk=self.m_oper.pk).update(activa=False)
        r = self.agregar("oper", PLANIFICADOR)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.m_oper.refresh_from_db()
        self.assertFalse(self.m_oper.activa)  # sigue inactiva hasta que acepte
        self.aceptar(r.data["id"], self.oper)
        self.m_oper.refresh_from_db()
        self.assertEqual((self.m_oper.activa, self.m_oper.rol.name), (True, PLANIFICADOR))
        self.assertEqual(Membresia.objects.filter(usuario=self.oper).count(), 1)

    def test_reactivar_con_un_rol_no_permitido_se_rechaza(self) -> None:
        Membresia.objects.filter(pk=self.m_oper.pk).update(activa=False)
        self.assertEqual(self.agregar("oper", RESPONSABLE).status_code, 403)
        self.m_oper.refresh_from_db()
        self.assertFalse(self.m_oper.activa)

    def test_no_se_agrega_a_una_entidad_ajena(self) -> None:
        r = self.client.post(
            reverse("entity-members", args=[self.otra.pk]),
            {"username": "ana", "rol": self.rol_id(COLABORADOR)},
        )
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_en_una_entidad_archivada_no_se_gestionan_miembros(self) -> None:
        Entidad.objects.filter(pk=self.alfa.pk).update(estado="archivada")
        self.assertEqual(self.agregar("ana", COLABORADOR).status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.crear_cuenta(COLABORADOR).status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.client.get(self.url).status_code, 200)  # sí se puede consultar

    def test_solo_acepta_json(self) -> None:
        r = self.client.post(
            self.url, {"username": "ana", "rol": self.rol_id(COLABORADOR)}, format="multipart"
        )
        self.assertEqual(r.status_code, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)


class ModificarMiembrosTests(MiembrosBase):
    def test_el_responsable_cambia_el_rol_de_un_operario(self) -> None:
        self.como(self.resp)
        r = self.client.patch(self.detalle(self.m_oper), {"rol": self.rol_id(PLANIFICADOR)})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["rol_nombre"], PLANIFICADOR)
        self.m_oper.refresh_from_db()
        self.assertEqual(self.m_oper.rol.name, PLANIFICADOR)

    def test_no_se_puede_subir_a_alguien_a_un_nivel_igual_o_superior(self) -> None:
        self.como(self.resp)
        r = self.client.patch(self.detalle(self.m_oper), {"rol": self.rol_id(RESPONSABLE)})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.m_oper.refresh_from_db()
        self.assertEqual(self.m_oper.rol.name, COLABORADOR)

    def test_un_responsable_no_modifica_a_otro_responsable(self) -> None:
        otro = usuario("otro_resp")
        m_otro = miembro(otro, self.alfa, RESPONSABLE)
        self.como(self.resp)
        r = self.client.patch(self.detalle(m_otro), {"rol": self.rol_id(COLABORADOR)})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(self.detalle(m_otro)).status_code, 403)

    def test_nadie_modifica_su_propia_membresia(self) -> None:
        self.como(self.resp)
        r = self.client.patch(self.detalle(self.m_resp), {"rol": self.rol_id(COLABORADOR)})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(self.detalle(self.m_resp)).status_code, 403)
        self.m_resp.refresh_from_db()
        self.assertTrue(self.m_resp.activa)

    def test_el_planificador_con_permiso_gestiona_operarios_pero_no_auditores(self) -> None:
        dar_permiso(PLANIFICADOR, "manage_members")
        self.como(self.plani)
        r = self.client.patch(self.detalle(self.m_oper), {"activa": False})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.patch(self.detalle(self.m_aud), {"activa": False}).status_code, 403
        )
        self.assertEqual(self.client.delete(self.detalle(self.m_aud)).status_code, 403)
        self.m_aud.refresh_from_db()
        self.assertTrue(self.m_aud.activa)

    def test_sin_el_permiso_de_gestionar_da_403(self) -> None:
        for quien in (self.plani, self.oper, self.aud):
            self.como(quien)
            r = self.client.patch(self.detalle(self.m_oper), {"activa": False})
            self.assertEqual(r.status_code, 403, quien.username)

    def test_el_admin_modifica_a_un_responsable(self) -> None:
        r = self.client.patch(self.detalle(self.m_resp), {"rol": self.rol_id(COLABORADOR)})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_delete_desactiva_y_conserva_la_membresia(self) -> None:
        self.como(self.resp)
        self.assertEqual(self.client.delete(self.detalle(self.m_oper)).status_code, 204)
        self.m_oper.refresh_from_db()
        self.assertFalse(self.m_oper.activa)
        self.assertTrue(User.objects.filter(pk=self.oper.pk, is_active=True).exists())

    def test_quien_sale_pierde_el_acceso_a_la_entidad(self) -> None:
        self.como(self.resp)
        self.client.delete(self.detalle(self.m_oper))
        self.como(self.oper)
        self.assertEqual(
            self.client.get(reverse("entities-detail", args=[self.alfa.pk])).status_code, 404
        )

    def test_reactivar_un_miembro(self) -> None:
        Membresia.objects.filter(pk=self.m_oper.pk).update(activa=False)
        self.como(self.resp)
        r = self.client.patch(self.detalle(self.m_oper), {"activa": True})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.data["activa"])

    def test_datos_invalidos(self) -> None:
        self.como(self.resp)
        for body in ({"rol": 99999}, {"activa": "quizas"}, {"rol": None}):
            r = self.client.patch(self.detalle(self.m_oper), body)
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, body)

    def test_un_rol_sin_perfil_no_se_asigna_al_cambiar(self) -> None:
        Group.objects.create(name="Heredado")
        r = self.client.patch(self.detalle(self.m_oper), {"rol": self.rol_id("Heredado")})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_se_toca_una_membresia_de_otra_entidad(self) -> None:
        m_ajeno = miembro(usuario("otro"), self.otra, COLABORADOR)
        self.como(self.resp)
        # El miembro existe, pero no en la entidad de la URL.
        self.assertEqual(
            self.client.patch(self.detalle(m_ajeno), {"activa": False}).status_code, 404
        )
        # Y la entidad ajena no es visible para este responsable.
        r = self.client.patch(self.detalle(m_ajeno, self.otra), {"activa": False})
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
        m_ajeno.refresh_from_db()
        self.assertTrue(m_ajeno.activa)

    def test_ver_un_miembro(self) -> None:
        self.como(self.resp)
        r = self.client.get(self.detalle(self.m_oper))
        self.assertEqual((r.status_code, r.data["username"]), (200, "oper"))
        self.como(self.oper)
        self.assertEqual(self.client.get(self.detalle(self.m_oper)).status_code, 403)

    def test_en_una_entidad_archivada_no_se_modifican_miembros(self) -> None:
        Entidad.objects.filter(pk=self.alfa.pk).update(estado="archivada")
        r = self.client.patch(self.detalle(self.m_oper), {"activa": False})
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)


class RolEnUsoTests(MiembrosBase):
    def test_no_se_borra_un_rol_que_tiene_miembros(self) -> None:
        grupo = Group.objects.create(name="Supervisor")
        PerfilRol.objects.create(grupo=grupo, nivel=35, nivel_minimo_para_asignar=36)
        miembro(usuario("sup"), self.alfa, "Supervisor")
        r = self.client.delete(reverse("roles-detail", args=[grupo.pk]))
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(Group.objects.filter(name="Supervisor").exists())

    def test_un_rol_sin_miembros_si_se_borra(self) -> None:
        grupo = Group.objects.create(name="Supervisor")
        PerfilRol.objects.create(grupo=grupo, nivel=35, nivel_minimo_para_asignar=36)
        r = self.client.delete(reverse("roles-detail", args=[grupo.pk]))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)

    def test_una_membresia_inactiva_tambien_protege_el_rol(self) -> None:
        grupo = Group.objects.create(name="Supervisor")
        PerfilRol.objects.create(grupo=grupo, nivel=35, nivel_minimo_para_asignar=36)
        miembro(usuario("sup"), self.alfa, "Supervisor", activa=False)
        r = self.client.delete(reverse("roles-detail", args=[grupo.pk]))
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)
