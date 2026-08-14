"""El rol Coach de ventas: ve toda la operación comercial y no escribe nada.

Es el primer rol que separa "ver todo" de "poder todo", que hasta ahora eran la
misma lista. Lo que se protege acá es el borde: que llegue a cada pantalla de
consultas y clientes, y que ninguna escritura pase — ni por formulario visible
ni por POST directo.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from consultas.models import Consulta, LineaCotizacion, SeguimientoLog
from productos.models import ARS, Producto

User = get_user_model()


def usuario(role, email=None):
    return User.objects.create_user(
        email or f'{role}@test.com', 'x',
        first_name='Test', last_name=role.title(), role=role)


class RolTest(TestCase):
    def test_es_un_rol_elegible(self):
        self.assertIn((User.COACH, 'Coach de ventas'), User.ROLE_CHOICES)

    def test_ve_toda_la_empresa(self):
        coach = usuario(User.COACH)
        self.assertTrue(coach.puede_ver_todas_las_consultas)
        self.assertTrue(coach.puede_ver_todos_los_clientes)
        self.assertTrue(coach.puede_ver_reportes)
        self.assertTrue(coach.puede_ver_ventas)

    def test_no_escribe_ni_administra(self):
        coach = usuario(User.COACH)
        self.assertFalse(coach.puede_cargar_ventas)
        self.assertFalse(coach.puede_asignar_clientes)
        self.assertFalse(coach.puede_borrar_clientes)
        self.assertFalse(coach.puede_gestionar_usuarios)
        self.assertFalse(coach.puede_editar_catalogo)
        self.assertFalse(coach.puede_editar_precios)

    def test_no_entra_al_admin_de_django(self):
        self.assertFalse(usuario(User.COACH).is_staff)

    def test_no_lleva_cartera(self):
        self.assertFalse(usuario(User.COACH).lleva_cartera)
        self.assertTrue(usuario(User.EMPLEADO).lleva_cartera)

    def test_ver_todo_y_poder_todo_dejaron_de_ser_la_misma_lista(self):
        self.assertIn(User.COACH, User.ROLES_VISION_TOTAL)
        self.assertNotIn(User.COACH, User.ROLES_DE_ADMINISTRACION)

    def test_el_gerente_sigue_pudiendo_todo(self):
        gerente = usuario(User.GERENTE)
        for capacidad in ('puede_ver_todas_las_consultas', 'puede_gestionar_usuarios',
                          'puede_asignar_clientes', 'puede_borrar_clientes',
                          'puede_editar_catalogo', 'puede_ver_reportes',
                          'puede_cargar_ventas'):
            with self.subTest(capacidad=capacidad):
                self.assertTrue(getattr(gerente, capacidad))


class BaseCoachTest(TestCase):
    def setUp(self):
        self.coach = usuario(User.COACH)
        self.emp = usuario(User.EMPLEADO)
        self.cliente = Cliente.objects.create(
            razon_social='ACME SRL', cuit='30-71234567-8', vendedor=self.emp)
        self.consulta = Consulta.objects.create(
            productos='Pallets', razon_social='ACME SRL',
            cliente=self.cliente, vendedor=self.emp, moneda=ARS)
        self.client.force_login(self.coach)


class VeTodoTest(BaseCoachTest):
    def test_ve_las_consultas_de_todos_los_vendedores(self):
        respuesta = self.client.get(reverse('consultas:list'))
        self.assertContains(respuesta, 'ACME SRL')

    def test_ve_los_clientes_de_todas_las_carteras(self):
        respuesta = self.client.get(reverse('clientes:list'))
        self.assertContains(respuesta, 'ACME SRL')

    def test_puede_filtrar_por_vendedor(self):
        self.assertIsNotNone(
            self.client.get(reverse('consultas:list')).context['vendedores'])

    def test_entra_a_la_ficha_de_un_cliente_ajeno(self):
        respuesta = self.client.get(reverse('clientes:detail', args=[self.cliente.pk]))
        self.assertEqual(respuesta.status_code, 200)

    def test_entra_a_la_ficha_de_una_consulta_ajena(self):
        respuesta = self.client.get(reverse('consultas:detail', args=[self.consulta.pk]))
        self.assertEqual(respuesta.status_code, 200)

    def test_entra_al_panel_del_equipo(self):
        self.assertEqual(self.client.get(reverse('reportes:equipo')).status_code, 200)

    def test_entra_a_la_ficha_de_un_vendedor(self):
        respuesta = self.client.get(reverse('reportes:empleado', args=[self.emp.pk]))
        self.assertEqual(respuesta.status_code, 200)

    def test_ve_el_dashboard(self):
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_ve_la_cotizacion_y_su_pdf(self):
        respuesta = self.client.get(reverse('consultas:cotizacion', args=[self.consulta.pk]))
        self.assertEqual(respuesta.status_code, 200)


class NoEscribeTest(BaseCoachTest):
    """Cada escritura, por POST directo: los botones ocultos no son seguridad."""

    def destino(self):
        return reverse('dashboard')

    def test_no_registra_seguimiento_en_una_consulta(self):
        self.client.post(reverse('consultas:detail', args=[self.consulta.pk]),
                         {'nota': 'Le dije que apure'})
        self.assertEqual(SeguimientoLog.objects.count(), 0)

    def test_no_registra_seguimiento_en_un_cliente(self):
        self.client.post(reverse('clientes:detail', args=[self.cliente.pk]),
                         {'nota': 'Le dije que apure'})
        self.assertEqual(SeguimientoLog.objects.count(), 0)

    def test_no_edita_una_consulta(self):
        self.client.post(reverse('consultas:edit', args=[self.consulta.pk]),
                         {'fecha': '2026-08-01', 'productos': 'Cambiado',
                          'via_entrada': 'mail', 'estado': 'facturado'})
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.productos, 'Pallets')
        self.assertEqual(self.consulta.estado, Consulta.COTIZADO)

    def test_ni_le_abre_el_formulario_de_edicion(self):
        respuesta = self.client.get(reverse('consultas:edit', args=[self.consulta.pk]))
        self.assertRedirects(respuesta, self.destino())

    def test_no_edita_un_cliente(self):
        self.client.post(reverse('clientes:edit', args=[self.cliente.pk]),
                         {'razon_social': 'Cambiado'})
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.razon_social, 'ACME SRL')

    def test_no_crea_clientes(self):
        self.client.post(reverse('clientes:create'), {'razon_social': 'Nuevo'})
        self.assertEqual(Cliente.objects.count(), 1)

    def test_no_crea_clientes_desde_el_modal(self):
        self.client.post(reverse('consultas:cliente_rapido'), {'razon_social': 'Nuevo'})
        self.assertEqual(Cliente.objects.count(), 1)

    def test_no_crea_consultas(self):
        self.client.post(reverse('consultas:create', args=[self.cliente.pk]),
                         {'fecha': '2026-08-01', 'productos': 'Algo',
                          'via_entrada': 'mail', 'estado': 'cotizado'})
        self.assertEqual(Consulta.objects.count(), 1)

    def test_no_crea_cotizaciones(self):
        self.client.post(reverse('consultas:nueva_cotizacion', args=[self.cliente.pk]), {
            'fecha': '2026-08-01', 'via_entrada': 'mail',
            'linea_desc_0': 'Pallet', 'linea_cant_0': '1', 'linea_precio_0': '100',
        })
        self.assertEqual(Consulta.objects.count(), 1)

    def test_no_agrega_lineas_a_una_cotizacion(self):
        self.client.post(reverse('consultas:cotizacion', args=[self.consulta.pk]), {
            'action': 'add', 'descripcion': 'Pallet',
            'cantidad': '1', 'precio_unitario': '100',
        })
        self.assertEqual(LineaCotizacion.objects.count(), 0)

    def test_no_borra_lineas_de_una_cotizacion(self):
        linea = LineaCotizacion.objects.create(
            consulta=self.consulta, descripcion='Pallet',
            cantidad=1, precio_unitario=Decimal('100'), moneda=ARS)
        self.client.post(reverse('consultas:cotizacion', args=[self.consulta.pk]),
                         {'action': 'delete', 'linea_id': linea.pk})
        self.assertTrue(LineaCotizacion.objects.filter(pk=linea.pk).exists())

    def test_no_cambia_la_moneda_de_una_cotizacion(self):
        self.client.post(reverse('consultas:cotizacion', args=[self.consulta.pk]),
                         {'action': 'moneda', 'moneda': 'USD', 'tipo_cambio': '1000'})
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.moneda, ARS)

    def test_no_asigna_clientes(self):
        self.client.post(reverse('clientes:asignar'),
                         {'cliente': [self.cliente.pk], 'vendedor': 'ninguno'})
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.vendedor, self.emp)

    def test_no_borra_clientes(self):
        self.client.post(reverse('clientes:borrar', args=[self.cliente.pk]))
        self.assertTrue(Cliente.objects.filter(pk=self.cliente.pk).exists())

    def test_no_toca_el_catalogo(self):
        producto = Producto.objects.create(codigo='P1', nombre='Pallet', moneda=ARS)
        self.client.post(reverse('productos:detail', args=[producto.pk]),
                         {'nombre': 'Cambiado', 'moneda': ARS})
        producto.refresh_from_db()
        self.assertEqual(producto.nombre, 'Pallet')

    def test_no_entra_a_los_precios(self):
        self.assertRedirects(self.client.get(reverse('productos:precios')),
                             self.destino())

    def test_no_gestiona_usuarios(self):
        self.assertRedirects(self.client.get(reverse('accounts:user_list')),
                             self.destino())


class PantallasSinBotonesTest(BaseCoachTest):
    """Lo que no puede hacer tampoco se le ofrece."""

    def test_la_lista_de_consultas_no_le_ofrece_crear(self):
        cuerpo = self.client.get(reverse('consultas:list')).content.decode()
        self.assertNotIn('+ Nueva consulta', cuerpo)
        self.assertNotIn('modal-nueva-consulta', cuerpo)

    def test_la_lista_de_clientes_no_le_ofrece_crear(self):
        self.assertNotContains(self.client.get(reverse('clientes:list')),
                               '+ Nuevo cliente')

    def test_la_ficha_del_cliente_no_le_ofrece_editar_ni_cotizar(self):
        cuerpo = self.client.get(
            reverse('clientes:detail', args=[self.cliente.pk])).content.decode()
        self.assertNotIn('Editar cliente', cuerpo)
        self.assertNotIn('Nueva cotización', cuerpo)
        self.assertNotIn('Registrar', cuerpo)

    def test_la_ficha_de_la_consulta_no_le_ofrece_registrar_seguimiento(self):
        self.assertNotContains(
            self.client.get(reverse('consultas:detail', args=[self.consulta.pk])),
            'Registrar')

    def test_la_cotizacion_no_le_ofrece_agregar_ni_quitar(self):
        LineaCotizacion.objects.create(
            consulta=self.consulta, descripcion='Pallet',
            cantidad=1, precio_unitario=Decimal('100'), moneda=ARS)
        cuerpo = self.client.get(
            reverse('consultas:cotizacion', args=[self.consulta.pk])).content.decode()
        self.assertNotIn('Agregar producto', cuerpo)
        self.assertNotIn('Quitar', cuerpo)
        self.assertNotIn('Guardar moneda', cuerpo)
        # El PDF sí: es lectura.
        self.assertIn(reverse('consultas:cotizacion_pdf', args=[self.consulta.pk]), cuerpo)

    def test_el_menu_le_muestra_lo_comercial_y_no_los_precios(self):
        cuerpo = self.client.get(reverse('consultas:list')).content.decode()
        self.assertIn(reverse('consultas:list'), cuerpo)
        self.assertIn(reverse('clientes:list'), cuerpo)
        self.assertIn(reverse('reportes:equipo'), cuerpo)
        self.assertNotIn(reverse('productos:precios'), cuerpo)


class NoLlevaCarteraTest(TestCase):
    """No se le pueden asignar clientes: sacaría al cliente del circuito."""

    def setUp(self):
        self.gerente = usuario(User.GERENTE)
        self.coach = usuario(User.COACH)
        self.emp = usuario(User.EMPLEADO)
        self.cliente = Cliente.objects.create(razon_social='ACME SRL', vendedor=self.emp)
        self.client.force_login(self.gerente)

    def test_no_aparece_entre_los_vendedores_asignables(self):
        vendedores = self.client.get(reverse('clientes:list')).context['vendedores']
        self.assertNotIn(self.coach, vendedores)
        self.assertIn(self.emp, vendedores)

    def test_no_aparece_en_el_formulario_del_cliente(self):
        form = self.client.get(
            reverse('clientes:edit', args=[self.cliente.pk])).context['form']
        self.assertNotIn(self.coach, form.fields['vendedor'].queryset)

    def test_asignarle_un_cliente_no_tiene_efecto(self):
        self.client.post(reverse('clientes:asignar'),
                         {'cliente': [self.cliente.pk], 'vendedor': self.coach.pk})
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.vendedor, self.emp)

    def test_tesoreria_tampoco_lleva_cartera(self):
        tes = usuario(User.TESORERIA)
        vendedores = self.client.get(reverse('clientes:list')).context['vendedores']
        self.assertNotIn(tes, vendedores)
