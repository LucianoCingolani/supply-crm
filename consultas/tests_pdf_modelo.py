"""El PDF de cotización replica "Planilla para cotizar.docx".

Se verifica el HTML que WeasyPrint convierte, que es donde vive todo lo que
define el documento: el orden de los bloques, la tipografía del modelo, las
condiciones textuales y qué datos salen y cuáles no.
"""

import datetime
import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from consultas import membrete
from consultas.models import Consulta, LineaCotizacion
from productos.models import ARS, USD, Producto

User = get_user_model()

PNG_1PX = bytes.fromhex(
    '89504e470d0a1a0a0000000d494844520000000100000001080600000'
    '01f15c4890000000a49444154789c6300010000050001'
    '0d0a2db40000000049454e44ae426082'
)


def usuario():
    return User.objects.create_user(
        'v@test.com', 'x', first_name='Vera', last_name='Vendedora',
        role=User.GERENTE)


class BasePDFTest(TestCase):
    def setUp(self):
        self.user = usuario()
        self.cliente = Cliente.objects.create(
            razon_social='ACME SRL', cuit='30-71234567-8', vendedor=self.user)
        self.consulta = Consulta.objects.create(
            productos='Recipiente', cliente=self.cliente, vendedor=self.user,
            numero_cotizacion='1914', fecha=datetime.date(2026, 7, 17), moneda=ARS)

    def producto(self, **kwargs):
        base = {
            'codigo': 'R120', 'nombre': 'Recipiente de Residuos de 120 litros',
            'precio': Decimal('87500'), 'moneda': ARS,
            'especificaciones': 'Cabezal desmontable tapa vaivén\n'
                                'Medidas externas 55 x 38 x 121 cm de alto\n'
                                'Uso industrial intenso',
            'colores': 'A eleccion',
        }
        return Producto.objects.create(**{**base, **kwargs})

    def linea(self, producto=None, descripcion=None, precio='87500', moneda=ARS):
        return LineaCotizacion.objects.create(
            consulta=self.consulta,
            producto=producto,
            descripcion=descripcion or (producto.nombre if producto else 'Ítem'),
            cantidad=1, precio_unitario=Decimal(precio), moneda=moneda,
        )

    def html(self):
        return render_to_string('consultas/cotizacion_pdf.html', {
            'consulta': self.consulta,
            **membrete.contexto(),
        })


class EncabezadoTest(BasePDFTest):
    def test_la_fecha_va_en_palabras_como_el_modelo(self):
        self.assertIn('Buenos Aires 17 de julio 2026', self.html())

    def test_el_numero_de_cotizacion(self):
        self.assertIn('Cotizacion 1914', self.html())

    def test_sin_numero_cargado_cae_al_id(self):
        self.consulta.numero_cotizacion = ''
        self.consulta.save()
        self.assertIn(f'Cotizacion {self.consulta.pk}', self.html())

    def test_no_nombra_al_cliente(self):
        """Decisión del modelo: el PDF no lleva razón social ni CUIT."""
        html = self.html()
        self.assertNotIn('ACME SRL', html)
        self.assertNotIn('30-71234567-8', html)

    def test_lleva_el_membrete_embebido(self):
        html = self.html()
        self.assertIn('data:image/jpeg;base64,', html)
        self.assertIn('18.46cm', html)

    def test_lleva_las_tres_tiras_del_pie(self):
        """El pie del modelo son tres tiras de familias de producto."""
        self.assertEqual(len(membrete.contexto()['img_familias']), 3)
        for img in membrete.contexto()['img_familias']:
            self.assertTrue(img.startswith('data:image/'))

    def test_numera_las_paginas(self):
        self.assertIn('counter(page)', self.html())


