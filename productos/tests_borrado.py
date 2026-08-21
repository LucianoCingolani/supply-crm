"""Sacar un artículo del catálogo, y poder volverlo a poner.

Es una baja y no un DELETE: la línea de una cotización guarda su propia
descripción y precio, pero la foto y la ficha las saca del artículo, así que
borrar la fila le cambiaría el PDF a cotizaciones ya enviadas.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from consultas.models import Consulta, LineaCotizacion
from productos.models import ARS, Categoria, Producto

User = get_user_model()
BAJAS = reverse('productos:bajas')

PNG_1PX = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00'
           b'\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc'
           b'\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')


def usuario(role, email=None):
    return User.objects.create_user(
        email or f'{role}@test.com', 'x',
        first_name='Test', last_name=role.title(), role=role)


class BaseTest(TestCase):
    def setUp(self):
        self.gerente = usuario(User.GERENTE)
        self.client.force_login(self.gerente)
        self.cajones = Categoria.objects.create(nombre='Cajones')
        self.producto = Producto.objects.create(
            codigo='C1', nombre='Cajón cosechero', categoria=self.cajones,
            precio=1000, moneda=ARS, especificaciones='Polietileno',
            foto=PNG_1PX, foto_tipo='image/png')
        self.url = reverse('productos:borrar', args=[self.producto.pk])

    def mensajes(self, respuesta):
        return ' '.join(str(m) for m in respuesta.context['messages'])


class ConfirmacionTest(BaseTest):
    def test_el_get_no_borra_nada(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.producto.refresh_from_db()
        self.assertTrue(self.producto.activo)

    def test_muestra_el_articulo(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'Cajón cosechero')
        self.assertContains(respuesta, 'C1')

    def test_avisa_que_no_figura_en_ninguna_cotizacion(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.context['cotizaciones'], 0)
        self.assertContains(respuesta, 'no hay historial en juego')

    def test_cuenta_en_cuantas_cotizaciones_figura(self):
        for i in range(2):
            consulta = Consulta.objects.create(
                productos='x', razon_social='ACME', vendedor=self.gerente, moneda=ARS)
            LineaCotizacion.objects.create(
                consulta=consulta, producto=self.producto,
                descripcion='Cajón', cantidad=1, precio_unitario=1000, moneda=ARS)
        self.assertEqual(self.client.get(self.url).context['cotizaciones'], 2)

    def test_no_cuenta_dos_veces_la_misma_cotizacion(self):
        consulta = Consulta.objects.create(
            productos='x', razon_social='ACME', vendedor=self.gerente, moneda=ARS)
        for i in range(2):
            LineaCotizacion.objects.create(
                consulta=consulta, producto=self.producto, orden=i,
                descripcion='Cajón', cantidad=1, precio_unitario=1000, moneda=ARS)
        self.assertEqual(self.client.get(self.url).context['cotizaciones'], 1)

    def test_de_uno_que_no_existe_da_404(self):
        self.assertEqual(
            self.client.get(reverse('productos:borrar', args=[9999])).status_code, 404)

    def test_de_uno_ya_dado_de_baja_da_404(self):
        self.producto.activo = False
        self.producto.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)


class BorrarTest(BaseTest):
    def test_lo_saca_del_catalogo(self):
        self.client.post(self.url)
        self.producto.refresh_from_db()
        self.assertFalse(self.producto.activo)

    def test_no_borra_la_fila(self):
        """La baja es reversible: los datos quedan."""
        self.client.post(self.url)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.nombre, 'Cajón cosechero')
        self.assertEqual(bytes(self.producto.foto), PNG_1PX)
        self.assertEqual(self.producto.especificaciones, 'Polietileno')
        self.assertEqual(self.producto.precio, 1000)

    def test_vuelve_al_catalogo_con_un_aviso(self):
        respuesta = self.client.post(self.url, follow=True)
        self.assertRedirects(respuesta, reverse('productos:catalogo'))
        self.assertIn('salió del catálogo', self.mensajes(respuesta))

    def test_le_toca_la_fecha_de_modificacion(self):
        antes = self.producto.updated_at
        self.client.post(self.url)
        self.producto.refresh_from_db()
        self.assertGreater(self.producto.updated_at, antes)

    def test_desaparece_del_catalogo(self):
        self.client.post(self.url)
        respuesta = self.client.get(reverse('productos:catalogo'))
        self.assertEqual(list(respuesta.context['pagina'].object_list), [])
        self.assertEqual(respuesta.context['total_general'], 0)

    def test_desaparece_de_la_lista_de_precios(self):
        self.client.post(self.url)
        respuesta = self.client.get(reverse('productos:precios'))
        self.assertEqual(list(respuesta.context['productos']), [])

    def test_desaparece_del_selector_al_cotizar(self):
        cliente = Cliente.objects.create(razon_social='ACME SRL')
        self.client.post(self.url)
        respuesta = self.client.get(
            reverse('consultas:nueva_cotizacion', args=[cliente.pk]))
        self.assertEqual(respuesta.context['productos'], [])

    def test_no_se_llega_mas_a_su_ficha(self):
        self.client.post(self.url)
        respuesta = self.client.get(
            reverse('productos:detail', args=[self.producto.pk]))
        self.assertEqual(respuesta.status_code, 404)

    def test_su_categoria_deja_de_contarlo(self):
        self.client.post(self.url)
        respuesta = self.client.get(reverse('productos:categorias'),
                                    {'abierta': self.cajones.pk})
        self.assertEqual(
            {c.nombre: c.total for c in respuesta.context['categorias']},
            {'Cajones': 1})  # la tabla lo sigue teniendo
        self.assertEqual(list(respuesta.context['articulos']), [])


class NoRompeLasCotizacionesTest(BaseTest):
    """Lo que motivó que sea una baja y no un DELETE."""

    def setUp(self):
        super().setUp()
        self.consulta = Consulta.objects.create(
            productos='x', razon_social='ACME', vendedor=self.gerente, moneda=ARS)
        self.linea = LineaCotizacion.objects.create(
            consulta=self.consulta, producto=self.producto,
            descripcion='Cajón cosechero', cantidad=2, precio_unitario=1000,
            moneda=ARS)
        self.client.post(self.url)

    def test_la_linea_sigue_apuntando_al_articulo(self):
        self.linea.refresh_from_db()
        self.assertEqual(self.linea.producto, self.producto)

    def test_la_cotizacion_conserva_su_precio(self):
        self.linea.refresh_from_db()
        self.assertEqual(self.linea.precio_unitario, 1000)

    def test_el_pdf_sigue_encontrando_la_foto(self):
        self.linea.refresh_from_db()
        self.assertTrue(self.linea.producto.foto_data_uri)

    def test_la_cotizacion_se_sigue_viendo(self):
        respuesta = self.client.get(
            reverse('consultas:cotizacion', args=[self.consulta.pk]))
        self.assertContains(respuesta, 'Cajón cosechero')


class ReactivarTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.client.post(self.url)

    def test_la_pantalla_lo_lista(self):
        respuesta = self.client.get(BAJAS)
        self.assertEqual(list(respuesta.context['productos']), [self.producto])
        self.assertContains(respuesta, 'Cajón cosechero')

    def test_no_lista_los_que_estan_en_el_catalogo(self):
        Producto.objects.create(codigo='C2', nombre='Cajón vivo', moneda=ARS)
        self.assertEqual(len(self.client.get(BAJAS).context['productos']), 1)

    def test_lo_devuelve_al_catalogo(self):
        self.client.post(BAJAS, {'producto': self.producto.pk})
        self.producto.refresh_from_db()
        self.assertTrue(self.producto.activo)

    def test_avisa_y_vuelve_a_la_pantalla(self):
        respuesta = self.client.post(BAJAS, {'producto': self.producto.pk},
                                     follow=True)
        self.assertRedirects(respuesta, BAJAS)
        self.assertIn('volvió al catálogo', self.mensajes(respuesta))

    def test_reaparece_en_el_catalogo(self):
        self.client.post(BAJAS, {'producto': self.producto.pk})
        self.assertContains(self.client.get(reverse('productos:catalogo')),
                            'Cajón cosechero')

    def test_no_reactiva_uno_que_ya_esta_activo(self):
        vivo = Producto.objects.create(codigo='C2', nombre='Cajón vivo', moneda=ARS)
        self.assertEqual(
            self.client.post(BAJAS, {'producto': vivo.pk}).status_code, 404)

    def test_sin_bajas_lo_dice(self):
        self.client.post(BAJAS, {'producto': self.producto.pk})
        self.assertContains(self.client.get(BAJAS), 'No hay artículos dados de baja')


class EnlacesTest(BaseTest):
    def test_la_ficha_ofrece_eliminar(self):
        respuesta = self.client.get(
            reverse('productos:detail', args=[self.producto.pk]))
        self.assertContains(respuesta, self.url)

    def test_el_catalogo_ofrece_los_dados_de_baja(self):
        self.assertContains(self.client.get(reverse('productos:catalogo')), BAJAS)

    def test_a_un_empleado_la_ficha_no_le_ofrece_eliminar(self):
        self.client.force_login(usuario(User.EMPLEADO))
        respuesta = self.client.get(
            reverse('productos:detail', args=[self.producto.pk]))
        self.assertNotContains(respuesta, self.url)

    def test_a_un_empleado_el_catalogo_no_le_ofrece_las_bajas(self):
        self.client.force_login(usuario(User.EMPLEADO))
        self.assertNotContains(self.client.get(reverse('productos:catalogo')), BAJAS)


class PermisosTest(BaseTest):
    """Los mismos roles que editan el catálogo."""

    def entra(self, role):
        self.client.force_login(usuario(role, f'permiso-{role}@test.com'))
        return self.client.get(self.url).status_code == 200

    def test_pueden_los_que_editan_el_catalogo(self):
        for role in (User.ADMIN, User.GERENTE, User.JEFE_VENTAS):
            with self.subTest(role=role):
                self.assertTrue(self.entra(role))

    def test_no_pueden_los_demas(self):
        for role in (User.EMPLEADO, User.TESORERIA, User.COACH):
            with self.subTest(role=role):
                self.assertFalse(self.entra(role))

    def test_un_empleado_no_lo_borra_por_post(self):
        self.client.force_login(usuario(User.EMPLEADO))
        self.client.post(self.url)
        self.producto.refresh_from_db()
        self.assertTrue(self.producto.activo)

    def test_tesoreria_tampoco_por_post(self):
        """Pone precios, no da de baja artículos."""
        self.client.force_login(usuario(User.TESORERIA))
        self.client.post(self.url)
        self.producto.refresh_from_db()
        self.assertTrue(self.producto.activo)

    def test_un_empleado_no_entra_a_las_bajas(self):
        self.client.force_login(usuario(User.EMPLEADO))
        self.assertRedirects(self.client.get(BAJAS), reverse('dashboard'))

    def test_un_empleado_no_reactiva_por_post(self):
        self.client.post(self.url)
        self.client.force_login(usuario(User.EMPLEADO))
        self.client.post(BAJAS, {'producto': self.producto.pk})
        self.producto.refresh_from_db()
        self.assertFalse(self.producto.activo)

    def test_sin_sesion_manda_al_login(self):
        self.client.logout()
        for url in (self.url, BAJAS):
            with self.subTest(url=url):
                respuesta = self.client.get(url)
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn('login', respuesta['Location'])
