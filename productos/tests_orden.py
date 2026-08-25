"""El catálogo ordenado por código, agrupando las familias de artículos.

El gerente pidió ver juntos todos los artículos del mismo código y, dentro del
grupo, de menor a mayor medida. La medida vive dentro de la descripción, así
que ordenar por descripción es lo que los desparramaba: alfabéticamente "Caño
100mm" cae antes que "Caño 50mm" porque compara el '1' contra el '5'.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from productos.models import ARS, Categoria, Producto, clave_de_orden

User = get_user_model()
URL = reverse('productos:catalogo')


def crear(codigo, nombre='Artículo', categoria=None):
    return Producto.objects.create(
        codigo=codigo, nombre=nombre, categoria=categoria, moneda=ARS)


class ClaveDeOrdenTest(TestCase):
    """La función que arma la clave, sin pasar por la base."""

    def test_rellena_los_numeros_para_que_ordenen_como_numeros(self):
        self.assertLess(clave_de_orden('SA-2'), clave_de_orden('SA-10'))

    def test_mantiene_juntas_las_familias(self):
        codigos = ['SA-10', 'TB-2', 'SA-2', 'TB-10']
        self.assertEqual(
            sorted(codigos, key=clave_de_orden),
            ['SA-2', 'SA-10', 'TB-2', 'TB-10'])

    def test_no_le_molestan_los_codigos_sin_separador(self):
        self.assertEqual(
            sorted(['A10', 'B1', 'A2'], key=clave_de_orden),
            ['A2', 'A10', 'B1'])

    def test_varios_numeros_en_el_mismo_codigo(self):
        """Un código con dos tandas de dígitos ordena por las dos, en orden."""
        self.assertEqual(
            sorted(['P-2-10', 'P-10-1', 'P-2-3'], key=clave_de_orden),
            ['P-2-3', 'P-2-10', 'P-10-1'])

    def test_la_diferencia_de_mayusculas_no_separa_la_familia(self):
        self.assertEqual(clave_de_orden('sa-1'), clave_de_orden('SA-1'))

    def test_codigo_vacio_no_explota(self):
        self.assertEqual(clave_de_orden(''), '')


class ClaveGuardadaTest(TestCase):
    """La clave se escribe sola, por cualquiera de los caminos de alta."""

    def test_al_crear(self):
        self.assertEqual(crear('SA-2').codigo_orden, clave_de_orden('SA-2'))

    def test_al_cambiar_el_codigo(self):
        producto = crear('SA-2')
        producto.codigo = 'SA-30'
        producto.save()
        producto.refresh_from_db()
        self.assertEqual(producto.codigo_orden, clave_de_orden('SA-30'))

    def test_al_importar_con_bulk_create(self):
        """El importador no llama a save(), pero sí al pre_save del campo."""
        Producto.objects.bulk_create([
            Producto(codigo='IM-10', nombre='Diez', moneda=ARS),
            Producto(codigo='IM-2', nombre='Dos', moneda=ARS),
        ])
        self.assertEqual(
            [p.codigo for p in Producto.objects.order_by('codigo_orden')],
            ['IM-2', 'IM-10'])

    def test_al_actualizar_un_precio_no_se_pierde(self):
        """PreciosView guarda con bulk_update, que no dispara el pre_save."""
        producto = crear('SA-2')
        producto.precio = 100
        Producto.objects.bulk_update([producto], ['precio'])
        producto.refresh_from_db()
        self.assertEqual(producto.codigo_orden, clave_de_orden('SA-2'))


class CatalogoOrdenadoTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'vendedor@test.com', 'x', first_name='V', last_name='E',
            role=User.EMPLEADO)
        self.client.force_login(self.user)

    def listados(self):
        respuesta = self.client.get(URL)
        return [p.codigo for p in respuesta.context['pagina'].object_list]

    def test_sale_por_codigo_y_no_por_descripcion(self):
        """La descripción los ordenaría al revés: 'Caño 100' antes de 'Caño 50'."""
        crear('CA-100', 'Caño 100mm')
        crear('CA-50', 'Caño 50mm')
        self.assertEqual(self.listados(), ['CA-50', 'CA-100'])

    def test_las_familias_salen_juntas_aunque_la_descripcion_las_separe(self):
        """Antes, ordenando por descripción, el tanque se metía en el medio."""
        crear('CA-1', 'Caño chico')
        crear('CA-2', 'Zócalo de caño')
        crear('TA-1', 'Tanque')
        self.assertEqual(self.listados(), ['CA-1', 'CA-2', 'TA-1'])

    def test_la_categoria_no_cambia_el_orden_de_adentro(self):
        cajones = Categoria.objects.create(nombre='Cajones')
        crear('CJ-10', 'Cajón grande', cajones)
        crear('CJ-2', 'Cajón chico', cajones)
        respuesta = self.client.get(URL, {'categoria': 'Cajones'})
        self.assertEqual(
            [p.codigo for p in respuesta.context['pagina'].object_list],
            ['CJ-2', 'CJ-10'])

    def test_los_buscados_tambien_salen_ordenados(self):
        crear('CA-10', 'Caño diez')
        crear('CA-2', 'Caño dos')
        crear('TA-1', 'Tanque')
        respuesta = self.client.get(URL, {'q': 'Caño'})
        self.assertEqual(
            [p.codigo for p in respuesta.context['pagina'].object_list],
            ['CA-2', 'CA-10'])