class BloqueDeProductoTest(BasePDFTest):
    def test_el_titulo_es_la_descripcion_con_dos_puntos(self):
        self.linea(self.producto())
        self.assertIn('Recipiente de Residuos de 120 litros:', self.html())

    def test_usa_la_descripcion_de_la_linea_no_la_del_catalogo(self):
        """El vendedor puede ajustar el texto al armar la cotización."""
        self.linea(self.producto(), descripcion='Recipiente 120L color especial')
        self.assertIn('Recipiente 120L color especial:', self.html())

    def test_la_descripcion_del_articulo_sale_siempre(self):
        """Si el vendedor ajustó la de la línea, la del catálogo va igual: es la
        que identifica al artículo."""
        self.linea(self.producto(), descripcion='Recipiente 120L color especial')

        html = self.html()
        self.assertIn('Recipiente 120L color especial:', html)
        self.assertIn('Recipiente de Residuos de 120 litros', html)

    def test_no_la_repite_cuando_es_la_misma(self):
        self.linea(self.producto())
        self.assertEqual(
            self.html().count('Recipiente de Residuos de 120 litros'), 1)

    def test_ignora_diferencias_de_espacios(self):
        self.linea(self.producto(), descripcion='  Recipiente de Residuos de 120 litros  ')
        self.assertEqual(
            self.html().count('Recipiente de Residuos de 120 litros'), 1)

    def test_una_linea_sin_articulo_no_inventa_descripcion(self):
        linea = self.linea(descripcion='Servicio de instalación')
        self.assertEqual(linea.descripcion_del_articulo, '')

    def test_imprime_cada_especificacion_en_su_linea(self):
        self.linea(self.producto())
        html = self.html()
        for spec in ('Cabezal desmontable tapa vaivén',
                     'Medidas externas 55 x 38 x 121 cm de alto',
                     'Uso industrial intenso'):
            with self.subTest(spec=spec):
                self.assertIn(spec, html)

    def test_imprime_los_colores_del_articulo(self):
        self.linea(self.producto())
        self.assertIn('Colores:', self.html())
        self.assertIn('A eleccion', self.html())

    def test_sin_colores_cargados_no_imprime_la_linea(self):
        self.linea(self.producto(colores=''))
        self.assertNotIn('Colores:', self.html())

    def test_el_precio_unitario_como_el_modelo(self):
        self.linea(self.producto())
        self.assertIn('Precio unitario:', self.html())
        self.assertIn('$ 87.500 + IVA', self.html())

    def test_no_imprime_cantidades_ni_totales(self):
        """El modelo cotiza la unidad: sin cantidad, sin subtotal, sin total."""
        self.linea(self.producto())
        html = self.html()
        for prohibido in ('Cantidad', 'Subtotal', 'Total c/ IVA', 'IVA (21%)'):
            with self.subTest(prohibido=prohibido):
                self.assertNotIn(prohibido, html)

    def test_incluye_la_foto_del_articulo(self):
        self.linea(self.producto(foto=PNG_1PX, foto_tipo='image/png'))
        self.assertIn('data:image/png;base64,', self.html())

    def test_deja_aire_entre_el_precio_y_la_foto(self):
        """Pegada al precio se lee como parte de esa línea."""
        self.linea(self.producto(foto=PNG_1PX, foto_tipo='image/png'))

        margen = re.search(r'\.foto\s*\{[^}]*margin-top:\s*([\d.]+)cm', self.html())
        self.assertIsNotNone(margen, 'la foto tiene que separarse con un margen en cm')
        self.assertGreaterEqual(float(margen.group(1)), 1.0)

    def test_el_bloque_no_salta_entero_a_la_hoja_siguiente(self):
        """Con page-break-inside: avoid, un bloque que no entraba bajo el
        membrete se iba completo a la hoja 2 y la primera quedaba con el
        membrete y nada más. Pasó de verdad con una foto grande."""
        self.linea(self.producto(foto=PNG_1PX, foto_tipo='image/png'))
        self.assertNotRegex(self.html(),
                            r'\.producto\s*\{[^}]*page-break-inside:\s*avoid')

    def test_la_foto_entra_debajo_del_texto_en_la_primera_hoja(self):
        """El alto útil bajo el membrete es ~19cm y el texto se come la mitad
        con una lista larga de especificaciones: el tope tiene que dejar aire."""
        self.linea(self.producto(foto=PNG_1PX, foto_tipo='image/png'))

        tope = re.search(r'\.foto img\s*\{[^}]*max-height:\s*([\d.]+)cm', self.html())
        self.assertIsNotNone(tope, 'la foto necesita un tope de alto')
        self.assertLessEqual(float(tope.group(1)), 10.0)

    def test_la_imagen_no_se_parte_entre_hojas(self):
        self.linea(self.producto(foto=PNG_1PX, foto_tipo='image/png'))
        self.assertRegex(self.html(),
                         r'\.foto\s*\{[^}]*page-break-inside:\s*avoid')

    def test_sin_foto_no_deja_el_espacio_colgando(self):
        """El aire va en el bloque de la foto, así que sin foto no queda hueco."""
        self.linea(self.producto())
        self.assertNotIn('class="foto"', self.html())

    def test_sin_foto_no_deja_un_hueco(self):
        self.linea(self.producto())
        self.assertNotIn('Sin imagen', self.html())

    def test_una_linea_sin_articulo_del_catalogo_igual_sale(self):
        """Se puede cotizar algo escrito a mano, sin ficha detrás."""
        self.linea(descripcion='Servicio de instalación', precio='50000')
        html = self.html()
        self.assertIn('Servicio de instalación:', html)
        self.assertIn('$ 50.000 + IVA', html)


class UnaPaginaPorProductoTest(BasePDFTest):
    def test_cada_producto_arranca_en_hoja_nueva(self):
        self.linea(self.producto(), descripcion='Primero')
        self.linea(self.producto(codigo='P2', nombre='Pallet'), descripcion='Segundo')

        html = self.html()
        self.assertIn('page-break-before', html)
        self.assertIn('Primero:', html)
        self.assertIn('Segundo:', html)

    def test_las_condiciones_van_en_su_propia_hoja(self):
        self.linea(self.producto())
        self.assertIn('class="condiciones"', self.html())


