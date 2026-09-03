"""El PDF de cotización.

Se verifica el HTML que WeasyPrint convierte, que es donde vive todo lo que
define el documento: el orden de los bloques, la tabla con sus totales, la ficha
de cada artículo, las condiciones y qué datos salen y cuáles no.

El documento volvió al diseño anterior al modelo del .docx: hoja 1 con la tabla
de líneas y los totales, una hoja por artículo y las condiciones al final. Lo
único que no se restituyó es el logo dibujado con CSS que traía ese diseño: la
marca la pone el membrete real de la empresa.
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
        # razon_social copiada, como la deja copiar_datos_del_cliente al cargarla.
        self.consulta = Consulta.objects.create(
            productos='Recipiente', cliente=self.cliente, vendedor=self.user,
            razon_social='ACME SRL', cuit='30-71234567-8',
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

    def linea(self, producto=None, descripcion=None, precio='87500',
              moneda=ARS, cantidad='1'):
        return LineaCotizacion.objects.create(
            consulta=self.consulta,
            producto=producto,
            descripcion=descripcion or (producto.nombre if producto else 'Ítem'),
            cantidad=Decimal(cantidad), precio_unitario=Decimal(precio), moneda=moneda,
        )

    def html(self):
        return render_to_string('consultas/cotizacion_pdf.html', {
            'consulta': self.consulta,
            'totales': self.consulta.totales(),
            **membrete.contexto(),
        })


class EncabezadoTest(BasePDFTest):
    def test_la_fecha_va_en_palabras(self):
        self.assertIn('Buenos Aires, Villa Ballester, 17 de julio de 2026',
                      self.html())

    def test_el_numero_de_cotizacion(self):
        self.assertIn('Cotización N° 1914', self.html())

    def test_sin_numero_cargado_no_inventa_uno(self):
        """El nombre del archivo cae al id, pero el documento no: un número de
        cotización que el cliente no reconoce es peor que ninguno."""
        self.consulta.numero_cotizacion = ''
        self.consulta.save()

        html = self.html()
        self.assertIn('Cotización', html)
        self.assertNotIn(f'Cotización N° {self.consulta.pk}', html)

    def test_nombra_al_cliente(self):
        html = self.html()
        self.assertIn('ACME SRL', html)

    def test_imprime_el_cuit(self):
        """CUIT nomás: la etiqueta "CUIT / CUIL" obligaba al cliente a leer dos
        siglas para un solo número."""
        html = self.html()
        self.assertIn('CUIT: 30-71234567-8', html)
        self.assertNotIn('CUIL', html)

    def test_sin_cuit_no_deja_la_etiqueta_colgando(self):
        self.consulta.cuit = ''
        self.consulta.save()
        self.assertNotIn('CUIT:', self.html())

    def test_usa_la_razon_social_copiada_en_la_consulta(self):
        """Así el PDF sigue nombrando al cliente aunque después se lo borre."""
        self.consulta.cliente = None
        self.consulta.save()
        self.assertIn('ACME SRL', self.html())

    def test_sin_la_copia_lo_busca_en_la_ficha_del_cliente(self):
        """Una consulta vieja o cargada por otra vía puede no tenerla copiada."""
        self.consulta.razon_social = ''
        self.consulta.save()
        self.assertIn('ACME SRL', self.html())

    def test_sin_razon_social_en_ningun_lado_cae_al_contacto(self):
        self.consulta.razon_social = ''
        self.consulta.contacto = 'Juan Pérez'
        self.consulta.cliente = None
        self.consulta.save()
        self.assertIn('Juan Pérez', self.html())

    def test_la_copia_le_gana_a_la_ficha(self):
        """Si el cliente se renombró después, la cotización dice lo que decía
        cuando se emitió."""
        self.cliente.razon_social = 'ACME Sociedad Anonima'
        self.cliente.save()
        self.assertIn('ACME SRL', self.html())


class MembreteTest(BasePDFTest):
    """La marca la pone la imagen de la empresa, no un logo dibujado con CSS."""

    def test_lleva_el_membrete_embebido(self):
        self.assertIn('data:image/jpeg;base64,', self.html())

    def test_no_dibuja_un_logo_propio(self):
        """El diseño anterior armaba un círculo verde con una S y escribía la
        marca con la tipografía del documento. No es el logo de la empresa."""
        html = self.html()
        self.assertNotIn('logo-circle', html)
        self.assertNotIn('brand-name', html)

    def test_no_repite_en_texto_lo_que_ya_dice_la_imagen(self):
        """El membrete ya trae CUIT, dirección y los tres sitios."""
        self.linea(self.producto())
        # Una sola vez: en el encabezado compacto de la hoja del artículo.
        self.assertEqual(self.html().count('CUIT 30-71892853-9'), 1)

    def test_va_una_sola_vez_y_no_como_elemento_fijo(self):
        """`position: fixed` es lo que hace que WeasyPrint repita un elemento en
        cada hoja: el membrete no puede usarlo o saldría en todas."""
        self.assertNotRegex(self.html(), r'\.membrete\s*\{[^}]*position:\s*fixed')

    def test_el_pie_se_repite_en_cada_hoja(self):
        html = self.html()
        self.assertRegex(html, r'\.pdf-footer\s*\{[^}]*position:\s*fixed')
        # Dentro del margen inferior de la página: si se apoyara en el borde del
        # área de contenido, el texto de una hoja llena le pasaría por encima.
        self.assertRegex(html, r'\.pdf-footer\s*\{[^}]*bottom:\s*-[\d.]+cm')

    def test_el_body_no_reserva_espacio_con_padding(self):
        """Reservarlo así solo corre el contenido de la última hoja."""
        html = self.html()
        self.assertNotRegex(html, r'body\s*\{[^}]*padding-top:\s*\d')
        self.assertNotRegex(html, r'body\s*\{[^}]*padding-bottom:\s*\d')

    def test_el_pie_nombra_las_familias_de_producto(self):
        html = self.html()
        for familia in ('Pallets Plásticos', 'Tanques', 'Recipientes de Residuos'):
            with self.subTest(familia=familia):
                self.assertIn(familia, html)


class TablaDePreciosTest(BasePDFTest):
    def test_lleva_las_columnas_del_diseño(self):
        self.linea(self.producto())

        html = self.html()
        for columna in ('N°', 'Descripción', 'Cantidad', 'Precio unitario', 'Subtotal'):
            with self.subTest(columna=columna):
                self.assertIn(columna, html)

    def test_una_fila_por_linea_con_su_codigo(self):
        self.linea(self.producto())

        html = self.html()
        self.assertIn('Recipiente de Residuos de 120 litros', html)
        self.assertIn('Cód. R120', html)

    def test_usa_la_descripcion_de_la_linea_no_la_del_catalogo(self):
        """El vendedor puede ajustar el texto al armar la cotización."""
        self.linea(self.producto(), descripcion='Recipiente 120L color especial')
        self.assertIn('Recipiente 120L color especial', self.html())

    def test_el_precio_unitario_aclara_que_no_lleva_iva(self):
        self.linea(self.producto())
        self.assertIn('$ 87.500,00 + IVA', self.html())

    def test_el_subtotal_multiplica_por_la_cantidad(self):
        self.linea(self.producto(), cantidad='3')
        self.assertIn('$ 262.500,00', self.html())

    def test_los_totales_con_el_iva_discriminado(self):
        self.linea(self.producto())

        html = self.html()
        self.assertIn('Subtotal neto', html)
        self.assertIn('IVA (21%)', html)
        self.assertIn('Total c/ IVA', html)
        self.assertIn('$ 18.375,00', html)   # IVA de 87.500
        self.assertIn('$ 105.875,00', html)  # total

    def test_una_linea_sin_articulo_del_catalogo_igual_sale(self):
        """Se puede cotizar algo escrito a mano, sin ficha detrás."""
        self.linea(descripcion='Servicio de instalación', precio='50000')

        html = self.html()
        self.assertIn('Servicio de instalación', html)
        self.assertIn('$ 50.000,00 + IVA', html)

    def test_avisa_el_tipo_de_cambio_cuando_la_cotizacion_mezcla_monedas(self):
        self.consulta.tipo_cambio = Decimal('1000')
        self.consulta.save()
        self.linea(self.producto(), moneda=USD, precio='250')

        html = self.html()
        self.assertIn('tipo de cambio', html)
        self.assertIn('$ 1.000,00 por dólar', html)

    def test_sin_mezcla_de_monedas_no_habla_de_tipo_de_cambio(self):
        self.consulta.tipo_cambio = Decimal('1000')
        self.consulta.save()
        self.linea(self.producto())
        self.assertNotIn('por dólar', self.html())


class FichaDelArticuloTest(BasePDFTest):
    def test_cada_articulo_arranca_en_hoja_nueva(self):
        self.linea(self.producto(), descripcion='Primero')
        self.linea(self.producto(codigo='P2', nombre='Pallet'), descripcion='Segundo')

        html = self.html()
        self.assertEqual(html.count('page-break-before'), 3)  # dos artículos + condiciones
        self.assertIn('Primero', html)
        self.assertIn('Segundo', html)

    def test_lleva_el_codigo_del_articulo(self):
        self.linea(self.producto())
        self.assertIn('Código: R120', self.html())

    def test_la_descripcion_del_articulo_sale_cuando_la_linea_se_renombro(self):
        """Si el vendedor ajustó la de la línea, la del catálogo va igual: es la
        que identifica al artículo."""
        self.linea(self.producto(), descripcion='Recipiente 120L color especial')

        html = self.html()
        self.assertIn('Recipiente 120L color especial', html)
        self.assertIn('Recipiente de Residuos de 120 litros', html)

    def test_no_la_repite_cuando_es_la_misma(self):
        self.linea(self.producto())
        # Una vez en la tabla y otra en la ficha, no tres.
        self.assertEqual(
            self.html().count('Recipiente de Residuos de 120 litros'), 2)

    def test_imprime_cada_especificacion_en_su_linea(self):
        self.linea(self.producto())

        html = self.html()
        for spec in ('Cabezal desmontable tapa vaivén',
                     'Medidas externas 55 x 38 x 121 cm de alto',
                     'Uso industrial intenso'):
            with self.subTest(spec=spec):
                self.assertIn(f'<li>{spec}</li>', html)

    def test_los_colores_van_como_una_especificación_más(self):
        self.linea(self.producto())

        html = self.html()
        self.assertIn('Colores:', html)
        self.assertIn('A eleccion', html)

    def test_sin_colores_cargados_no_imprime_la_linea(self):
        self.linea(self.producto(colores=''))
        self.assertNotIn('Colores:', self.html())

    def test_las_especificaciones_van_en_dos_columnas(self):
        self.linea(self.producto())
        self.assertRegex(self.html(), r'\.product-specs\s*\{[^}]*columns:\s*2')

    def test_incluye_la_foto_del_articulo(self):
        self.linea(self.producto(foto=PNG_1PX, foto_tipo='image/png'))

        html = self.html()
        self.assertIn('class="product-photo"', html)
        self.assertIn('data:image/png;base64,', html)

    def test_sin_foto_no_deja_el_recuadro_vacio(self):
        self.linea(self.producto())

        html = self.html()
        self.assertNotIn('class="product-photo"', html)
        self.assertNotIn('Sin imagen', html)


class CondicionesTest(BasePDFTest):
    ETIQUETAS = [
        'Tasa de IVA:', 'Disponibilidad:', 'Mantenimiento de la oferta:',
        'Pagos:', 'Pagos fuera del término acordado:', 'Anticipos:',
        'Moneda extranjera:', 'Garantías:', 'Entregas:',
        'Retiros por depósito:', 'Embalaje:', 'Descargas:',
        'Compromiso de disponibilidad:',
        'Disponibilidad de material importado:',
    ]

    def test_estan_todas_las_etiquetas(self):
        html = self.html()
        self.assertIn('Condiciones de suministro', html)
        for etiqueta in self.ETIQUETAS:
            with self.subTest(etiqueta=etiqueta):
                self.assertIn(etiqueta, html)

    def test_van_en_su_propia_hoja_y_en_dos_columnas(self):
        self.linea(self.producto())

        html = self.html()
        self.assertIn('class="cond-title"', html)
        self.assertRegex(html, r'\.cond-body\s*\{[^}]*columns:\s*2')

    def test_conserva_las_direcciones_de_correo(self):
        html = self.html()
        self.assertIn('facturacion@supplyargentina.com.ar', html)
        self.assertIn('comercial@supplyargentina.com.ar', html)

    def test_firma_el_vendedor_que_cotizó(self):
        html = self.html()
        self.assertIn('Esperamos su favorable respuesta', html)
        self.assertIn('Vera Vendedora, Dpto. Ventas', html)

    def test_sin_nombre_cargado_firma_con_el_mail(self):
        self.user.first_name = ''
        self.user.last_name = ''
        self.user.save()
        self.assertIn('v@test.com, Dpto. Ventas', self.html())

    def test_no_van_justificadas(self):
        self.assertNotIn('text-align: justify', self.html())

    def test_el_cierre_va_al_pie_de_la_hoja_y_centrado(self):
        """Antes era la columna derecha de un bloque a dos columnas y quedaba
        tirado a un costado, colgando del final de las condiciones."""
        html = self.html()
        firma = re.search(r'\.firma-block\s*\{([^}]*)\}', html)
        self.assertIsNotNone(firma)
        estilo = firma.group(1)
        self.assertIn('position: absolute', estilo)
        self.assertIn('bottom: 0', estilo)
        self.assertIn('text-align: center', estilo)
        self.assertNotIn('columns: 2', estilo)

    def test_la_hoja_de_condiciones_mide_el_area_imprimible(self):
        """Es lo que le da referencia al cierre para anclarse al pie: sin una
        altura definida, `bottom: 0` no tiene contra qué medir."""
        html = self.html()
        hoja = re.search(r'\.hoja-condiciones\s*\{([^}]*)\}', html)
        self.assertIsNotNone(hoja)
        self.assertIn('position: relative', hoja.group(1))

        alto = re.search(r'height:\s*([\d.]+)cm', hoja.group(1))
        self.assertIsNotNone(alto)
        # margin: <arriba> <lat> <abajo> <lat>
        margenes = re.search(
            r'@page\s*\{[^}]*margin:\s*([\d.]+)cm\s+[\d.]+cm\s+([\d.]+)cm', html)
        self.assertIsNotNone(margenes)
        arriba, abajo = float(margenes.group(1)), float(margenes.group(2))
        self.assertAlmostEqual(float(alto.group(1)), 29.7 - arriba - abajo, places=2)


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
        self.assertIn('$ 250.000,00 + IVA', self.html())
