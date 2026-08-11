"""El flujo "Nueva consulta" desde la lista de consultas.

El botón abre un modal con dos caminos —cliente existente o cliente nuevo— y
los dos terminan en la pantalla de productos de un cliente concreto. Sigue
valiendo que no hay consulta sin cliente; lo que cambia es por dónde se entra.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from productos.models import Producto

User = get_user_model()


def usuario(email, role):
    return User.objects.create_user(
        email, 'x', first_name='Test', last_name='User', role=role)


class ModalTest(TestCase):
    def setUp(self):
        self.emp = usuario('e@test.com', User.EMPLEADO)
        self.client.force_login(self.emp)
        self.url = reverse('consultas:list')

    def test_el_boton_y_las_dos_opciones_estan_en_la_lista(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, '+ Nueva consulta')
        self.assertContains(respuesta, 'Cliente existente')
        self.assertContains(respuesta, 'Cliente nuevo')

    def test_el_buscador_apunta_al_endpoint_de_clientes(self):
        self.assertContains(self.client.get(self.url), reverse('clientes:search'))

    def test_el_formulario_pide_los_seis_campos(self):
        respuesta = self.client.get(self.url)
        for campo in ('razon_social', 'cuit', 'contacto', 'telefono', 'whatsapp', 'email'):
            with self.subTest(campo=campo):
                self.assertContains(respuesta, f'name="{campo}"')


class BuscadorTest(TestCase):
    """El buscador del modal usa el endpoint que ya existía."""

    def setUp(self):
        self.emp = usuario('e@test.com', User.EMPLEADO)
        self.otro = usuario('o@test.com', User.EMPLEADO)
        self.mio = Cliente.objects.create(
            razon_social='ACME SRL', cuit='30-71234567-8', vendedor=self.emp)
        self.ajeno = Cliente.objects.create(
            razon_social='ACME del otro', cuit='30-99999999-9', vendedor=self.otro)
        self.client.force_login(self.emp)

    def buscar(self, q):
        return self.client.get(reverse('clientes:search'), {'q': q}).json()

    def test_encuentra_por_razon_social(self):
        self.assertEqual([c['razon_social'] for c in self.buscar('ACME')], ['ACME SRL'])

    def test_encuentra_por_cuit(self):
        self.assertEqual(len(self.buscar('30-71234567-8')), 1)

    def test_encuentra_el_cuit_escrito_sin_guiones(self):
        self.assertEqual(len(self.buscar('30712345678')), 1)

    def test_no_ofrece_clientes_de_otra_cartera(self):
        self.assertNotIn('ACME del otro', [c['razon_social'] for c in self.buscar('ACME')])


class ClienteRapidoTest(TestCase):
    def setUp(self):
        self.gerente = usuario('g@test.com', User.GERENTE)
        self.emp = usuario('e@test.com', User.EMPLEADO)
        self.url = reverse('consultas:cliente_rapido')
        self.client.force_login(self.emp)

    def datos(self, **overrides):
        return {
            'razon_social': 'ACME SRL',
            'cuit': '30-71234567-8',
            'contacto': 'Juan Pérez',
            'telefono': '11 4444-5555',
            'whatsapp': '11 6666-7777',
            'email': 'juan@acme.com',
            **overrides,
        }

    def test_crea_el_cliente_con_los_seis_campos(self):
        self.client.post(self.url, self.datos())

        cliente = Cliente.objects.get(razon_social='ACME SRL')
        self.assertEqual(cliente.cuit, '30-71234567-8')
        self.assertEqual(cliente.contacto, 'Juan Pérez')
        self.assertEqual(cliente.telefono, '11 4444-5555')
        self.assertEqual(cliente.whatsapp, '11 6666-7777')
        self.assertEqual(cliente.email, 'juan@acme.com')

    def test_termina_en_la_pantalla_de_productos(self):
        respuesta = self.client.post(self.url, self.datos())
        cliente = Cliente.objects.get(razon_social='ACME SRL')
        self.assertRedirects(
            respuesta, reverse('consultas:nueva_cotizacion', args=[cliente.pk]))

    def test_el_empleado_se_queda_el_cliente(self):
        self.client.post(self.url, self.datos())
        self.assertEqual(Cliente.objects.get(razon_social='ACME SRL').vendedor, self.emp)

    def test_normaliza_el_cuit(self):
        self.client.post(self.url, self.datos(cuit='30712345678'))
        self.assertEqual(Cliente.objects.get(razon_social='ACME SRL').cuit, '30-71234567-8')

    def test_alcanza_con_la_razon_social(self):
        self.client.post(self.url, {'razon_social': 'Solo el nombre'})
        self.assertTrue(Cliente.objects.filter(razon_social='Solo el nombre').exists())

    def test_sin_razon_social_no_crea_nada(self):
        respuesta = self.client.post(self.url, self.datos(razon_social=''))
        self.assertFalse(Cliente.objects.exists())
        self.assertRedirects(respuesta, reverse('consultas:list'))

    def test_el_get_no_crea_nada(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_el_anonimo_no_puede(self):
        self.client.logout()
        self.client.post(self.url, self.datos())
        self.assertFalse(Cliente.objects.exists())


class ClienteRapidoDuplicadoTest(TestCase):
    """Cargar dos veces al mismo cliente es el error más fácil de cometer acá."""

    def setUp(self):
        self.emp = usuario('e@test.com', User.EMPLEADO)
        self.otro = usuario('o@test.com', User.EMPLEADO)
        self.url = reverse('consultas:cliente_rapido')
        self.existente = Cliente.objects.create(
            razon_social='ACME SRL', cuit='30-71234567-8', vendedor=self.emp)
        self.client.force_login(self.emp)

    def datos(self, **overrides):
        return {'razon_social': 'ACME Sociedad Anonima',
                'cuit': '30-71234567-8', **overrides}

    def test_no_duplica_y_sigue_con_el_que_ya_estaba(self):
        respuesta = self.client.post(self.url, self.datos())

        self.assertEqual(Cliente.objects.count(), 1)
        self.assertRedirects(
            respuesta, reverse('consultas:nueva_cotizacion', args=[self.existente.pk]))

    def test_avisa_que_ya_estaba(self):
        respuesta = self.client.post(self.url, self.datos(), follow=True)
        self.assertContains(respuesta, 'ya estaba cargado')

    def test_lo_detecta_escrito_sin_guiones(self):
        self.client.post(self.url, self.datos(cuit='30712345678'))
        self.assertEqual(Cliente.objects.count(), 1)

    def test_si_es_de_otra_cartera_manda_al_gerente(self):
        self.existente.vendedor = self.otro
        self.existente.save()

        respuesta = self.client.post(self.url, self.datos(), follow=True)
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertContains(respuesta, 'cartera de otro vendedor')

    def test_sin_cuit_no_compara_contra_nada(self):
        """Si el CUIT vacío matcheara, nadie podría cargar un cliente sin CUIT."""
        Cliente.objects.create(razon_social='Sin CUIT', cuit='', vendedor=self.emp)
        self.client.post(self.url, {'razon_social': 'Otro sin CUIT'})
        self.assertTrue(Cliente.objects.filter(razon_social='Otro sin CUIT').exists())


class FiltroPorCategoriaTest(TestCase):
    """La pantalla de productos con 740 artículos necesita recortar."""

    def setUp(self):
        self.emp = usuario('e@test.com', User.EMPLEADO)
        self.cliente = Cliente.objects.create(razon_social='ACME SRL', vendedor=self.emp)
        Producto.objects.create(codigo='P1', nombre='Pallet', categoria='pallets plasticos')
        Producto.objects.create(codigo='C1', nombre='Cajón', categoria='Cajones')
        Producto.objects.create(codigo='X1', nombre='Suelto', categoria='')
        self.url = reverse('consultas:nueva_cotizacion', args=[self.cliente.pk])
        self.client.force_login(self.emp)

    def test_ofrece_el_filtro_con_las_categorias_en_uso(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'Filtrar por categoría')
        self.assertContains(respuesta, 'pallets plasticos')
        self.assertContains(respuesta, 'Cajones')

    def test_las_categorias_van_ordenadas_sin_importar_la_mayuscula(self):
        categorias = self.client.get(self.url).context['categorias']
        self.assertEqual(categorias, ['Cajones', 'pallets plasticos'])

    def test_no_ofrece_una_categoria_vacia(self):
        self.assertNotIn('', self.client.get(self.url).context['categorias'])

    def test_los_productos_viajan_con_su_categoria(self):
        data = self.client.get(self.url).context['productos_data']
        pallet = next(p for p in data if p['codigo'] == 'P1')
        self.assertEqual(pallet['categoria'], 'pallets plasticos')
        self.assertEqual(pallet['nombre'], 'Pallet')

    def test_los_productos_inactivos_no_llegan(self):
        Producto.objects.create(codigo='OFF', nombre='Dado de baja',
                                categoria='Cajones', activo=False)
        data = self.client.get(self.url).context['productos_data']
        self.assertNotIn('OFF', [p['codigo'] for p in data])
