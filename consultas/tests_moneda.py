"""Cotizaciones en pesos y en dólares.

Lo que se protege acá es que un total nunca mezcle monedas. Antes las líneas
eran números pelados y sumarlas daba un número sin significado que igual salía
impreso en el PDF del cliente.
"""

import unittest
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.template.loader import render_to_string
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from clientes.models import Cliente
from consultas.models import Consulta, LineaCotizacion
from productos.models import ARS, USD, Producto

User = get_user_model()


def _weasyprint_anda():
    """En Windows suelen faltar las libs nativas de GTK; en el server están."""
    try:
        import weasyprint  # noqa: F401
    except Exception:
        return False
    return True


WEASYPRINT = _weasyprint_anda()


def usuario(email='vendedor@test.com', role=User.GERENTE):
    return User.objects.create_user(
        email=email, password='x', first_name='Test', last_name='User', role=role,
    )


def consulta_de(user, cliente=None, **kwargs):
    return Consulta.objects.create(
        productos='Consulta de prueba',
        cliente=cliente,
        vendedor=user,
        **kwargs,
    )


def linea(consulta, precio, moneda=ARS, cantidad=1, descripcion='Ítem'):
    return LineaCotizacion.objects.create(
        consulta=consulta, descripcion=descripcion,
        cantidad=Decimal(cantidad), precio_unitario=Decimal(precio), moneda=moneda,
    )


class ConversionTest(TestCase):
    def setUp(self):
        self.user = usuario()

    def test_sin_mezcla_no_hace_falta_tipo_de_cambio(self):
        c = consulta_de(self.user, moneda=ARS)
        linea(c, '1000', ARS)
        linea(c, '500', ARS)

        self.assertFalse(c.falta_tipo_cambio)
        self.assertEqual(c.totales().neto, Decimal('1500.00'))

    def test_convierte_dolares_a_pesos(self):
        c = consulta_de(self.user, moneda=ARS, tipo_cambio=Decimal('1000'))
        linea(c, '10', USD)

        self.assertEqual(c.totales().neto, Decimal('10000.00'))

    def test_convierte_pesos_a_dolares(self):
        c = consulta_de(self.user, moneda=USD, tipo_cambio=Decimal('1000'))
        linea(c, '10000', ARS)

        self.assertEqual(c.totales().neto, Decimal('10.00'))

    def test_suma_las_dos_monedas_en_la_de_la_cotizacion(self):
        c = consulta_de(self.user, moneda=ARS, tipo_cambio=Decimal('1000'))
        linea(c, '5000', ARS)
        linea(c, '10', USD)  # = 10.000 pesos

        totales = c.totales()
        self.assertEqual(totales.neto, Decimal('15000.00'))
        self.assertEqual(totales.iva, Decimal('3150.00'))
        self.assertEqual(totales.con_iva, Decimal('18150.00'))

    def test_multiplica_por_la_cantidad_antes_de_convertir(self):
        c = consulta_de(self.user, moneda=ARS, tipo_cambio=Decimal('1000'))
        linea(c, '10', USD, cantidad=3)

        self.assertEqual(c.totales().neto, Decimal('30000.00'))

    def test_sin_tipo_de_cambio_no_hay_total(self):
        """El caso que antes devolvía un número inventado."""
        c = consulta_de(self.user, moneda=ARS)
        linea(c, '5000', ARS)
        linea(c, '10', USD)

        self.assertTrue(c.falta_tipo_cambio)
        self.assertIsNone(c.totales())

    def test_cambiar_el_tipo_de_cambio_recalcula(self):
        """Las líneas guardan su precio original, no el convertido."""
        c = consulta_de(self.user, moneda=ARS, tipo_cambio=Decimal('1000'))
        linea(c, '10', USD)
        self.assertEqual(c.totales().neto, Decimal('10000.00'))

        c.tipo_cambio = Decimal('1500')
        c.save()
        self.assertEqual(c.totales().neto, Decimal('15000.00'))

    def test_cambiar_la_moneda_de_la_cotizacion_da_vuelta_la_conversion(self):
        c = consulta_de(self.user, moneda=ARS, tipo_cambio=Decimal('1000'))
        linea(c, '10000', ARS)
        self.assertEqual(c.totales().neto, Decimal('10000.00'))

        c.moneda = USD
        c.save()
        self.assertEqual(c.totales().neto, Decimal('10.00'))

    def test_una_cotizacion_vacia_da_cero(self):
        c = consulta_de(self.user, moneda=ARS)
        self.assertEqual(c.totales().neto, Decimal('0.00'))

    def test_el_simbolo_sigue_a_la_moneda(self):
        self.assertEqual(consulta_de(self.user, moneda=ARS).simbolo_moneda, '$')
        self.assertEqual(consulta_de(self.user, moneda=USD).simbolo_moneda, 'u$s')


