"""Alta de un cliente nuevo desde la web.

Hasta acá los clientes solo entraban por el importador del sistema de
facturación. El que atiende una consulta de alguien que llama por primera vez
necesita poder cargarlo en el momento.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente

User = get_user_model()


def usuario(email, role):
    return User.objects.create_user(
        email, 'x', first_name='Test', last_name='User', role=role)


class BaseAltaTest(TestCase):
    def setUp(self):
        self.gerente = usuario('g@test.com', User.GERENTE)
        self.emp = usuario('e@test.com', User.EMPLEADO)
        self.otro = usuario('o@test.com', User.EMPLEADO)
        self.url = reverse('clientes:create')

    def datos(self, **overrides):
        return {'razon_social': 'ACME SRL', 'cuit': '30-71234567-8', **overrides}


class AccesoTest(BaseAltaTest):
    def test_el_listado_ofrece_cargar_uno_nuevo(self):
        self.client.force_login(self.emp)
        self.assertContains(self.client.get(reverse('clientes:list')), '+ Nuevo cliente')

    def test_cualquier_rol_puede_cargar(self):
        """El que atiende la consulta es el que tiene los datos del cliente."""
        for user in (self.gerente, self.emp):
            with self.subTest(rol=user.role):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_el_anonimo_va_al_login(self):
        respuesta = self.client.get(self.url)
        self.assertIn(reverse('accounts:login'), respuesta['Location'])


class AltaTest(BaseAltaTest):
    def test_crea_y_lleva_a_la_ficha(self):
        self.client.force_login(self.emp)
        respuesta = self.client.post(self.url, self.datos())

        cliente = Cliente.objects.get(razon_social='ACME SRL')
        self.assertRedirects(respuesta, reverse('clientes:detail', args=[cliente.pk]))

    def test_el_empleado_se_queda_el_cliente_que_trae(self):
        """Si quedara sin asignar, desaparecería de su vista al instante."""
        self.client.force_login(self.emp)
        self.client.post(self.url, self.datos())

        cliente = Cliente.objects.get(razon_social='ACME SRL')
        self.assertEqual(cliente.vendedor, self.emp)
        self.assertIn(cliente, Cliente.objects.visibles_para(self.emp))

    def test_al_empleado_no_se_le_pregunta_por_el_vendedor(self):
        self.client.force_login(self.emp)
        self.assertNotContains(self.client.get(self.url), 'name="vendedor"')

    def test_el_empleado_no_puede_asignarselo_a_otro(self):
        self.client.force_login(self.emp)
        self.client.post(self.url, self.datos(vendedor=self.otro.pk))
        self.assertEqual(Cliente.objects.get(razon_social='ACME SRL').vendedor, self.emp)

    def test_al_gerente_se_le_propone_a_si_mismo(self):
        self.client.force_login(self.gerente)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'name="vendedor"')
        self.assertEqual(respuesta.context['form'].initial['vendedor'], self.gerente)

    def test_el_gerente_puede_asignarlo_a_un_empleado(self):
        self.client.force_login(self.gerente)
        self.client.post(self.url, self.datos(vendedor=self.emp.pk))
        self.assertEqual(Cliente.objects.get(razon_social='ACME SRL').vendedor, self.emp)

    def test_el_gerente_puede_dejarlo_sin_asignar(self):
        self.client.force_login(self.gerente)
        self.client.post(self.url, self.datos(vendedor=''))
        self.assertIsNone(Cliente.objects.get(razon_social='ACME SRL').vendedor)

    def test_guarda_el_cuit_en_la_forma_canonica(self):
        self.client.force_login(self.emp)
        self.client.post(self.url, self.datos(cuit='30712345678'))
        self.assertEqual(Cliente.objects.get(razon_social='ACME SRL').cuit, '30-71234567-8')

    def test_sin_razon_social_no_crea_nada(self):
        self.client.force_login(self.emp)
        respuesta = self.client.post(self.url, self.datos(razon_social=''))
        self.assertFalse(Cliente.objects.exists())
        self.assertEqual(respuesta.status_code, 200)

    def test_el_cuit_puede_quedar_vacio(self):
        """Muchos consultan antes de dar los datos fiscales."""
        self.client.force_login(self.emp)
        self.client.post(self.url, self.datos(cuit=''))
        self.assertTrue(Cliente.objects.filter(razon_social='ACME SRL').exists())


class DuplicadosTest(BaseAltaTest):
    """El CUIT no es único en la base, así que el aviso es la única defensa."""

    def setUp(self):
        super().setUp()
        self.existente = Cliente.objects.create(
            razon_social='ACME Sociedad Anonima', cuit='30-71234567-8',
            vendedor=self.emp)

    def test_avisa_en_lugar_de_crear_el_duplicado(self):
        self.client.force_login(self.emp)
        respuesta = self.client.post(self.url, self.datos())

        self.assertEqual(Cliente.objects.count(), 1)
        self.assertContains(respuesta, 'Ya hay un cliente con ese CUIT')
        self.assertContains(respuesta, 'ACME Sociedad Anonima')

    def test_lo_detecta_aunque_lo_escriban_sin_guiones(self):
        self.client.force_login(self.emp)
        respuesta = self.client.post(self.url, self.datos(cuit='30712345678'))
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertContains(respuesta, 'Ya hay un cliente con ese CUIT')

    def test_no_pierde_lo_que_ya_habia_tipeado(self):
        self.client.force_login(self.emp)
        respuesta = self.client.post(self.url, self.datos(
            razon_social='ACME SRL', telefono='11 2345-6789'))
        self.assertContains(respuesta, 'ACME SRL')
        self.assertContains(respuesta, '11 2345-6789')

    def test_si_lo_tiene_en_su_cartera_le_linkea_la_ficha(self):
        self.client.force_login(self.emp)
        respuesta = self.client.post(self.url, self.datos())
        self.assertContains(respuesta, reverse('clientes:detail', args=[self.existente.pk]))

    def test_si_es_de_otro_no_le_da_el_link(self):
        """No lo puede abrir: eso lo destraba el gerente asignándoselo."""
        self.existente.vendedor = self.otro
        self.existente.save()
        self.client.force_login(self.emp)

        respuesta = self.client.post(self.url, self.datos())
        self.assertContains(respuesta, 'está en la cartera de')
        self.assertNotContains(respuesta, reverse('clientes:detail', args=[self.existente.pk]))

    def test_el_empleado_no_puede_forzar_el_alta(self):
        self.client.force_login(self.emp)
        self.client.post(self.url, self.datos(confirmar='1'))
        self.assertEqual(Cliente.objects.count(), 1)

    def test_al_empleado_no_se_le_ofrece_forzar(self):
        self.client.force_login(self.emp)
        respuesta = self.client.post(self.url, self.datos())
        self.assertNotContains(respuesta, 'Guardar igual')

    def test_el_gerente_puede_forzar_el_alta(self):
        """Dos empresas distintas pueden compartir CUIT; alguien tiene que poder."""
        self.client.force_login(self.gerente)
        respuesta = self.client.post(self.url, self.datos())
        self.assertContains(respuesta, 'Guardar igual')

        self.client.post(self.url, self.datos(confirmar='1'))
        self.assertEqual(Cliente.objects.filter(cuit='30-71234567-8').count(), 2)

    def test_sin_cuit_no_hay_nada_que_comparar(self):
        """Si el CUIT vacío contara como repetido, no se podría cargar a nadie."""
        Cliente.objects.create(razon_social='Otro sin CUIT', cuit='')
        self.client.force_login(self.emp)
        self.client.post(self.url, self.datos(cuit=''))
        self.assertTrue(Cliente.objects.filter(razon_social='ACME SRL').exists())


class EdicionSigueAndandoTest(BaseAltaTest):
    """El template de formulario ahora es compartido con el alta."""

    def setUp(self):
        super().setUp()
        self.cliente = Cliente.objects.create(
            razon_social='ACME SRL', cuit='30-71234567-8', vendedor=self.emp)

    def test_la_pantalla_de_edicion_sigue_diciendo_editar(self):
        self.client.force_login(self.emp)
        respuesta = self.client.get(reverse('clientes:edit', args=[self.cliente.pk]))
        self.assertContains(respuesta, 'Editar cliente')

    def test_edita_sin_que_su_propio_cuit_le_frene(self):
        """Guardar un cliente que ya existe no puede chocar consigo mismo."""
        self.client.force_login(self.emp)
        self.client.post(reverse('clientes:edit', args=[self.cliente.pk]),
                         {'razon_social': 'ACME SRL Renombrada', 'cuit': '30-71234567-8'})
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.razon_social, 'ACME SRL Renombrada')