class CondicionesTest(BasePDFTest):
    """Las 19 condiciones, con el texto del modelo."""

    ETIQUETAS = [
        'Condiciones de suministro:', 'Tasa de IVA:', 'Disponibilidad:',
        'Mantenimiento de la oferta:', 'Pagos:',
        'Pagos fuera del término acordado', 'Anticipos:', 'Moneda Extranjera:',
        'Garantías:', 'Entregas de mercaderías:', 'Embalaje:',
        'Descargas de mercaderias:',
        'Pedidos no retirados o guardas  de mercaderias:',
        'Lugar y tiempo de descarga o espera de atención para la recepción de',
        'Compromiso de Disponibilidad:', 'Disponibilidad de material importado:',
    ]

    def test_estan_todas_las_etiquetas(self):
        html = self.html()
        for etiqueta in self.ETIQUETAS:
            with self.subTest(etiqueta=etiqueta):
                self.assertIn(etiqueta, html)

    def test_el_texto_es_el_del_modelo_no_el_reescrito(self):
        html = self.html()
        self.assertIn('7 dias', html)                       # antes decía 24 hs
        self.assertIn('A confirmar según cola de fabricación', html)
        self.assertIn('cheque o e/check personal al día', html)

    def test_conserva_las_direcciones_de_correo(self):
        html = self.html()
        self.assertIn('facturacion@supplyargentina.com.ar', html)
        self.assertIn('supply.argentina@gmail.com', html)

    def test_el_cierre_del_modelo(self):
        html = self.html()
        self.assertIn('Esperamos su favorable respuesta, atte.: Dpto. ventas', html)
        self.assertIn('0810 444 0152', html)
        self.assertIn('Neuquen 4044 - Villa Ballester - Buenos Aires', html)


class TipografiaTest(BasePDFTest):
    """El modelo usa Calibri para el cuerpo y Segoe UI para los títulos."""

    def test_declara_las_fuentes_con_sus_sustitutos(self):
        """Carlito y no DejaVu: fonts-dejavu-core no trae la oblicua, y sin ella
        el título del modelo perdía la itálica."""
        html = self.html()
        self.assertIn('Calibri, Carlito', html)
        self.assertIn('"Segoe UI", Carlito', html)

    def test_el_titulo_lleva_el_color_y_la_italica_del_modelo(self):
        html = self.html()
        self.assertIn('#163358', html)
        self.assertIn('font-style: italic', html)

    def test_los_margenes_laterales_son_los_del_modelo(self):
        self.assertIn('1.27cm', self.html())

    def test_las_condiciones_no_van_justificadas(self):
        """El modelo las tiene alineadas a la izquierda."""
        self.assertNotIn('text-align: justify', self.html())


class MembreteSoloEnLaPrimeraTest(BasePDFTest):
    """El membrete va una sola vez; el pie sí se repite.

    La diferencia está en el mecanismo: `position: fixed` es lo que hace que
    WeasyPrint repita un elemento en cada hoja. El membrete no puede usarlo o
    volvería a aparecer en todas.
    """

    def test_el_membrete_no_es_un_elemento_fijo(self):
        self.assertNotRegex(self.html(), r'\.membrete\s*\{[^}]*position:\s*fixed')

    def test_la_banda_del_membrete_se_reserva_solo_en_la_primera_hoja(self):
        html = self.html()
        self.assertRegex(html, r'@page\s*:first\s*\{[^}]*margin-top')

    def test_las_hojas_de_continuacion_despegan_el_texto_del_borde(self):
        """Sin membrete arriba, el margen del modelo (0,5cm) deja el texto al filo."""
        margen = re.search(r'@page\s*\{[^}]*margin:\s*([\d.]+)cm', self.html())
        self.assertIsNotNone(margen)
        self.assertGreaterEqual(float(margen.group(1)), 1.0)

    def test_el_pie_sigue_repitiendose_en_cada_hoja(self):
        html = self.html()
        self.assertRegex(html, r'\.pie\s*\{[^}]*position:\s*fixed')
        self.assertRegex(html, r'\.pie\s*\{[^}]*bottom:\s*-\d')

    def test_el_body_no_reserva_espacio_con_padding(self):
        """Reservarlo así solo corre el contenido de la primera hoja."""
        html = self.html()
        self.assertNotRegex(html, r'body\s*\{[^}]*padding-top:\s*\d')
        self.assertNotRegex(html, r'body\s*\{[^}]*padding-bottom:\s*\d')


class GuardaTipoDeCambioTest(BasePDFTest):
    """Sin tipo de cambio no se puede convertir el precio de la línea."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.url = reverse('consultas:cotizacion_pdf', args=[self.consulta.pk])

    def test_se_niega_si_falta_el_tipo_de_cambio(self):
        self.linea(self.producto(), moneda=USD, precio='250')
        respuesta = self.client.get(self.url)
        self.assertRedirects(
            respuesta, reverse('consultas:cotizacion', args=[self.consulta.pk]))

    def test_con_el_tipo_de_cambio_convierte_el_precio_unitario(self):
        self.consulta.tipo_cambio = Decimal('1000')
        self.consulta.save()
        self.linea(self.producto(), moneda=USD, precio='250')
        self.assertIn('$ 250.000 + IVA', self.html())