class PDFTest(TestCase):
    """El PDF es lo que ve el cliente: o sale bien o no sale."""

    def setUp(self):
        self.user = usuario()
        self.cliente = Cliente.objects.create(razon_social='ACME SRL', vendedor=self.user)
        self.client.force_login(self.user)

    def _pdf(self, consulta):
        return self.client.get(reverse('consultas:cotizacion_pdf', args=[consulta.pk]))

    def test_se_niega_a_generarlo_si_falta_el_tipo_de_cambio(self):
        c = consulta_de(self.user, self.cliente, moneda=ARS)
        linea(c, '5000', ARS)
        linea(c, '10', USD)

        respuesta = self._pdf(c)
        self.assertRedirects(respuesta, reverse('consultas:cotizacion', args=[c.pk]))

    @unittest.skipUnless(WEASYPRINT, 'WeasyPrint no tiene sus libs nativas acá')
    def test_lo_genera_cuando_la_moneda_cierra(self):
        c = consulta_de(self.user, self.cliente, moneda=ARS, tipo_cambio=Decimal('1000'))
        linea(c, '5000', ARS)
        linea(c, '10', USD)

        respuesta = self._pdf(c)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')


class HTMLDelPDFTest(TestCase):
    """El HTML que se convierte a PDF, sin depender de las libs de WeasyPrint.

    Acá vivía el bug: el template imprimía 'u$s' fijo en cada línea y en cada
    total, así que toda cotización salía en dólares dijera lo que dijera.
    """

    def setUp(self):
        self.user = usuario()
        self.cliente = Cliente.objects.create(razon_social='ACME SRL', vendedor=self.user)

    def _html(self, consulta):
        from consultas import membrete
        return render_to_string('consultas/cotizacion_pdf.html', {
            'consulta': consulta,
            **membrete.contexto(),
        })

    def test_una_cotizacion_en_pesos_no_dice_dolares(self):
        c = consulta_de(self.user, self.cliente, moneda=ARS)
        linea(c, '1000', ARS)

        html = self._html(c)
        self.assertNotIn('u$s', html)
        self.assertIn('$ 1.000 + IVA', html)

    def test_una_cotizacion_en_dolares_lo_dice(self):
        c = consulta_de(self.user, self.cliente, moneda=USD)
        linea(c, '250', USD)

        self.assertIn('u$s 250 + IVA', self._html(c))

    def test_imprime_los_montos_ya_convertidos(self):
        c = consulta_de(self.user, self.cliente, moneda=ARS, tipo_cambio=Decimal('1000'))
        linea(c, '10', USD)  # = 10.000 pesos

        html = self._html(c)
        self.assertIn('$ 10.000 + IVA', html)
        self.assertNotIn('u$s', html)

    def test_conserva_los_centavos_cuando_existen(self):
        """El modelo escribe "$ 87.500", pero un precio en dólares suele tener
        centavos y perderlos sería cotizar otro número."""
        c = consulta_de(self.user, self.cliente, moneda=USD)
        linea(c, '49.50', USD)

        self.assertIn('u$s 49,50 + IVA', self._html(c))


