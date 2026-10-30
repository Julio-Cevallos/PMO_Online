from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.roles import NOMBRES_ANTERIORES, sincronizar_roles_del_sistema

from .models import Membresia
from .utiles_pruebas import (
    AUDITOR,
    COLABORADOR,
    PLANIFICADOR,
    RESPONSABLE,
    entidad,
    miembro,
    usuario,
)


class CandidatosTests(APITestCase):
    """Búsqueda de cuentas para sumar a una entidad (D-26)."""

    def setUp(self) -> None:
        self.admin = usuario("jefe", admin=True)
        self.dev = usuario("dev", superuser=True)
        self.alfa = entidad("Alfa", "Proyecto")
        self.beta = entidad("Beta", "Sucursal")
        self.gamma = entidad("Gamma", "Proyecto")
        self.resp = usuario("resp")
        miembro(self.resp, self.alfa, RESPONSABLE)
        miembro(self.resp, self.beta, RESPONSABLE)
        # Comparte Beta con el Responsable; ya está en Alfa:
        self.en_alfa = usuario("ya_en_alfa")
        miembro(self.en_alfa, self.alfa, COLABORADOR)
        miembro(self.en_alfa, self.beta, COLABORADOR)
        # Comparte Beta (puede sumarse a Alfa):
        self.ana = usuario("ana")
        self.ana.first_name, self.ana.last_name = "Ana", "Pérez"
        self.ana.save()
        miembro(self.ana, self.beta, COLABORADOR)
        # Solo está en Gamma, donde el Responsable no está: no debe verla.
        self.lejana = usuario("lejana")
        miembro(self.lejana, self.gamma, COLABORADOR)
        # Sin ninguna entidad:
        self.suelta = usuario("suelta")
        self.url = reverse("entity-candidates", args=[self.alfa.pk])

    def buscar(self, user, q: str | None = None) -> list[str]:
        self.client.force_authenticate(user)
        r = self.client.get(self.url, {"q": q} if q is not None else {})
        self.assertEqual(r.status_code, status.HTTP_200_OK, user.username)
        return [c["username"] for c in r.data]

    def test_el_admin_busca_entre_todas_las_cuentas_normales(self) -> None:
        # Sin él, sin superusuarios y sin quien ya es miembro activo de Alfa (resp, ya_en_alfa).
        self.assertEqual(self.buscar(self.admin), ["ana", "lejana", "suelta"])

    def test_el_responsable_solo_ve_a_quien_comparte_otra_entidad(self) -> None:
        self.assertEqual(self.buscar(self.resp), ["ana"])

    def test_nunca_aparecen_superusuarios_ni_el_propio_ni_cuentas_desactivadas(self) -> None:
        self.suelta.is_active = False
        self.suelta.save()
        nombres = self.buscar(self.admin)
        self.assertNotIn("dev", nombres)
        self.assertNotIn("jefe", nombres)  # el propio
        self.assertNotIn("suelta", nombres)

    def test_quien_ya_es_miembro_activo_no_aparece_pero_un_inactivo_si(self) -> None:
        self.assertNotIn("ya_en_alfa", self.buscar(self.admin))
        Membresia.objects.filter(usuario=self.en_alfa, entidad=self.alfa).update(activa=False)
        self.assertIn("ya_en_alfa", self.buscar(self.admin))
        self.assertIn("ya_en_alfa", self.buscar(self.resp))

    def test_busca_por_usuario_nombre_y_apellido_sin_distinguir_mayusculas(self) -> None:
        for texto in ("an", "ANA", "pérez", "ana pér", "pérez ana"):
            self.assertEqual(self.buscar(self.resp, texto), ["ana"], texto)
        self.assertEqual(self.buscar(self.resp, "zzz"), [])

    def test_las_palabras_deben_coincidir_todas(self) -> None:
        self.assertEqual(self.buscar(self.admin, "ana pérez suelta"), [])

    def test_devuelve_como_maximo_diez(self) -> None:
        for i in range(15):
            usuario(f"masa{i:02d}")
        nombres = self.buscar(self.admin, "masa")
        self.assertEqual(len(nombres), 10)
        self.assertEqual(nombres, sorted(nombres))

    def test_no_se_ve_a_quien_comparte_solo_una_entidad_ya_inactiva(self) -> None:
        Membresia.objects.filter(usuario=self.resp, entidad=self.beta).update(activa=False)
        self.assertEqual(self.buscar(self.resp), [])

    def test_sin_permiso_de_gestionar_miembros_da_403(self) -> None:
        planificador = usuario("plani")
        miembro(planificador, self.alfa, PLANIFICADOR)
        auditor = usuario("aud")
        miembro(auditor, self.alfa, AUDITOR)
        for user in (planificador, auditor, self.en_alfa):
            self.client.force_authenticate(user)
            r = self.client.get(self.url)
            self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN, user.username)

    def test_quien_no_ve_la_entidad_recibe_404_y_sin_sesion_401(self) -> None:
        self.client.force_authenticate(self.lejana)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_el_resultado_no_expone_datos_sensibles(self) -> None:
        self.client.force_authenticate(self.resp)
        (fila,) = self.client.get(self.url).data
        self.assertEqual(set(fila), {"id", "username", "first_name", "last_name"})

    def test_las_consultas_no_crecen_con_el_numero_de_cuentas(self) -> None:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def consultas() -> int:
            self.client.force_authenticate(self.resp)
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(self.url)
            return len(ctx)

        consultas()  # la primera vez Django guarda en caché los tipos de contenido
        antes = consultas()
        for i in range(8):
            miembro(usuario(f"extra{i}"), self.beta, COLABORADOR)
        self.assertEqual(consultas(), antes)


class RenombrarRolTests(APITestCase):
    """«Operario de campo» pasó a llamarse «Colaborador»: las bases existentes se renombran."""

    def test_el_rol_antiguo_se_renombra_y_conserva_sus_miembros(self) -> None:
        antiguo = next(iter(NOMBRES_ANTERIORES))
        grupo = Group.objects.get(name=COLABORADOR)
        grupo.name = antiguo
        grupo.save()
        ent = entidad("Alfa", "Proyecto")
        m = miembro(usuario("ana"), ent, antiguo)

        sincronizar_roles_del_sistema()

        m.refresh_from_db()
        self.assertEqual(m.rol_id, grupo.pk)
        self.assertEqual(m.rol.name, COLABORADOR)
        self.assertFalse(Group.objects.filter(name=antiguo).exists())
        self.assertEqual(Group.objects.filter(name=COLABORADOR).count(), 1)

    def test_si_ya_existen_los_dos_no_se_pisa_ninguno(self) -> None:
        antiguo = next(iter(NOMBRES_ANTERIORES))
        Group.objects.create(name=antiguo)
        sincronizar_roles_del_sistema()
        self.assertEqual(Group.objects.filter(name=COLABORADOR).count(), 1)
        self.assertEqual(Group.objects.filter(name=antiguo).count(), 1)
