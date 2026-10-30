from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .jerarquia import puede_asignar
from .models import PerfilRol
from .roles import NIVELES_SISTEMA, ROL_ADMIN, ROLES_POR_ENTIDAD, sincronizar_roles_del_sistema
from .test_users_admin import crear_usuario


def perfil(nombre: str) -> PerfilRol:
    return PerfilRol.objects.get(grupo__name=nombre)


class PerfilesDelSistemaTests(TestCase):
    def test_los_roles_del_sistema_tienen_su_nivel(self) -> None:
        for nombre in ROLES_POR_ENTIDAD:
            nivel, minimo = NIVELES_SISTEMA[nombre]
            p = perfil(nombre)
            self.assertEqual((p.nivel, p.nivel_minimo_para_asignar), (nivel, minimo))

    def test_escala_inicial(self) -> None:
        niveles = {n: perfil(n).nivel for n in ROLES_POR_ENTIDAD}
        self.assertEqual(
            niveles,
            {
                "Responsable de entidad": 40,
                "Planificador": 30,
                "Auditor": 20,
                "Colaborador": 10,
            },
        )

    def test_el_auditor_solo_lo_asigna_el_responsable(self) -> None:
        self.assertEqual(perfil("Auditor").nivel_minimo_para_asignar, 40)

    def test_admin_es_global_y_no_tiene_perfil(self) -> None:
        self.assertFalse(PerfilRol.objects.filter(grupo__name=ROL_ADMIN).exists())

    def test_sincronizar_no_pisa_los_cambios_del_admin(self) -> None:
        PerfilRol.objects.filter(grupo__name="Planificador").update(
            nivel=35, nivel_minimo_para_asignar=36
        )
        sincronizar_roles_del_sistema()
        self.assertEqual(perfil("Planificador").nivel, 35)

    def test_sincronizar_repone_un_perfil_que_falta(self) -> None:
        PerfilRol.objects.filter(grupo__name="Auditor").delete()
        sincronizar_roles_del_sistema()
        p = perfil("Auditor")
        self.assertEqual((p.nivel, p.nivel_minimo_para_asignar), (20, 40))

    def test_borrar_un_rol_borra_su_perfil(self) -> None:
        grupo = Group.objects.create(name="Temporal")
        PerfilRol.objects.create(grupo=grupo, nivel=5, nivel_minimo_para_asignar=6)
        grupo.delete()
        self.assertFalse(PerfilRol.objects.filter(nivel=5, nivel_minimo_para_asignar=6).exists())


class RestriccionesDeLaBaseTests(TestCase):
    def crear(self, nivel: int, minimo: int) -> None:
        grupo = Group.objects.create(name=f"Rol {nivel}-{minimo}")
        with transaction.atomic():
            PerfilRol.objects.create(grupo=grupo, nivel=nivel, nivel_minimo_para_asignar=minimo)

    def test_nivel_fuera_de_rango(self) -> None:
        for nivel in (0, 100):
            with self.assertRaises(IntegrityError):
                self.crear(nivel, 100)

    def test_el_minimo_debe_superar_al_nivel(self) -> None:
        for nivel, minimo in ((10, 10), (10, 9)):
            with self.assertRaises(IntegrityError):
                self.crear(nivel, minimo)

    def test_el_minimo_no_pasa_de_100(self) -> None:
        with self.assertRaises(IntegrityError):
            self.crear(10, 101)

    def test_valores_validos_en_los_extremos(self) -> None:
        self.crear(1, 2)
        self.crear(99, 100)


class PuedeAsignarTests(TestCase):
    """Regla de D-18: nivel estrictamente mayor + nivel mínimo para asignar."""

    def permitido(self, actor: str, objetivo: str) -> bool:
        return puede_asignar(perfil(actor).nivel, perfil(objetivo))

    def test_responsable(self) -> None:
        self.assertTrue(self.permitido("Responsable de entidad", "Planificador"))
        self.assertTrue(self.permitido("Responsable de entidad", "Auditor"))
        self.assertTrue(self.permitido("Responsable de entidad", "Colaborador"))

    def test_nadie_asigna_su_mismo_nivel_ni_uno_mayor(self) -> None:
        for nombre in ROLES_POR_ENTIDAD:
            self.assertFalse(self.permitido(nombre, nombre))
        self.assertFalse(self.permitido("Planificador", "Responsable de entidad"))
        self.assertFalse(self.permitido("Colaborador", "Planificador"))

    def test_el_responsable_no_asigna_otro_responsable(self) -> None:
        self.assertFalse(self.permitido("Responsable de entidad", "Responsable de entidad"))

    def test_el_planificador_asigna_operarios_pero_no_auditores(self) -> None:
        self.assertTrue(self.permitido("Planificador", "Colaborador"))
        self.assertFalse(self.permitido("Planificador", "Auditor"))

    def test_el_operario_no_asigna_a_nadie(self) -> None:
        for nombre in ROLES_POR_ENTIDAD:
            self.assertFalse(self.permitido("Colaborador", nombre))

    def test_un_rol_nuevo_sigue_la_regla_por_defecto(self) -> None:
        grupo = Group.objects.create(name="Supervisor")
        nuevo = PerfilRol.objects.create(grupo=grupo, nivel=25, nivel_minimo_para_asignar=26)
        self.assertTrue(puede_asignar(30, nuevo))  # Planificador
        self.assertFalse(puede_asignar(25, nuevo))
        self.assertFalse(puede_asignar(20, nuevo))