class PantallaCotizacionTest(TestCase):
    def setUp(self):
        self.user = usuario()
        self.cliente = Cliente.objects.create(razon_social='ACME SRL', vendedor=self.user)
        self.consulta = consulta_de(self.user, self.cliente, moneda=ARS)
        self.url = reverse('consultas:cotizacion', args=[self.consulta.pk])
        self.client.force_login(self.user)

    def test_la_linea_toma_la_moneda_que_se_eligio(self):
        self.client.post(self.url, {
            'action': 'add', 'descripcion': 'Bomba', 'cantidad': '1',
            'precio_unitario': '250', 'moneda': USD,
        })
        self.assertEqual(LineaCotizacion.objects.get().moneda, USD)

    def test_una_moneda_inventada_cae_en_la_de_la_cotizacion(self):
        self.client.post(self.url, {
            'action': 'add', 'descripcion': 'Bomba', 'cantidad': '1',
            'precio_unitario': '250', 'moneda': 'BTC',
        })
        self.assertEqual(LineaCotizacion.objects.get().moneda, ARS)

    def test_guarda_moneda_y_tipo_de_cambio(self):
        self.client.post(self.url, {
            'action': 'moneda', 'moneda': USD, 'tipo_cambio': '1350,50',
        })
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.moneda, USD)
        self.assertEqual(self.consulta.tipo_cambio, Decimal('1350.5000'))

    def test_rechaza_un_tipo_de_cambio_que_no_es_numero(self):
        self.client.post(self.url, {
            'action': 'moneda', 'moneda': ARS, 'tipo_cambio': 'mil',
        })
        self.consulta.refresh_from_db()
        self.assertIsNone(self.consulta.tipo_cambio)

    def test_rechaza_un_tipo_de_cambio_negativo(self):
        self.client.post(self.url, {
            'action': 'moneda', 'moneda': ARS, 'tipo_cambio': '-50',
        })
        self.consulta.refresh_from_db()
        self.assertIsNone(self.consulta.tipo_cambio)

    def test_avisa_en_pantalla_que_falta_el_tipo_de_cambio(self):
        linea(self.consulta, '10', USD)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'Falta el tipo de cambio')


class QueriesTest(TestCase):
    """Convertir línea por línea no puede costar una query por línea.

    `linea.precio_convertido` lee `linea.consulta`; el prefetch de la vista ya
    deja esa relación cacheada, y esto lo mantiene así.
    """

    def test_el_costo_no_crece_con_la_cantidad_de_lineas(self):
        user = usuario()
        cliente = Cliente.objects.create(razon_social='ACME SRL', vendedor=user)
        self.client.force_login(user)

        def queries_con(cantidad_lineas):
            consulta = consulta_de(user, cliente, moneda=ARS, tipo_cambio=Decimal('1000'))
            for i in range(cantidad_lineas):
                linea(consulta, '10', USD, descripcion=f'Ítem {i}')
            url = reverse('consultas:cotizacion', args=[consulta.pk])
            with CaptureQueriesContext(connection) as capturadas:
                self.client.get(url)
            return len(capturadas)

        self.assertEqual(queries_con(2), queries_con(20))


class NuevaCotizacionMonedaTest(TestCase):
    def setUp(self):
        self.user = usuario()
        self.cliente = Cliente.objects.create(razon_social='ACME SRL', vendedor=self.user)
        self.url = reverse('consultas:nueva_cotizacion', args=[self.cliente.pk])
        self.client.force_login(self.user)

    def _post(self, **extra):
        datos = {
            'fecha': '2026-08-07', 'via_entrada': 'mail', 'moneda': ARS,
            'linea_desc_0': 'Bomba', 'linea_cant_0': '1',
            'linea_precio_0': '100', 'linea_moneda_0': ARS, 'linea_prod_0': '',
        }
        datos.update(extra)
        return self.client.post(self.url, datos)

    def test_guarda_la_moneda_de_la_cotizacion_y_de_cada_linea(self):
        self._post(moneda=USD, linea_moneda_0=USD)

        consulta = Consulta.objects.get()
        self.assertEqual(consulta.moneda, USD)
        self.assertEqual(consulta.lineas.get().moneda, USD)

    def test_no_deja_crear_una_mezcla_sin_tipo_de_cambio(self):
        self._post(moneda=ARS, linea_moneda_0=USD)
        self.assertFalse(Consulta.objects.exists())

    def test_con_tipo_de_cambio_la_mezcla_pasa(self):
        self._post(moneda=ARS, linea_moneda_0=USD, tipo_cambio='1000')

        consulta = Consulta.objects.get()
        self.assertEqual(consulta.tipo_cambio, Decimal('1000'))
        self.assertEqual(consulta.totales().neto, Decimal('100000.00'))


class ProductoMonedaTest(TestCase):
    def test_el_producto_nace_en_pesos(self):
        producto = Producto.objects.create(codigo='X-1', nombre='Guante')
        self.assertEqual(producto.moneda, ARS)

    def test_el_selector_de_la_cotizacion_lleva_la_moneda_del_producto(self):
        Producto.objects.create(codigo='X-1', nombre='Bomba', precio=Decimal('250'), moneda=USD)
        user = usuario()
        cliente = Cliente.objects.create(razon_social='ACME SRL', vendedor=user)
        consulta = consulta_de(user, cliente)
        self.client.force_login(user)

        respuesta = self.client.get(reverse('consultas:cotizacion', args=[consulta.pk]))
        self.assertContains(respuesta, 'data-moneda="USD"')
