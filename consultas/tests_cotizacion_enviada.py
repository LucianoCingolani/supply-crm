"""El rastro de las cotizaciones que salieron para el cliente.

Antes de esto la consulta no mostraba nada de su propia cotización y nada
registraba que hubiera salido: `estado` nace en "cotizado" el día que se carga
la consulta, así que en la lista todo decía "Cotizado" y el gerente no tenía
manera de saber a quién le faltaba cotización.
"""

import datetime
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente
from consultas.models import Consulta, CotizacionGenerada, LineaCotizacion
from productos.models import ARS, USD

User = get_user_model()


class BaseTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'v@test.com', 'x', first_name='Vera', last_name='Vendedora',
            role=User.GERENTE)
        self.client.force_login(self.user)
        self.cliente = Cliente.objects.create(
            razon_social='ACME SRL', cuit='30-71234567-8', vendedor=self.user)
        self.consulta = Consulta.objects.create(
            productos='Recipiente', cliente=self.cliente, vendedor=self.user,
            razon_social='ACME SRL', numero_cotizacion='1914',
            fecha=datetime.date(2026, 7, 17), moneda=ARS)

    def linea(self, **kwargs):
        base = {'descripcion': 'Recipiente 120 L', 'cantidad': Decimal('2'),
                'precio_unitario': Decimal('1000'), 'moneda': ARS}
        return LineaCotizacion.objects.create(consulta=self.consulta, **{**base, **kwargs})

    def bajar_pdf(self):
        """Baja el PDF con WeasyPrint reemplazado por un doble.

        Se suplanta el módulo entero y no solo `HTML`: en Windows WeasyPrint no
        encuentra sus librerías nativas y ni se puede importar. Acá lo que se
        prueba es qué queda registrado al bajarlo, no el binario —de eso se
        ocupa tests_pdf, que renderiza el HTML sin pasar por la vista.
        """
        falso = MagicMock()
        falso.HTML.return_value.write_pdf.return_value = b'%PDF-fake'
        with patch.dict(sys.modules, {'weasyprint': falso}):
            return self.client.get(
                reverse('consultas:cotizacion_pdf', args=[self.consulta.pk]))


class RegistroAlGenerarPDFTest(BaseTest):
    """Bajar el PDF es el acto de mandar la cotización: se anota solo."""

    def test_generar_el_pdf_deja_registro(self):
        self.linea()
        self.bajar_pdf()

        registro = self.consulta.cotizaciones.get()
        self.assertEqual(registro.numero, '1914')
        self.assertEqual(registro.generada_por, self.user)
        self.assertEqual(registro.total_neto, Decimal('2000.00'))
        self.assertEqual(registro.moneda, ARS)
        # Generada no es enviada: eso lo confirma el vendedor.
        self.assertIsNone(registro.enviada_at)

    def test_bajarlo_dos_veces_seguidas_es_un_solo_envio(self):
        """El que abre el PDF, lo cierra y lo vuelve a bajar para adjuntarlo no
        tiene que dejar tres filas en la ficha."""
        self.linea()
        self.bajar_pdf()
        self.bajar_pdf()
        self.assertEqual(self.consulta.cotizaciones.count(), 1)

    def test_volver_a_cotizar_con_otro_precio_deja_otro_registro(self):
        """Un precio nuevo es una cotización nueva, aunque sea el mismo día."""
        linea = self.linea()
        self.bajar_pdf()
        linea.precio_unitario = Decimal('1500')
        linea.save()
        self.bajar_pdf()

        self.assertEqual(self.consulta.cotizaciones.count(), 2)
        self.assertEqual(
            {c.total_neto for c in self.consulta.cotizaciones.all()},
            {Decimal('2000.00'), Decimal('3000.00')})

    def test_pasada_la_ventana_es_otro_envio(self):
        self.linea()
        self.bajar_pdf()
        viejo = self.consulta.cotizaciones.get()
        CotizacionGenerada.objects.filter(pk=viejo.pk).update(
            fecha=timezone.now() - 2 * CotizacionGenerada.VENTANA_MISMA_DESCARGA)

        self.bajar_pdf()
        self.assertEqual(self.consulta.cotizaciones.count(), 2)

    def test_el_pdf_que_no_se_puede_generar_no_deja_registro(self):
        """Mezcla de monedas sin tipo de cambio: la vista rebota y nada salió."""
        self.linea()
        self.linea(moneda=USD, precio_unitario=Decimal('50'))

        respuesta = self.bajar_pdf()
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(self.consulta.cotizaciones.count(), 0)


