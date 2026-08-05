"""El flujo arranca del cliente.

Ya no se crea una consulta desde /consultas/, no se importan PDFs, y el
seguimiento cuelga del cliente en una sola línea de tiempo.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from clientes.models import Cliente
from consultas.models import Consulta, LineaCotizacion, SeguimientoLog

User = get_user_model()


class SinAltaSuletaTest(TestCase):
    """Las vías que se saltaban el cliente dejaron de existir."""

    def setUp(self):
        self.emp = User.objects.create_user('a@test.com', 'x', first_name='Ana',
                                            last_name='Alfa', role=User.EMPLEADO)
        self.client.force_login(self.emp)

    def test_no_hay_ruta_para_crear_una_consulta_sin_cliente(self):
        with self.assertRaises(NoReverseMatch):
            reverse('consultas:create')

    def test_no_hay_ruta_para_cotizar_sin_cliente(self):
        with self.assertRaises(NoReverseMatch):
            reverse('consultas:nueva_cotizacion')

    def test_el_import_de_pdf_ya_no_existe(self):
        with self.assertRaises(NoReverseMatch):
            reverse('consultas:import_pdf')
        self.assertEqual(self.client.get('/consultas/importar-pdf/').status_code, 404)

    def test_la_vieja_url_de_alta_ya_no_responde(self):
        self.assertEqual(self.client.get('/consultas/nueva/').status_code, 404)

    def test_la_lista_de_consultas_no_ofrece_crear(self):
        cuerpo = self.client.get(reverse('consultas:list')).content.decode()
        self.assertNotIn('Importar PDF', cuerpo)
        self.assertNotIn('+ Nueva consulta', cuerpo)


class AltaDesdeLaFichaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gerente = User.objects.create_user('g@test.com', 'x', first_name='G',
                                               last_name='G', role=User.GERENTE)
        cls.emp_a = User.objects.create_user('a@test.com', 'x', first_name='Ana',
                                             last_name='Alfa', role=User.EMPLEADO)
        cls.emp_b = User.objects.create_user('b@test.com', 'x', first_name='Beto',
                                             last_name='Beta', role=User.EMPLEADO)

    def setUp(self):
        self.mio = Cliente.objects.create(
            razon_social='Los Grobo', cuit='30-60445647-5', contacto='Juan',
            telefono='1122334455', email='juan@grobo.com',
            localidad='Carlos Casares', provincia='Buenos Aires', vendedor=self.emp_a)
        self.ajeno = Cliente.objects.create(
            razon_social='De Beto', cuit='30-11111111-1', vendedor=self.emp_b)

    def alta(self, cliente_pk, **extra):
        datos = {'fecha': '2026-08-01', 'productos': 'Pallets',
                 'via_entrada': 'mail', 'estado': 'cotizado', **extra}
        return self.client.post(reverse('consultas:create', args=[cliente_pk]), datos)

    def test_copia_los_datos_del_cliente_sin_tipearlos(self):
        self.client.force_login(self.emp_a)
        self.alta(self.mio.pk)

        c = Consulta.objects.get()
        self.assertEqual(c.cliente, self.mio)
        self.assertEqual(c.razon_social, 'Los Grobo')
        self.assertEqual(c.cuit, '30-60445647-5')
        self.assertEqual(c.contacto, 'Juan')
        self.assertEqual(c.telefono, '1122334455')
        self.assertEqual(c.email, 'juan@grobo.com')
        self.assertEqual(c.vendedor, self.emp_a)

    def test_no_puede_cargar_sobre_un_cliente_de_otro(self):
        self.client.force_login(self.emp_a)
        self.assertEqual(
            self.client.get(reverse('consultas:create', args=[self.ajeno.pk])).status_code, 404)
        self.assertEqual(self.alta(self.ajeno.pk).status_code, 404)
        self.assertEqual(Consulta.objects.count(), 0)

    def test_el_gerente_puede_cargar_sobre_cualquiera(self):
        self.client.force_login(self.gerente)
        self.alta(self.ajeno.pk)
        self.assertEqual(Consulta.objects.get().cliente, self.ajeno)

    def test_el_formulario_no_pide_datos_del_cliente(self):
        self.client.force_login(self.emp_a)
        form = self.client.get(reverse('consultas:create', args=[self.mio.pk])).context['form']
        for campo in ('razon_social', 'cuit', 'contacto', 'telefono', 'email'):
            self.assertNotIn(campo, form.fields)

    def test_editar_una_consulta_tampoco_pide_datos_del_cliente(self):
        self.client.force_login(self.emp_a)
        self.alta(self.mio.pk)
        consulta = Consulta.objects.get()
        form = self.client.get(reverse('consultas:edit', args=[consulta.pk])).context['form']
        self.assertNotIn('razon_social', form.fields)
        self.assertIn('productos', form.fields)

    def test_la_ficha_linkea_al_alta_y_a_la_cotizacion(self):
        self.client.force_login(self.emp_a)
        cuerpo = self.client.get(reverse('clientes:detail', args=[self.mio.pk])).content.decode()
        self.assertIn(reverse('consultas:create', args=[self.mio.pk]), cuerpo)
        self.assertIn(reverse('consultas:nueva_cotizacion', args=[self.mio.pk]), cuerpo)


class CotizacionDesdeLaFichaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.emp = User.objects.create_user('a@test.com', 'x', first_name='Ana',
                                           last_name='Alfa', role=User.EMPLEADO)
        cls.otro = User.objects.create_user('b@test.com', 'x', role=User.EMPLEADO)

    def setUp(self):
        self.mio = Cliente.objects.create(razon_social='Los Grobo', cuit='30-60445647-5',
                                          vendedor=self.emp)
        self.client.force_login(self.emp)

    def test_cotiza_a_un_cliente_de_la_cartera(self):
        resp = self.client.post(reverse('consultas:nueva_cotizacion', args=[self.mio.pk]), {
            'fecha': '2026-08-01', 'via_entrada': 'mail', 'numero_cotizacion': '9001',
            'linea_desc_0': 'Pallet P61', 'linea_cant_0': '5', 'linea_precio_0': '1000',
        })
        consulta = Consulta.objects.get()
        self.assertRedirects(resp, reverse('consultas:cotizacion', args=[consulta.pk]))
        self.assertEqual(consulta.cliente, self.mio)
        self.assertEqual(consulta.razon_social, 'Los Grobo')
        self.assertEqual(consulta.cuit, '30-60445647-5')
        self.assertEqual(consulta.productos, 'Pallet P61')
        self.assertEqual(consulta.numero_cotizacion, '9001')
        self.assertEqual(LineaCotizacion.objects.count(), 1)

    def test_sin_lineas_no_crea_nada(self):
        resp = self.client.post(reverse('consultas:nueva_cotizacion', args=[self.mio.pk]),
                                {'fecha': '2026-08-01', 'via_entrada': 'mail'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Consulta.objects.count(), 0)

    def test_no_puede_cotizarle_a_un_cliente_de_otro(self):
        ajeno = Cliente.objects.create(razon_social='Ajeno', vendedor=self.otro)
        self.assertEqual(
            self.client.get(
                reverse('consultas:nueva_cotizacion', args=[ajeno.pk])).status_code, 404)


class SeguimientoDelClienteTest(TestCase):
    """El seguimiento cuelga del cliente: una sola línea de tiempo."""

    @classmethod
    def setUpTestData(cls):
        cls.emp = User.objects.create_user('a@test.com', 'x', first_name='Ana',
                                           last_name='Alfa', role=User.EMPLEADO)
        cls.otro = User.objects.create_user('b@test.com', 'x', role=User.EMPLEADO)

    def setUp(self):
        self.cliente = Cliente.objects.create(razon_social='Los Grobo', vendedor=self.emp)
        self.client.force_login(self.emp)

    def test_registra_un_seguimiento_desde_la_ficha(self):
        resp = self.client.post(reverse('clientes:detail', args=[self.cliente.pk]),
                                {'nota': 'Llamé, quedó en confirmar'})
        self.assertRedirects(resp, reverse('clientes:detail', args=[self.cliente.pk]))
        log = SeguimientoLog.objects.get()
        self.assertEqual(log.cliente, self.cliente)
        self.assertIsNone(log.consulta)      # no hace falta una consulta abierta
        self.assertEqual(log.user, self.emp)

    def test_la_ficha_muestra_la_linea_de_tiempo_mas_nuevo_primero(self):
        SeguimientoLog.objects.create(cliente=self.cliente, user=self.emp, nota='Primera')
        SeguimientoLog.objects.create(cliente=self.cliente, user=self.emp, nota='Segunda')
        resp = self.client.get(reverse('clientes:detail', args=[self.cliente.pk]))
        self.assertEqual([s.nota for s in resp.context['seguimientos']], ['Segunda', 'Primera'])

    def test_una_nota_vacia_no_se_guarda(self):
        resp = self.client.post(reverse('clientes:detail', args=[self.cliente.pk]), {'nota': ''})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(SeguimientoLog.objects.count(), 0)

    def test_el_seguimiento_de_una_consulta_tambien_entra_en_la_linea_del_cliente(self):
        consulta = Consulta.objects.create(productos='Pallets', cliente=self.cliente,
                                           vendedor=self.emp)
        self.client.post(reverse('consultas:detail', args=[consulta.pk]),
                         {'nota': 'Sobre esta cotización'})
        log = SeguimientoLog.objects.get()
        self.assertEqual(log.consulta, consulta)
        self.assertEqual(log.cliente, self.cliente)
        resp = self.client.get(reverse('clientes:detail', args=[self.cliente.pk]))
        self.assertEqual(len(resp.context['seguimientos']), 1)

    def test_no_puede_seguir_un_cliente_ajeno(self):
        ajeno = Cliente.objects.create(razon_social='Ajeno', vendedor=self.otro)
        resp = self.client.post(reverse('clientes:detail', args=[ajeno.pk]), {'nota': 'hola'})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(SeguimientoLog.objects.count(), 0)

    def test_borrar_la_consulta_no_borra_el_seguimiento(self):
        """SET_NULL: la nota sigue en la historia del cliente."""
        consulta = Consulta.objects.create(productos='Pallets', cliente=self.cliente,
                                           vendedor=self.emp)
        SeguimientoLog.objects.create(cliente=self.cliente, consulta=consulta,
                                      user=self.emp, nota='Queda')
        consulta.delete()
        log = SeguimientoLog.objects.get()
        self.assertIsNone(log.consulta)
        self.assertEqual(log.cliente, self.cliente)

    def test_borrar_el_cliente_si_borra_sus_seguimientos(self):
        SeguimientoLog.objects.create(cliente=self.cliente, user=self.emp, nota='Chau')
        self.cliente.delete()
        self.assertEqual(SeguimientoLog.objects.count(), 0)
