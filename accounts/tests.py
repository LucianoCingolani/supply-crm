"""Matriz de permisos de los tres roles: Admin, Gerente y Empleado."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from consultas.models import Consulta
from productos.models import Producto

User = get_user_model()


class BaseRolesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            'admin@test.com', 'x', first_name='Ana', last_name='Admin', role=User.ADMIN)
        cls.gerente = User.objects.create_user(
            'gerente@test.com', 'x', first_name='Gaby', last_name='Gerente', role=User.GERENTE)
        cls.emp_a = User.objects.create_user(
            'a@test.com', 'x', first_name='Emi', last_name='Uno', role=User.EMPLEADO)
        cls.emp_b = User.objects.create_user(
            'b@test.com', 'x', first_name='Beto', last_name='Dos', role=User.EMPLEADO)

        # La cartera la reparte el Gerente: es lo que define qué ve cada uno.
        cls.cli_a = Cliente.objects.create(razon_social='Cliente de A', cuit='30-11111111-1',
                                           vendedor=cls.emp_a)
        cls.cli_b = Cliente.objects.create(razon_social='Cliente de B', cuit='30-22222222-2',
                                           vendedor=cls.emp_b)

        cls.con_a = Consulta.objects.create(
            productos='Pallets', razon_social='Cliente de A',
            cliente=cls.cli_a, vendedor=cls.emp_a)
        cls.con_b = Consulta.objects.create(
            productos='Bines', razon_social='Cliente de B',
            cliente=cls.cli_b, vendedor=cls.emp_b)

        cls.producto = Producto.objects.create(
            codigo='P61', nombre='Pallet plástico', categoria='PALLETS')

    def login(self, user):
        self.client.force_login(user)


class RolesYCapacidadesTest(BaseRolesTest):
    def test_capacidades_por_rol(self):
        esperado = {
            self.admin: dict(ver_consultas=True, ver_clientes=True, usuarios=True,
                             catalogo=True, admins=True, staff=True),
            self.gerente: dict(ver_consultas=True, ver_clientes=True, usuarios=True,
                               catalogo=True, admins=False, staff=False),
            self.emp_a: dict(ver_consultas=False, ver_clientes=False, usuarios=False,
                             catalogo=False, admins=False, staff=False),
        }
        for user, exp in esperado.items():
            with self.subTest(rol=user.role):
                self.assertEqual(user.puede_ver_todas_las_consultas, exp['ver_consultas'])
                self.assertEqual(user.puede_ver_todos_los_clientes, exp['ver_clientes'])
                self.assertEqual(user.puede_gestionar_usuarios, exp['usuarios'])
                self.assertEqual(user.puede_editar_catalogo, exp['catalogo'])
                self.assertEqual(user.puede_administrar_admins, exp['admins'])
                self.assertEqual(user.is_staff, exp['staff'])

    def test_is_staff_lo_deriva_el_rol(self):
        self.emp_a.role = User.ADMIN
        self.emp_a.save()
        self.assertTrue(self.emp_a.is_staff)
        self.emp_a.role = User.EMPLEADO
        self.emp_a.save()
        self.assertFalse(self.emp_a.is_staff)

    def test_rol_por_defecto_es_empleado(self):
        nuevo = User.objects.create_user('nuevo@test.com', 'x')
        self.assertEqual(nuevo.role, User.EMPLEADO)


class AlcanceConsultasTest(BaseRolesTest):
    def test_admin_y_gerente_ven_todas(self):
        for user in (self.admin, self.gerente):
            with self.subTest(rol=user.role):
                self.login(user)
                resp = self.client.get(reverse('consultas:list'))
                self.assertEqual(resp.context['total'], 2)

    def test_empleado_ve_solo_las_de_su_cartera(self):
        self.login(self.emp_a)
        resp = self.client.get(reverse('consultas:list'))
        self.assertEqual(resp.context['total'], 1)
        self.assertEqual(resp.context['consultas'][0].pk, self.con_a.pk)

    def test_empleado_no_accede_a_consulta_ajena(self):
        self.login(self.emp_a)
        for nombre in ('consultas:detail', 'consultas:edit', 'consultas:cotizacion',
                       'consultas:cotizacion_pdf'):
            with self.subTest(vista=nombre):
                resp = self.client.get(reverse(nombre, args=[self.con_b.pk]))
                self.assertEqual(resp.status_code, 404)

    def test_empleado_no_puede_editar_consulta_ajena_por_post(self):
        self.login(self.emp_a)
        resp = self.client.post(reverse('consultas:edit', args=[self.con_b.pk]),
                                {'fecha': '2026-01-01', 'productos': 'hackeado',
                                 'via_entrada': 'mail', 'estado': 'cotizado'})
        self.assertEqual(resp.status_code, 404)
        self.con_b.refresh_from_db()
        self.assertEqual(self.con_b.productos, 'Bines')

    def test_dashboard_cuenta_solo_lo_visible(self):
        self.login(self.emp_a)
        self.assertEqual(self.client.get(reverse('dashboard')).context['stats']['total'], 1)
        self.login(self.gerente)
        self.assertEqual(self.client.get(reverse('dashboard')).context['stats']['total'], 2)


class AlcanceClientesTest(BaseRolesTest):
    def test_admin_y_gerente_ven_todos_los_clientes(self):
        for user in (self.admin, self.gerente):
            with self.subTest(rol=user.role):
                self.login(user)
                self.assertEqual(self.client.get(reverse('clientes:list')).context['total'], 2)

    def test_empleado_ve_solo_su_cartera_asignada(self):
        self.login(self.emp_a)
        resp = self.client.get(reverse('clientes:list'))
        self.assertEqual(resp.context['total'], 1)
        self.assertEqual(resp.context['clientes'][0].pk, self.cli_a.pk)

    def test_un_cliente_sin_asignar_no_lo_ve_ningun_empleado(self):
        Cliente.objects.create(razon_social='Huérfano', cuit='30-99999999-9')
        for empleado in (self.emp_a, self.emp_b):
            with self.subTest(empleado=empleado.email):
                self.login(empleado)
                nombres = [c.razon_social for c in
                           self.client.get(reverse('clientes:list')).context['clientes']]
                self.assertNotIn('Huérfano', nombres)

        self.login(self.gerente)
        self.assertEqual(self.client.get(reverse('clientes:list')).context['total'], 3)

    def test_reasignar_mueve_la_cartera_completa(self):
        """La consulta la cargó emp_a, pero el cliente pasa a emp_b."""
        self.cli_a.vendedor = self.emp_b
        self.cli_a.save()

        self.login(self.emp_b)
        self.assertEqual(
            [c.pk for c in self.client.get(reverse('clientes:list')).context['clientes']],
            [self.cli_a.pk, self.cli_b.pk])
        self.assertEqual(
            self.client.get(reverse('consultas:detail', args=[self.con_a.pk])).status_code, 200)

        # El anterior la pierde de vista, aunque la haya cargado él.
        self.login(self.emp_a)
        self.assertEqual(self.client.get(reverse('clientes:list')).context['total'], 0)
        self.assertEqual(
            self.client.get(reverse('consultas:detail', args=[self.con_a.pk])).status_code, 404)

    def test_empleado_no_accede_a_cliente_ajeno(self):
        self.login(self.emp_a)
        self.assertEqual(
            self.client.get(reverse('clientes:detail', args=[self.cli_b.pk])).status_code, 404)
        self.assertEqual(
            self.client.get(reverse('clientes:edit', args=[self.cli_b.pk])).status_code, 404)

    def test_empleado_no_puede_editar_cliente_ajeno_por_post(self):
        self.login(self.emp_a)
        resp = self.client.post(reverse('clientes:edit', args=[self.cli_b.pk]),
                                {'razon_social': 'hackeado'})
        self.assertEqual(resp.status_code, 404)
        self.cli_b.refresh_from_db()
        self.assertEqual(self.cli_b.razon_social, 'Cliente de B')

    def test_autocomplete_no_filtra_clientes_ajenos(self):
        self.login(self.emp_a)
        resp = self.client.get(reverse('clientes:search'), {'q': 'Cliente'})
        self.assertEqual([c['razon_social'] for c in resp.json()], ['Cliente de A'])

    def test_el_asignado_ve_todo_el_historial_del_cliente(self):
        """Hereda el contexto: incluye consultas que cargó otro vendedor."""
        ajena = Consulta.objects.create(productos='Cajones', cliente=self.cli_a,
                                        vendedor=self.emp_b)
        self.login(self.emp_a)
        resp = self.client.get(reverse('clientes:detail', args=[self.cli_a.pk]))
        self.assertEqual({c.pk for c in resp.context['consultas']}, {self.con_a.pk, ajena.pk})

    def test_total_consultas_cuenta_todas_las_del_cliente(self):
        Consulta.objects.create(productos='Cajones', cliente=self.cli_a, vendedor=self.emp_b)
        self.login(self.emp_a)
        resp = self.client.get(reverse('clientes:list'))
        self.assertEqual(resp.context['clientes'][0].total_consultas, 2)

    def test_el_empleado_conserva_sus_consultas_sin_cliente(self):
        """Nada de lo que cargó él mismo desaparece por no tener cliente."""
        suelta = Consulta.objects.create(productos='Sin cliente', vendedor=self.emp_a)
        self.login(self.emp_a)
        self.assertEqual(
            self.client.get(reverse('consultas:detail', args=[suelta.pk])).status_code, 200)
        self.login(self.emp_b)
        self.assertEqual(
            self.client.get(reverse('consultas:detail', args=[suelta.pk])).status_code, 404)


class GestionUsuariosTest(BaseRolesTest):
    def test_empleado_no_entra_a_usuarios(self):
        self.login(self.emp_a)
        resp = self.client.get(reverse('accounts:user_list'))
        self.assertRedirects(resp, reverse('dashboard'))

    def test_gerente_no_ve_admins_en_la_lista(self):
        self.login(self.gerente)
        emails = {u.email for u in self.client.get(reverse('accounts:user_list')).context['users']}
        self.assertNotIn(self.admin.email, emails)
        self.assertIn(self.emp_a.email, emails)

    def test_admin_ve_a_todos_menos_a_si_mismo(self):
        self.login(self.admin)
        emails = {u.email for u in self.client.get(reverse('accounts:user_list')).context['users']}
        self.assertEqual(emails, {self.gerente.email, self.emp_a.email, self.emp_b.email})

    def test_gerente_no_puede_editar_un_admin(self):
        self.login(self.gerente)
        self.assertEqual(
            self.client.get(reverse('accounts:user_edit', args=[self.admin.pk])).status_code, 404)
        self.assertEqual(
            self.client.get(reverse('accounts:user_password', args=[self.admin.pk])).status_code, 404)

    def test_gerente_no_puede_asignar_el_rol_admin(self):
        self.login(self.gerente)
        resp = self.client.post(reverse('accounts:user_create'), {
            'email': 'colado@test.com', 'first_name': 'Co', 'last_name': 'Lado',
            'role': User.ADMIN, 'password1': 'Segura123!', 'password2': 'Segura123!',
        })
        self.assertEqual(resp.status_code, 200)  # el form rechaza el rol
        self.assertFalse(User.objects.filter(email='colado@test.com').exists())

    def test_gerente_puede_crear_un_empleado(self):
        self.login(self.gerente)
        resp = self.client.post(reverse('accounts:user_create'), {
            'email': 'nuevo@test.com', 'first_name': 'Nue', 'last_name': 'Vo',
            'role': User.EMPLEADO, 'password1': 'Segura123!', 'password2': 'Segura123!',
        })
        self.assertRedirects(resp, reverse('accounts:user_list'))
        creado = User.objects.get(email='nuevo@test.com')
        self.assertEqual(creado.role, User.EMPLEADO)
        self.assertFalse(creado.is_staff)

    def test_admin_puede_crear_otro_admin(self):
        self.login(self.admin)
        resp = self.client.post(reverse('accounts:user_create'), {
            'email': 'admin2@test.com', 'first_name': 'Ad', 'last_name': 'Dos',
            'role': User.ADMIN, 'password1': 'Segura123!', 'password2': 'Segura123!',
        })
        self.assertRedirects(resp, reverse('accounts:user_list'))
        self.assertTrue(User.objects.get(email='admin2@test.com').is_staff)


class CatalogoTest(BaseRolesTest):
    """La ficha del artículo es la misma para todos; el formulario, no."""

    def ficha(self):
        return reverse('productos:detail', args=[self.producto.pk])

    def test_solo_admin_y_gerente_ven_el_formulario(self):
        for user in (self.admin, self.gerente):
            with self.subTest(rol=user.role):
                self.login(user)
                self.assertContains(self.client.get(self.ficha()), 'Guardar cambios')

        self.login(self.emp_a)
        resp = self.client.get(self.ficha())
        self.assertEqual(resp.status_code, 200)          # la ficha sí la ve
        self.assertNotContains(resp, 'Guardar cambios')  # editarla, no

    def test_empleado_no_puede_cambiar_precio_por_post(self):
        self.login(self.emp_a)
        self.client.post(self.ficha(), {'nombre': 'Hackeado', 'precio': '1'})
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.nombre, 'Pallet plástico')
        self.assertIsNone(self.producto.precio)

    def test_la_url_vieja_de_edicion_lleva_a_la_ficha(self):
        self.login(self.gerente)
        resp = self.client.get(reverse('productos:edit', args=[self.producto.pk]))
        self.assertRedirects(resp, self.ficha(), status_code=301)

    def test_el_catalogo_lo_ve_cualquier_rol(self):
        for user in (self.admin, self.gerente, self.emp_a):
            with self.subTest(rol=user.role):
                self.login(user)
                resp = self.client.get(reverse('productos:catalogo'), follow=True)
                self.assertEqual(resp.status_code, 200)