class ApiNivelesTests(APITestCase):
    def setUp(self) -> None:
        self.admin = crear_usuario("jefe", admin=True)
        self.client.force_authenticate(self.admin)
        self.url = reverse("roles-list")

    def detalle(self, nombre: str) -> str:
        return reverse("roles-detail", args=[Group.objects.get(name=nombre).pk])

    def test_el_listado_incluye_los_niveles(self) -> None:
        filas = {r["name"]: r for r in self.client.get(self.url).data}
        self.assertEqual(filas["Auditor"]["nivel"], 20)
        self.assertEqual(filas["Auditor"]["nivel_minimo_para_asignar"], 40)
        self.assertEqual(filas["Responsable de entidad"]["nivel"], 40)

    def test_admin_no_tiene_nivel(self) -> None:
        filas = {r["name"]: r for r in self.client.get(self.url).data}
        self.assertIsNone(filas[ROL_ADMIN]["nivel"])
        self.assertIsNone(filas[ROL_ADMIN]["nivel_minimo_para_asignar"])

    def test_crear_exige_nivel(self) -> None:
        r = self.client.post(self.url, {"name": "Supervisor"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nivel", r.data)
        self.assertFalse(Group.objects.filter(name="Supervisor").exists())

    def test_el_minimo_por_defecto_es_nivel_mas_uno(self) -> None:
        r = self.client.post(self.url, {"name": "Supervisor", "nivel": 25})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual((r.data["nivel"], r.data["nivel_minimo_para_asignar"]), (25, 26))

    def test_crear_con_minimo_explicito(self) -> None:
        body = {"name": "Revisor", "nivel": 15, "nivel_minimo_para_asignar": 40}
        r = self.client.post(self.url, body)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["nivel_minimo_para_asignar"], 40)

    def test_niveles_fuera_de_rango(self) -> None:
        for nivel in (0, 100, -1, "x"):
            r = self.client.post(self.url, {"name": "Malo", "nivel": nivel})
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        r = self.client.post(
            self.url, {"name": "Malo", "nivel": 10, "nivel_minimo_para_asignar": 101}
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_el_minimo_debe_superar_al_nivel(self) -> None:
        for minimo in (10, 5):
            body = {"name": "Malo", "nivel": 10, "nivel_minimo_para_asignar": minimo}
            r = self.client.post(self.url, body)
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("nivel_minimo_para_asignar", r.data)
        self.assertFalse(Group.objects.filter(name="Malo").exists())

    def test_los_niveles_no_pueden_ser_nulos(self) -> None:
        for campo in ("nivel", "nivel_minimo_para_asignar"):
            r = self.client.post(self.url, {"name": "Malo", "nivel": 10, campo: None})
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_el_admin_ajusta_el_nivel_de_un_rol_del_sistema(self) -> None:
        r = self.client.patch(self.detalle("Colaborador"), {"nivel": 12})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        # El mínimo era 11 y quedaría por debajo del nivel: se ajusta solo.
        self.assertEqual((r.data["nivel"], r.data["nivel_minimo_para_asignar"]), (12, 13))
        self.assertEqual(perfil("Colaborador").nivel, 12)

    def test_cambiar_el_nivel_conserva_un_minimo_que_sigue_siendo_valido(self) -> None:
        r = self.client.patch(self.detalle("Auditor"), {"nivel": 25})
        self.assertEqual((r.data["nivel"], r.data["nivel_minimo_para_asignar"]), (25, 40))

    def test_cambiar_el_nivel_con_un_minimo_invalido_se_rechaza(self) -> None:
        body = {"nivel": 30, "nivel_minimo_para_asignar": 30}
        r = self.client.patch(self.detalle("Colaborador"), body)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(perfil("Colaborador").nivel, 10)

    def test_cambiar_solo_el_minimo(self) -> None:
        r = self.client.patch(self.detalle("Auditor"), {"nivel_minimo_para_asignar": 90})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual((r.data["nivel"], r.data["nivel_minimo_para_asignar"]), (20, 90))

    def test_editar_el_nombre_no_toca_los_niveles(self) -> None:
        self.client.post(self.url, {"name": "Supervisor", "nivel": 25})
        r = self.client.patch(self.detalle("Supervisor"), {"name": "Jefe de zona"})
        self.assertEqual((r.data["nivel"], r.data["nivel_minimo_para_asignar"]), (25, 26))

    def test_un_rol_sin_perfil_exige_nivel_al_ajustar_la_jerarquia(self) -> None:
        Group.objects.create(name="Heredado")
        r = self.client.patch(self.detalle("Heredado"), {"nivel_minimo_para_asignar": 50})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nivel", r.data)
        r = self.client.patch(self.detalle("Heredado"), {"nivel": 15})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual((r.data["nivel"], r.data["nivel_minimo_para_asignar"]), (15, 16))

    def test_un_rol_sin_perfil_se_puede_listar_y_renombrar(self) -> None:
        Group.objects.create(name="Heredado")
        filas = {r["name"]: r for r in self.client.get(self.url).data}
        self.assertIsNone(filas["Heredado"]["nivel"])
        r = self.client.patch(self.detalle("Heredado"), {"name": "Heredado 2"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_el_rol_admin_sigue_protegido(self) -> None:
        r = self.client.patch(self.detalle(ROL_ADMIN), {"nivel": 50})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(PerfilRol.objects.filter(grupo__name=ROL_ADMIN).exists())

    def test_eliminar_un_rol_creado_elimina_su_perfil(self) -> None:
        self.client.post(self.url, {"name": "Supervisor", "nivel": 25})
        r = self.client.delete(self.detalle("Supervisor"))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(PerfilRol.objects.filter(grupo__name="Supervisor").exists())
