"""El rol Jefe de ventas: dirige el equipo sin administrar el sistema.

Queda entre Gerente y Empleado. Ve toda la operación, reparte la cartera, vende
con la suya propia y mantiene el catálogo y los precios. Lo que no toca son las
dos llaves del sistema: los usuarios y la baja de clientes.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from consultas.models import Consulta
from productos.models import ARS, Producto

User = get_user_model()


def usuario(role, email=None):
    return User.objects.create_user(
        email or f'{role}@test.com', 'x',
        first_name='Test', last_name=role.title(), role=role)


class RolTest(TestCase):
    def test_es_un_rol_elegible(self):
        self.assertIn((User.JEFE_VENTAS, 'Jefe de ventas'), User.ROLE_CHOICES)

    def test_figura_entre_gerente_y_empleado(self):
        """El desplegable se lee en orden de alcance."""
        valores = [valor for valor, _ in User.ROLE_CHOICES]
        self.assertLess(valores.index(User.GERENTE), valores.index(User.JEFE_VENTAS))
        self.assertLess(valores.index(User.JEFE_VENTAS), valores.index(User.EMPLEADO))

    def test_lo_que_puede(self):
        jefe = usuario(User.JEFE_VENTAS)
        for capacidad in ('puede_ver_todas_las_consultas', 'puede_ver_todos_los_clientes',
                          'puede_ver_reportes', 'puede_ver_ventas', 'puede_cargar_ventas',
                          'puede_asignar_clientes', 'puede_editar_catalogo',
                          'puede_editar_precios', 'lleva_cartera'):
            with self.subTest(capacidad=capacidad):
                self.assertTrue(getattr(jefe, capacidad))

    def test_lo_que_no_puede(self):
        """Las dos llaves quedan en el Gerente."""
        jefe = usuario(User.JEFE_VENTAS)
        self.assertFalse(jefe.puede_gestionar_usuarios)
        self.assertFalse(jefe.puede_borrar_clientes)
        self.assertFalse(jefe.puede_administrar_admins)

    def test_no_entra_al_admin_de_django(self):
        self.assertFalse(usuario(User.JEFE_VENTAS).is_staff)

    def test_arranca_en_el_dashboard(self):
        self.assertEqual(usuario(User.JEFE_VENTAS).pagina_inicial, 'dashboard')

    def test_dirigir_y_administrar_dejaron_de_ser_la_misma_lista(self):
        self.assertIn(User.JEFE_VENTAS, User.ROLES_QUE_REPARTEN_CARTERA)
        self.assertNotIn(User.JEFE_VENTAS, User.ROLES_DE_ADMINISTRACION)

    def test_no_le_movio_nada_a_los_otros_roles(self):
        empleado, gerente, coach = (usuario(User.EMPLEADO), usuario(User.GERENTE),
                                    usuario(User.COACH))
        self.assertFalse(empleado.puede_asignar_clientes)
        self.assertFalse(empleado.puede_editar_catalogo)
        self.assertTrue(gerente.puede_gestionar_usuarios)
        self.assertTrue(gerente.puede_borrar_clientes)
        self.assertFalse(coach.puede_cargar_ventas)
        self.assertFalse(coach.puede_asignar_clientes)


class BaseJefeTest(TestCase):
    def setUp(self):
        self.jefe = usuario(User.JEFE_VENTAS)
        self.emp = usuario(User.EMPLEADO)
        self.cliente = Cliente.objects.create(
            razon_social='ACME SRL', cuit='30-71234567-8', vendedor=self.emp)
        self.consulta = Consulta.objects.create(
            productos='Pallets', razon_social='ACME SRL',
            cliente=self.cliente, vendedor=self.emp, moneda=ARS)
        self.client.force_login(self.jefe)


class DirigeElEquipoTest(BaseJefeTest):
    def test_ve_las_consultas_de_todos(self):
        self.assertContains(self.client.get(reverse('consultas:list')), 'ACME SRL')

    def test_ve_los_clientes_de_todas_las_carteras(self):
        self.assertContains(self.client.get(reverse('clientes:list')), 'ACME SRL')

    def test_entra_al_panel_del_equipo(self):
        self.assertEqual(self.client.get(reverse('reportes:equipo')).status_code, 200)

    def test_reparte_la_cartera(self):
        self.client.post(reverse('clientes:asignar'),
                         {'cliente': [self.cliente.pk], 'vendedor': self.jefe.pk})
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.vendedor, self.jefe)

    def test_le_aparece_la_barra_de_asignacion(self):
        self.assertTrue(self.client.get(reverse('clientes:list')).context['puede_asignar'])

    def test_puede_recibir_cartera_propia(self):
        """Vende además de dirigir, así que es un destino válido."""
        vendedores = self.client.get(reverse('clientes:list')).context['vendedores']
        self.assertIn(self.jefe, vendedores)

    def test_carga_clientes_y_consultas(self):
        self.client.post(reverse('clientes:create'), {'razon_social': 'Nuevo cliente'})
        self.assertTrue(Cliente.objects.filter(razon_social='Nuevo cliente').exists())

    def test_edita_la_consulta_de_otro_vendedor(self):
        """Cubrir al equipo es parte del trabajo."""
        self.client.post(reverse('consultas:edit', args=[self.consulta.pk]), {
            'fecha': '2026-08-01', 'productos': 'Pallets y cajones',
            'via_entrada': 'mail', 'estado': 'facturado',
        })
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.estado, Consulta.FACTURADO)

    def test_registra_seguimientos(self):
        self.client.post(reverse('consultas:detail', args=[self.consulta.pk]),
                         {'nota': 'Hablé con el cliente'})
        self.assertEqual(self.consulta.logs.count(), 1)


class MantieneElCatalogoTest(BaseJefeTest):
    def setUp(self):
        super().setUp()
        self.producto = Producto.objects.create(
            codigo='P1', nombre='Pallet', moneda=ARS, categoria='Pallets')

    def test_edita_un_articulo(self):
        self.client.post(reverse('productos:detail', args=[self.producto.pk]),
                         {'nombre': 'Pallet reforzado', 'unidad_medida': '',
                          'precio': '150', 'moneda': ARS, 'categoria': 'Pallets',
                          'colores': '', 'especificaciones': ''})
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.nombre, 'Pallet reforzado')

    def test_da_de_alta_articulos(self):
        self.assertEqual(self.client.get(reverse('productos:create')).status_code, 200)

    def test_entra_a_la_pantalla_de_precios(self):
        self.assertEqual(self.client.get(reverse('productos:precios')).status_code, 200)

    def test_el_menu_le_ofrece_precios(self):
        self.assertContains(self.client.get(reverse('consultas:list')),
                            reverse('productos:precios'))


class NoAdministraTest(BaseJefeTest):
    """Las dos llaves, por POST directo."""

    def test_no_entra_a_usuarios(self):
        self.assertRedirects(self.client.get(reverse('accounts:user_list')),
                             reverse('dashboard'))

    def test_no_crea_usuarios(self):
        self.client.post(reverse('accounts:user_create'), {
            'email': 'colado@test.com', 'first_name': 'Co', 'last_name': 'Lado',
            'role': User.GERENTE, 'password1': 'Segura123!', 'password2': 'Segura123!',
        })
        self.assertFalse(User.objects.filter(email='colado@test.com').exists())

    def test_no_le_cambia_la_contrasena_a_nadie(self):
        respuesta = self.client.get(
            reverse('accounts:user_password', args=[self.emp.pk]))
        self.assertRedirects(respuesta, reverse('dashboard'))

    def test_no_borra_clientes(self):
        self.client.post(reverse('clientes:borrar', args=[self.cliente.pk]))
        self.assertTrue(Cliente.objects.filter(pk=self.cliente.pk).exists())

    def test_la_ficha_no_le_ofrece_borrar(self):
        self.assertNotContains(
            self.client.get(reverse('clientes:detail', args=[self.cliente.pk])),
            reverse('clientes:borrar', args=[self.cliente.pk]))

    def test_el_menu_no_le_ofrece_usuarios(self):
        self.assertNotContains(self.client.get(reverse('consultas:list')),
                               reverse('accounts:user_list'))


class ElGerenteLoDaDeAltaTest(TestCase):
    def setUp(self):
        self.gerente = usuario(User.GERENTE)
        self.client.force_login(self.gerente)

    def test_puede_crear_un_jefe_de_ventas(self):
        self.client.post(reverse('accounts:user_create'), {
            'email': 'jefe@test.com', 'first_name': 'Jefa', 'last_name': 'Ventas',
            'role': User.JEFE_VENTAS, 'password1': 'Segura123!', 'password2': 'Segura123!',
        })
        creado = User.objects.get(email='jefe@test.com')
        self.assertEqual(creado.role, User.JEFE_VENTAS)
        self.assertFalse(creado.is_staff)

    def test_el_rol_figura_en_el_formulario(self):
        form = self.client.get(reverse('accounts:user_create')).context['form']
        self.assertIn(User.JEFE_VENTAS, [v for v, _ in form.fields['role'].choices])