class MarcarEnviadaTest(BaseTest):
    def registro(self):
        return CotizacionGenerada.objects.create(
            consulta=self.consulta, numero='1914', generada_por=self.user,
            total_neto=Decimal('2000'), moneda=ARS)

    def url(self, registro):
        return reverse('consultas:cotizacion_enviada',
                       args=[self.consulta.pk, registro.pk])

    def test_marcarla_enviada_la_sella_con_quien_y_cuando(self):
        registro = self.registro()
        self.client.post(self.url(registro))

        registro.refresh_from_db()
        self.assertIsNotNone(registro.enviada_at)
        self.assertEqual(registro.enviada_por, self.user)
        self.assertTrue(registro.fue_enviada)

    def test_se_puede_deshacer(self):
        """Marcarla por error y no poder corregirlo ensucia justo el dato que el
        gerente viene a mirar."""
        registro = self.registro()
        registro.marcar_enviada(self.user)

        self.client.post(self.url(registro), {'accion': 'deshacer'})
        registro.refresh_from_db()
        self.assertIsNone(registro.enviada_at)
        self.assertIsNone(registro.enviada_por)

    def test_no_se_puede_marcar_la_cotizacion_de_otra_consulta(self):
        otra = Consulta.objects.create(
            productos='Otra', cliente=self.cliente, vendedor=self.user)
        registro = self.registro()
        respuesta = self.client.post(
            reverse('consultas:cotizacion_enviada', args=[otra.pk, registro.pk]))

        self.assertEqual(respuesta.status_code, 404)
        registro.refresh_from_db()
        self.assertIsNone(registro.enviada_at)

    def test_quien_solo_mira_no_puede_marcar(self):
        coach = User.objects.create_user('c@test.com', 'x', role=User.COACH)
        self.client.force_login(coach)
        registro = self.registro()

        self.client.post(self.url(registro))
        registro.refresh_from_db()
        self.assertIsNone(registro.enviada_at)


class DetalleTest(BaseTest):
    def detalle(self):
        return self.client.get(reverse('consultas:detail', args=[self.consulta.pk]))

    def test_el_detalle_muestra_las_lineas_y_el_total(self):
        self.linea()
        contenido = self.detalle().content.decode()

        self.assertIn('Recipiente 120 L', contenido)
        self.assertIn('2.000,00', contenido)          # neto
        self.assertIn('2.420,00', contenido)          # con IVA

    def test_sin_cotizacion_lo_dice_en_lugar_de_no_mostrar_nada(self):
        contenido = self.detalle().content.decode()
        self.assertIn('Todavía no se le cargó ninguna cotización', contenido)

    def test_avisa_cuando_nunca_se_genero_el_pdf(self):
        self.linea()
        contenido = self.detalle().content.decode()
        self.assertIn('Nunca se generó el PDF', contenido)

    def test_muestra_quien_genero_la_cotizacion_y_cuando(self):
        self.linea()
        self.bajar_pdf()
        contenido = self.detalle().content.decode()

        self.assertIn('1914', contenido)
        self.assertIn('Vera Vendedora', contenido)
        self.assertIn('La mandé', contenido)

    def test_una_vez_marcada_lo_muestra_enviada(self):
        self.linea()
        self.bajar_pdf()
        self.consulta.cotizaciones.get().marcar_enviada(self.user)

        contenido = self.detalle().content.decode()
        self.assertIn('Enviada al cliente', contenido)
        self.assertNotIn('La mandé', contenido)

    def test_el_total_no_se_recalcula_desde_las_lineas(self):
        """El registro es la foto de lo que se le mandó: si después se cambia el
        precio, lo que se le mandó sigue diciendo lo mismo."""
        linea = self.linea()
        self.bajar_pdf()
        linea.precio_unitario = Decimal('9999')
        linea.save()

        self.assertEqual(self.consulta.cotizaciones.get().total_neto, Decimal('2000.00'))


