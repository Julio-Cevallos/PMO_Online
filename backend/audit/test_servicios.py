import json
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase, override_settings

from entities.utiles_pruebas import entidad, usuario

from .models import Categoria, EventoAuditoria
from .servicios import (
    OCULTO,
    cambios_de_alta,
    diferencias,
    ip_de,
    registrar,
    valores,
)


def peticion(user=None, **meta):
    """Una petición mínima: lo que `registrar` necesita (usuario y cabeceras)."""
    anonimo = SimpleNamespace(is_authenticated=False)
    return SimpleNamespace(user=user or anonimo, META={"REMOTE_ADDR": "10.1.2.3", **meta})


class RegistrarTests(TestCase):
    def setUp(self) -> None:
        self.ana = usuario("ana")

    def test_toma_al_usuario_y_la_ip_de_la_peticion(self) -> None:
        evento = registrar(
            accion="usuario.crear", categoria=Categoria.SISTEMA, request=peticion(self.ana)
        )
        self.assertEqual(
            (evento.usuario_id, evento.usuario_nombre, evento.ip), (self.ana.pk, "ana", "10.1.2.3")
        )
        self.assertEqual((evento.categoria, evento.accion), ("sistema", "usuario.crear"))

    def test_el_usuario_se_puede_indicar_a_mano(self) -> None:
        luis = usuario("luis")
        evento = registrar(
            accion="usuario.registrar",
            categoria=Categoria.SISTEMA,
            request=peticion(),
            usuario=luis,
        )
        self.assertEqual(evento.usuario_nombre, "luis")

    def test_sin_sesion_ni_usuario_queda_sin_autor(self) -> None:
        evento = registrar(accion="sistema.tarea", categoria=Categoria.SISTEMA)
        self.assertEqual((evento.usuario_id, evento.usuario_nombre, evento.ip), (None, "", None))

    def test_guarda_el_objeto_afectado(self) -> None:
        luis = usuario("luis")
        evento = registrar(accion="usuario.editar", categoria=Categoria.SISTEMA, objeto=luis)
        self.assertEqual(
            (evento.objeto_tipo, evento.objeto_id, evento.objeto_nombre),
            ("accounts.user", str(luis.pk), "luis"),
        )

    def test_guarda_la_entidad(self) -> None:
        alfa = entidad("Alfa")
        evento = registrar(
            accion="entidad.editar", categoria=Categoria.ENTIDAD, entidad=alfa, objeto=alfa
        )
        self.assertEqual((evento.entidad_id, evento.entidad_nombre), (alfa.pk, "Alfa"))

    def test_el_historial_no_depende_de_que_el_usuario_siga_igual(self) -> None:
        """Sin llaves foráneas: renombrar o borrar al usuario no altera el evento."""
        evento = registrar(
            accion="usuario.crear", categoria=Categoria.SISTEMA, request=peticion(self.ana)
        )
        self.ana.username = "ana_renombrada"
        self.ana.save()
        self.assertEqual(EventoAuditoria.objects.get(pk=evento.pk).usuario_nombre, "ana")
        identificador = self.ana.pk
        self.ana.delete()
        evento.refresh_from_db()
        self.assertEqual((evento.usuario_id, evento.usuario_nombre), (identificador, "ana"))

    def test_categoria_invalida(self) -> None:
        with self.assertRaises(ValueError):
            registrar(accion="a.b", categoria="otra")

    def test_guarda_cambios_y_detalle(self) -> None:
        evento = registrar(
            accion="rol.editar",
            categoria=Categoria.SISTEMA,
            cambios=diferencias({"nombre": "A"}, {"nombre": "B"}),
            detalle={"motivo": "prueba", "fecha": date(2026, 10, 29)},
        )
        evento.refresh_from_db()
        self.assertEqual(evento.cambios, [{"campo": "nombre", "antes": "A", "despues": "B"}])
        self.assertEqual(evento.detalle, {"motivo": "prueba", "fecha": "2026-10-29"})


