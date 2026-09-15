"""La alícuota de IVA con la que sale la cotización.

No todas las operaciones van al 21%: hay clientes en provincias que no tributan
IVA y hay artículos que van al 10,5%. Antes el 21% estaba escrito a mano en el
modelo y en las tres pantallas, así que al cliente exento le salía impreso un
IVA que nadie le iba a facturar.
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from consultas import membrete
from consultas.models import (IVA_EXENTO, IVA_GENERAL, IVA_REDUCIDO, Consulta,
                              LineaCotizacion)
from productos.models import ARS

User = get_user_model()


def usuario(email='vendedor@test.com'):
    return User.objects.create_user(
        email=email, password='x', first_name='Test', last_name='User',
        role=User.GERENTE)


class BaseIVATest(TestCase):
    def setUp(self):
        self.user = usuario()
        self.cliente = Cliente.objects.create(
            razon_social='ACME SRL', cuit='30-71234567-8', vendedor=self.user)
        self.consulta = Consulta.objects.create(
            productos='Recipiente', cliente=self.cliente, vendedor=self.user,
            razon_social='ACME SRL', numero_cotizacion='1914',
            fecha=datetime.date(2026, 7, 17), moneda=ARS)
        self.client.force_login(self.user)

    def linea(self, precio='100000', cantidad='1'):
        return LineaCotizacion.objects.create(
            consulta=self.consulta, descripcion='Recipiente 120L',
            cantidad=Decimal(cantidad), precio_unitario=Decimal(precio), moneda=ARS)

    def html(self):
        self.consulta.refresh_from_db()
        return render_to_string('consultas/cotizacion_pdf.html', {
            'consulta': self.consulta,
            'totales': self.consulta.totales(),
            **membrete.contexto(),
        })


class TotalesTest(BaseIVATest):
    def test_por_defecto_cotiza_al_21(self):
        """La alícuota general: la de casi siempre, que no hay que elegir."""
        self.linea()

        totales = self.consulta.totales()
        self.assertEqual(self.consulta.alicuota_iva, IVA_GENERAL)
        self.assertEqual(totales.iva, Decimal('21000.00'))
        self.assertEqual(totales.con_iva, Decimal('121000.00'))

    def test_al_105_el_iva_es_la_mitad(self):
        self.consulta.alicuota_iva = IVA_REDUCIDO
        self.consulta.save()
        self.linea()

        totales = self.consulta.totales()
        self.assertEqual(totales.iva, Decimal('10500.00'))
        self.assertEqual(totales.con_iva, Decimal('110500.00'))

    def test_exenta_no_suma_nada(self):
        """El total sigue donde estaba: `con_iva` iguala al neto."""
        self.consulta.alicuota_iva = IVA_EXENTO
        self.consulta.save()
        self.linea()

        totales = self.consulta.totales()
        self.assertEqual(totales.iva, Decimal('0.00'))
        self.assertEqual(totales.con_iva, totales.neto)
        self.assertEqual(totales.con_iva, Decimal('100000.00'))

    def test_redondea_al_centavo(self):
        self.consulta.alicuota_iva = IVA_REDUCIDO
        self.consulta.save()
        self.linea(precio='333.33')

        self.assertEqual(self.consulta.totales().iva, Decimal('35.00'))

    def test_cotiza_con_iva_solo_es_falso_en_la_exenta(self):
        for alicuota, esperado in [(IVA_GENERAL, True), (IVA_REDUCIDO, True),
                                   (IVA_EXENTO, False)]:
            with self.subTest(alicuota=alicuota):
                self.consulta.alicuota_iva = alicuota
                self.assertIs(self.consulta.cotiza_con_iva, esperado)

    def test_el_porcentaje_se_escribe_con_coma_y_sin_ceros_de_mas(self):
        """Va impreso en la cotización: "10,5%", no "10.50%"."""
        self.consulta.alicuota_iva = IVA_GENERAL
        self.assertEqual(self.consulta.iva_porcentaje, '21')

        self.consulta.alicuota_iva = IVA_REDUCIDO
        self.assertEqual(self.consulta.iva_porcentaje, '10,5')

    def test_el_porcentaje_sale_igual_leido_de_la_base(self):
        """La base devuelve Decimal('10.50'); el texto no puede cambiar por eso."""
        self.consulta.alicuota_iva = IVA_REDUCIDO
        self.consulta.save()
        self.consulta.refresh_from_db()

        self.assertEqual(self.consulta.iva_porcentaje, '10,5')


class PDFTest(BaseIVATest):
    """Lo que ve el cliente. Un IVA impreso de más es plata que no se factura."""

    def test_al_21_discrimina_como_siempre(self):
        self.linea()

        html = self.html()
        self.assertIn('IVA (21%)', html)
        self.assertIn('Total c/ IVA', html)
        self.assertIn('$ 21.000,00', html)

    def test_al_105_lo_dice_en_los_totales_y_en_las_condiciones(self):
        self.consulta.alicuota_iva = IVA_REDUCIDO
        self.consulta.save()
        self.linea()

        html = self.html()
        self.assertIn('IVA (10,5%)', html)
        self.assertIn('$ 10.500,00', html)
        self.assertIn('Tasa de IVA:', html)
        self.assertIn('10,5%', html)
        self.assertNotIn('IVA (21%)', html)

    def test_exenta_no_nombra_el_iva_en_ninguna_parte(self):
        self.consulta.alicuota_iva = IVA_EXENTO
        self.consulta.save()
        self.linea()

        html = self.html()
        self.assertNotIn('IVA (21%)', html)
        self.assertNotIn('Total c/ IVA', html)
        self.assertNotIn('+ IVA', html)
        self.assertIn('Operación exenta de IVA', html)

    def test_exenta_imprime_el_neto_como_total(self):
        self.consulta.alicuota_iva = IVA_EXENTO
        self.consulta.save()
        self.linea()

        html = self.html()
        self.assertIn('$ 100.000,00', html)
        self.assertNotIn('$ 121.000,00', html)


class ElegirLaAlicuotaTest(BaseIVATest):
    """El panel de la cotización ya armada."""

    def _url(self):
        return reverse('consultas:cotizacion', args=[self.consulta.pk])

    def _guardar(self, alicuota):
        return self.client.post(self._url(), {
            'action': 'moneda', 'moneda': ARS, 'tipo_cambio': '',
            'alicuota_iva': alicuota,
        })

    def test_la_guarda_junto_con_la_moneda(self):
        self._guardar('0')

        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.alicuota_iva, IVA_EXENTO)

    def test_guarda_la_reducida(self):
        self._guardar('10.5')

        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.alicuota_iva, IVA_REDUCIDO)

    def test_una_alicuota_inventada_no_entra(self):
        """Solo se cotiza con las tres que la empresa factura."""
        self.consulta.alicuota_iva = IVA_REDUCIDO
        self.consulta.save()

        self._guardar('35')

        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.alicuota_iva, IVA_REDUCIDO)

    def test_un_valor_ilegible_deja_la_que_estaba(self):
        self.consulta.alicuota_iva = IVA_EXENTO
        self.consulta.save()

        self._guardar('veintiuno')

        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.alicuota_iva, IVA_EXENTO)

    def test_el_selector_sale_en_la_pantalla(self):
        respuesta = self.client.get(self._url())

        self.assertContains(respuesta, 'alicuota_iva')
        self.assertContains(respuesta, 'Exento (sin IVA)')


class NuevaCotizacionTest(TestCase):
    """La alícuota se elige en el encabezado, al armar la cotización."""

    def setUp(self):
        self.user = usuario()
        self.cliente = Cliente.objects.create(
            razon_social='ACME SRL', vendedor=self.user)
        self.client.force_login(self.user)
        self.url = reverse('consultas:nueva_cotizacion', args=[self.cliente.pk])

    def _post(self, **extra):
        datos = {
            'moneda': ARS, 'tipo_cambio': '', 'fecha': '2026-07-17',
            'via_entrada': 'mail', 'numero_cotizacion': '1914',
            'linea_desc_0': 'Recipiente 120L', 'linea_cant_0': '1',
            'linea_precio_0': '100000', 'linea_moneda_0': ARS, 'linea_prod_0': '',
        }
        datos.update(extra)
        return self.client.post(self.url, datos)

    def test_nace_al_21_si_no_se_elige(self):
        self._post()

        self.assertEqual(Consulta.objects.get().alicuota_iva, IVA_GENERAL)

    def test_se_puede_crear_exenta(self):
        self._post(alicuota_iva='0')

        consulta = Consulta.objects.get()
        self.assertEqual(consulta.alicuota_iva, IVA_EXENTO)
        self.assertEqual(consulta.totales().con_iva, Decimal('100000.00'))

    def test_se_puede_crear_al_105(self):
        self._post(alicuota_iva='10.5')

        consulta = Consulta.objects.get()
        self.assertEqual(consulta.alicuota_iva, IVA_REDUCIDO)
        self.assertEqual(consulta.totales().iva, Decimal('10500.00'))

    def test_el_selector_sale_en_el_formulario(self):
        respuesta = self.client.get(self.url)

        self.assertContains(respuesta, 'alicuota_iva')
        self.assertContains(respuesta, '10,5%')
