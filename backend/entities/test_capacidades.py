from django.contrib.auth.models import Group
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status

from accounts.models import PerfilRol

from .permisos import (
    puede_editar_entidad,
    puede_gestionar_miembros,
    puede_ver_historial,
    puede_ver_miembros,
)
from .test_miembros import MiembrosBase
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

CAMPOS = ("puede_editar", "puede_ver_miembros", "puede_gestionar_miembros")
HISTORIAL = "puede_ver_historial"


class CapacidadesTests(MiembrosBase):
    """Lo que la web usa para decidir qué botones mostrar (el backend sigue siendo la barrera)."""

    def capacidades(self, user) -> tuple[bool, bool, bool]:
        self.como(user)
        r = self.client.get(reverse("entities-detail", args=[self.alfa.pk]))
        self.assertEqual(r.status_code, status.HTTP_200_OK, user.username)
        return tuple(r.data[campo] for campo in CAMPOS)

    def test_capacidades_de_cada_rol(self) -> None:
        esperado = {
            self.resp: (True, True, True),
            self.plani: (False, True, False),
            self.oper: (False, False, False),
            self.aud: (False, False, False),
            self.admin: (True, True, True),
            self.dev: (True, True, True),
        }
        for user, valores in esperado.items():
            self.assertEqual(self.capacidades(user), valores, user.username)

    def test_coinciden_con_las_reglas_que_aplica_el_backend(self) -> None:
        for user in (self.resp, self.plani, self.oper, self.aud, self.admin, self.dev):
            api = self.capacidades(user)
            reglas = (
                puede_editar_entidad(user, self.alfa),
                puede_ver_miembros(user, self.alfa),
                puede_gestionar_miembros(user, self.alfa),
            )
            self.assertEqual(api, reglas, user.username)

    def test_quien_ve_el_historial_de_la_entidad(self) -> None:
        # Responsable y Auditor (permiso por entidad), Admin y superusuario; el resto, no.
        esperado = {
            self.resp: True,
            self.aud: True,
            self.admin: True,
            self.dev: True,
            self.plani: False,
            self.oper: False,
        }
        for user, valor in esperado.items():
            self.como(user)
            r = self.client.get(reverse("entities-detail", args=[self.alfa.pk]))
            self.assertIs(r.data[HISTORIAL], valor, user.username)
            self.assertIs(puede_ver_historial(user, self.alfa), valor, user.username)

    def test_ver_el_historial_depende_del_rol_en_cada_entidad(self) -> None:
        ana = usuario("ana")
        miembro(ana, self.alfa, AUDITOR)
        miembro(ana, self.otra, COLABORADOR)
        self.como(ana)
        filas = {
            e["id"]: e[HISTORIAL] for e in self.client.get(reverse("entities-list")).data["results"]
        }
        self.assertEqual(filas, {self.alfa.pk: True, self.otra.pk: False})

    def test_la_capacidad_coincide_con_lo_que_devuelve_el_historial(self) -> None:
        from audit.models import EventoAuditoria
        from audit.visibilidad import eventos_visibles
        from entities.auditoria import entidad_creada

        self.client.force_authenticate(self.admin)
        entidad_creada(type("R", (), {"user": self.admin, "META": {}})(), self.alfa)
        self.assertTrue(EventoAuditoria.objects.filter(entidad_id=self.alfa.pk).exists())
        for user in (self.resp, self.plani, self.oper, self.aud, self.admin, self.dev):
            ve = eventos_visibles(user).filter(entidad_id=self.alfa.pk).exists()
            self.assertIs(puede_ver_historial(user, self.alfa), ve, user.username)

    def test_el_listado_y_el_detalle_coinciden(self) -> None:
        self.como(self.plani)
        fila = self.client.get(reverse("entities-list")).data["results"][0]
        self.assertEqual(tuple(fila[campo] for campo in CAMPOS), (False, True, False))

    def test_al_dar_un_permiso_a_un_rol_cambia_la_capacidad(self) -> None:
        dar_permiso(COLABORADOR, "manage_members")
        self.assertEqual(self.capacidades(self.oper), (False, True, True))

    def test_quien_no_es_miembro_no_tiene_capacidades_ni_ve_la_entidad(self) -> None:
        self.como(usuario("ajeno"))
        r = self.client.get(reverse("entities-detail", args=[self.alfa.pk]))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_en_cada_entidad_valen_los_permisos_de_su_rol(self) -> None:
        ana = usuario("ana")
        miembro(ana, self.alfa, RESPONSABLE)
        miembro(ana, self.otra, COLABORADOR)
        self.como(ana)
        filas = {e["nombre"]: e for e in self.client.get(reverse("entities-list")).data["results"]}
        self.assertEqual(filas["Alfa"]["puede_gestionar_miembros"], True)
        self.assertEqual(filas["Norte"]["puede_gestionar_miembros"], False)
        self.assertEqual(filas["Alfa"]["mi_rol"], RESPONSABLE)
        self.assertEqual(filas["Norte"]["mi_rol"], COLABORADOR)

    def test_el_listado_no_hace_mas_consultas_con_mas_entidades(self) -> None:
        def consultas() -> int:
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(reverse("entities-list"))
            return len(ctx)

        self.como(self.resp)
        consultas()  # calienta cachés
        antes = consultas()
        for i in range(6):
            miembro(self.resp, entidad(f"Extra {i}", "Proyecto"), RESPONSABLE)
        self.assertEqual(consultas(), antes)