class IpTests(TestCase):
    def test_usa_la_direccion_de_la_conexion(self) -> None:
        self.assertEqual(ip_de(peticion()), "10.1.2.3")

    def test_ignora_x_forwarded_for_si_no_hay_proxy_de_confianza(self) -> None:
        self.assertEqual(ip_de(peticion(HTTP_X_FORWARDED_FOR="8.8.8.8")), "10.1.2.3")

    @override_settings(AUDIT_TRUST_PROXY=True)
    def test_con_proxy_de_confianza_usa_el_primer_valor_de_x_forwarded_for(self) -> None:
        self.assertEqual(ip_de(peticion(HTTP_X_FORWARDED_FOR="8.8.8.8, 10.0.0.1")), "8.8.8.8")

    @override_settings(AUDIT_TRUST_PROXY=True)
    def test_un_valor_falso_no_se_guarda(self) -> None:
        self.assertEqual(ip_de(peticion(HTTP_X_FORWARDED_FOR="no-es-una-ip")), "10.1.2.3")

    def test_direcciones_invalidas_o_ausentes(self) -> None:
        self.assertIsNone(ip_de(None))
        self.assertIsNone(ip_de(SimpleNamespace(META={"REMOTE_ADDR": "basura"})))
        self.assertIsNone(ip_de(SimpleNamespace(META={})))

    def test_ipv6(self) -> None:
        self.assertEqual(ip_de(SimpleNamespace(META={"REMOTE_ADDR": "::1"})), "::1")


class CambiosTests(TestCase):
    def test_solo_los_campos_que_cambiaron(self) -> None:
        antes = {"nombre": "A", "estado": "activa", "descripcion": ""}
        despues = {"nombre": "B", "estado": "activa", "descripcion": ""}
        self.assertEqual(
            diferencias(antes, despues), [{"campo": "nombre", "antes": "A", "despues": "B"}]
        )

    def test_sin_cambios(self) -> None:
        self.assertEqual(diferencias({"a": 1}, {"a": 1}), [])

    def test_un_campo_nuevo_o_quitado(self) -> None:
        self.assertEqual(
            diferencias({"a": 1}, {"b": 2}),
            [
                {"campo": "a", "antes": 1, "despues": None},
                {"campo": "b", "antes": None, "despues": 2},
            ],
        )

    def test_las_listas_se_comparan_por_contenido(self) -> None:
        self.assertEqual(diferencias({"permisos": ["a"]}, {"permisos": ["a"]}), [])
        self.assertEqual(
            diferencias({"permisos": ["a"]}, {"permisos": ["a", "b"]}),
            [{"campo": "permisos", "antes": ["a"], "despues": ["a", "b"]}],
        )

    def test_alta(self) -> None:
        self.assertEqual(
            cambios_de_alta({"nombre": "A", "activo": True}),
            [
                {"campo": "nombre", "antes": None, "despues": "A"},
                {"campo": "activo", "antes": None, "despues": True},
            ],
        )

    def test_las_contrasenas_y_tokens_nunca_se_guardan(self) -> None:
        secreto, otro = "Clave-Super-Secreta-1", "Otra-Clave-2"
        cambios = diferencias({"password": secreto}, {"password": otro})
        evento = registrar(
            accion="usuario.cambiar_clave", categoria=Categoria.SISTEMA, cambios=cambios
        )
        self.assertEqual(cambios, [{"campo": "password", "antes": OCULTO, "despues": OCULTO}])
        guardado = json.dumps(EventoAuditoria.objects.get(pk=evento.pk).cambios)
        self.assertNotIn(secreto, guardado)
        self.assertNotIn(otro, guardado)

    def test_tambien_en_el_alta_y_con_otros_nombres(self) -> None:
        for campo in ("password", "new_password", "token", "access", "refresh"):
            self.assertEqual(
                cambios_de_alta({campo: "valor-secreto"}),
                [{"campo": campo, "antes": OCULTO, "despues": OCULTO}],
            )

    def test_valores_toma_una_foto_de_los_campos(self) -> None:
        luis = usuario("luis")
        foto = valores(luis, ["username", "email", "is_active"])
        self.assertEqual(foto, {"username": "luis", "email": "luis@example.com", "is_active": True})
        luis.email = "otro@example.com"
        self.assertEqual(foto["email"], "luis@example.com")  # la foto no cambia

    def test_los_valores_se_convierten_a_json(self) -> None:
        foto = valores(
            SimpleNamespace(
                f=datetime(2026, 10, 29, 12, 0, tzinfo=UTC),
                d=Decimal("1.50"),
                c={"b", "a"},
                n=None,
                x=object,
            ),
            ["f", "d", "c", "n", "x"],
        )
        self.assertEqual(foto["f"], "2026-10-29T12:00:00+00:00")
        self.assertEqual((foto["d"], foto["c"], foto["n"]), ("1.50", ["a", "b"], None))
        json.dumps(foto)  # no falla

    def test_los_textos_muy_largos_se_recortan(self) -> None:
        foto = valores(SimpleNamespace(t="x" * 5000), ["t"])
        self.assertEqual(len(foto["t"]), 2000)