class ListaTest(BaseTest):
    def lista(self, **params):
        return self.client.get(reverse('consultas:list'), params)

    # El desplegable del filtro repite los textos de los badges, así que las
    # aserciones se anclan en el badge y no en el texto suelto.
    BADGE_SIN = '>Sin cotizar</span>'
    BADGE_ARMADA = 'title="La cotización está armada pero nunca se generó el PDF"'
    BADGE_GENERADO = 'title="Se generó el PDF pero nadie confirmó que se mandó"'
    BADGE_ENVIADA = 'title="Enviada al cliente"'

    def test_la_consulta_sin_cotizacion_sale_sin_cotizar(self):
        self.assertIn(self.BADGE_SIN, self.lista().content.decode())

    def test_la_cotizacion_armada_y_sin_mandar_no_sale_sin_cotizar(self):
        """Tener las líneas cargadas y no haber generado el PDF no es lo mismo
        que no tener nada: son dos cosas distintas para hacer."""
        self.linea()
        contenido = self.lista().content.decode()
        self.assertIn(self.BADGE_ARMADA, contenido)
        self.assertNotIn(self.BADGE_SIN, contenido)

    def test_con_pdf_generado_lo_distingue_de_enviada(self):
        self.linea()
        self.bajar_pdf()
        contenido = self.lista().content.decode()
        self.assertIn(self.BADGE_GENERADO, contenido)
        self.assertNotIn(self.BADGE_ARMADA, contenido)

        self.consulta.cotizaciones.get().marcar_enviada(self.user)
        contenido = self.lista().content.decode()
        self.assertIn(self.BADGE_ENVIADA, contenido)
        self.assertNotIn(self.BADGE_GENERADO, contenido)

    def test_se_puede_filtrar_a_quien_le_falta_la_cotizacion(self):
        cotizada = Consulta.objects.create(
            productos='Ya cotizada', cliente=self.cliente, vendedor=self.user)
        CotizacionGenerada.objects.create(
            consulta=cotizada, generada_por=self.user, moneda=ARS)

        sin = self.lista(cotizacion='sin').context['consultas']
        self.assertEqual([c.pk for c in sin], [self.consulta.pk])

        generadas = self.lista(cotizacion='generada').context['consultas']
        self.assertEqual([c.pk for c in generadas], [cotizada.pk])

        self.assertEqual(self.lista(cotizacion='enviada').context['consultas'], [])

    def test_las_mas_recientes_van_arriba(self):
        """La anotación no tiene que costarle el orden a la lista.

        `annotate` agrega un GROUP BY y con eso Django deja de aplicar el
        ordering del Meta: sin un order_by explícito las consultas salen en el
        orden que quiera la base.
        """
        vieja = Consulta.objects.create(
            productos='La de enero', cliente=self.cliente, vendedor=self.user,
            fecha=datetime.date(2026, 1, 5))
        nueva = Consulta.objects.create(
            productos='La de agosto', cliente=self.cliente, vendedor=self.user,
            fecha=datetime.date(2026, 8, 20))

        # self.consulta es del 17/07/2026: la nueva arriba, la vieja al fondo.
        self.assertEqual(
            [c.pk for c in self.lista().context['consultas']],
            [nueva.pk, self.consulta.pk, vieja.pk])

    def test_el_orden_aguanta_con_el_filtro_puesto(self):
        antigua = Consulta.objects.create(
            productos='Antigua', cliente=self.cliente, vendedor=self.user,
            fecha=datetime.date(2026, 2, 2))
        reciente = Consulta.objects.create(
            productos='Reciente', cliente=self.cliente, vendedor=self.user,
            fecha=datetime.date(2026, 9, 1))

        consultas = self.lista(cotizacion='sin').context['consultas']
        self.assertEqual([c.pk for c in consultas],
                         [reciente.pk, self.consulta.pk, antigua.pk])

    def test_filtrar_por_enviada_deja_solo_las_confirmadas(self):
        registro = CotizacionGenerada.objects.create(
            consulta=self.consulta, generada_por=self.user, moneda=ARS)
        registro.marcar_enviada(self.user)

        enviadas = self.lista(cotizacion='enviada').context['consultas']
        self.assertEqual([c.pk for c in enviadas], [self.consulta.pk])