class RolesAsignablesTests(MiembrosBase):
    def setUp(self) -> None:
        super().setUp()
        self.url_roles = reverse("entity-assignable-roles", args=[self.alfa.pk])

    def nombres(self, user) -> list[str]:
        self.como(user)
        r = self.client.get(self.url_roles)
        self.assertEqual(r.status_code, status.HTTP_200_OK, user.username)
        return [rol["name"] for rol in r.data]

    def test_el_responsable_puede_asignar_los_roles_de_menor_nivel_en_orden(self) -> None:
        self.como(self.resp)
        r = self.client.get(self.url_roles)
        self.assertEqual(
            [(x["name"], x["nivel"]) for x in r.data],
            [(PLANIFICADOR, 30), (AUDITOR, 20), (COLABORADOR, 10)],
        )

    def test_el_admin_y_el_superusuario_pueden_asignar_todos_los_de_entidad(self) -> None:
        for user in (self.admin, self.dev):
            self.assertEqual(
                self.nombres(user), [RESPONSABLE, PLANIFICADOR, AUDITOR, COLABORADOR], user.username
            )

    def test_sin_permiso_de_gestionar_miembros_da_403(self) -> None:
        for user in (self.plani, self.oper, self.aud):
            self.como(user)
            self.assertEqual(self.client.get(self.url_roles).status_code, 403, user.username)

    def test_con_el_permiso_el_planificador_solo_puede_asignar_operarios(self) -> None:
        dar_permiso(PLANIFICADOR, "manage_members")
        self.assertEqual(self.nombres(self.plani), [COLABORADOR])  # no el Auditor (D-18)

    def test_un_rol_nuevo_aparece_segun_su_nivel(self) -> None:
        grupo = Group.objects.create(name="Supervisor")
        PerfilRol.objects.create(grupo=grupo, nivel=35, nivel_minimo_para_asignar=36)
        self.assertEqual(
            self.nombres(self.resp), ["Supervisor", PLANIFICADOR, AUDITOR, COLABORADOR]
        )

    def test_nunca_aparecen_el_admin_ni_los_roles_sin_perfil(self) -> None:
        Group.objects.create(name="Heredado")
        for user in (self.admin, self.resp):
            nombres = self.nombres(user)
            self.assertNotIn("Admin", nombres)
            self.assertNotIn("Heredado", nombres)

    def test_quien_no_ve_la_entidad_recibe_404(self) -> None:
        self.como(usuario("ajeno"))
        self.assertEqual(self.client.get(self.url_roles).status_code, status.HTTP_404_NOT_FOUND)

    def test_sin_sesion_401(self) -> None:
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url_roles).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_en_una_entidad_archivada_se_puede_consultar(self) -> None:
        self.alfa.estado = "archivada"
        self.alfa.save()
        self.assertEqual(self.nombres(self.resp), [PLANIFICADOR, AUDITOR, COLABORADOR])

    def test_coincide_con_lo_que_el_backend_permite_agregar(self) -> None:
        """Un rol está en la lista si y solo si agregar a alguien con ese rol no da 403."""
        grupo = Group.objects.create(name="Supervisor")
        PerfilRol.objects.create(grupo=grupo, nivel=35, nivel_minimo_para_asignar=36)
        dar_permiso(PLANIFICADOR, "manage_members")
        todos = [RESPONSABLE, "Supervisor", PLANIFICADOR, AUDITOR, COLABORADOR]
        for actor in (self.resp, self.plani, self.admin):
            en_lista = set(self.nombres(actor))
            for i, rol in enumerate(todos):
                candidato = usuario(f"cand_{actor.username}_{i}")
                self.como(actor)
                r = self.agregar(candidato.username, rol)
                self.assertEqual(rol in en_lista, r.status_code != 403, f"{actor.username} / {rol}")
