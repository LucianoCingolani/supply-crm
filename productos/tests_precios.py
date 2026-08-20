"""El rol Tesorería y su pantalla de precios.

Tesorería entra a mantener la lista de precios y a mirar el catálogo, nada más.
Lo que se protege acá es el alcance —que no llegue al circuito comercial ni al
resto de la ficha del artículo— y que un error de tipeo en una fila no le haga
perder las otras ediciones de la pantalla.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from productos.models import ARS, USD, Categoria, Producto

User = get_user_model()


def usuario(role, email=None):
    return User.objects.create_user(
        email or f'{role}@test.com', 'x',
        first_name='Test', last_name='User', role=role)


class RolTest(TestCase):
    def test_tesoreria_es_un_rol_elegible(self):
        self.assertIn((User.TESORERIA, 'Tesorería'), User.ROLE_CHOICES)

    def test_no_ve_los_datos_de_toda_la_empresa(self):
        self.assertNotIn(User.TESORERIA, User.ROLES_VISION_TOTAL)

    def test_sus_capacidades(self):
        tes = usuario(User.TESORERIA)
        self.assertTrue(tes.puede_editar_precios)
        self.assertFalse(tes.puede_ver_ventas)
        self.assertFalse(tes.puede_editar_catalogo)
        self.assertFalse(tes.puede_ver_reportes)
        self.assertFalse(tes.puede_gestionar_usuarios)
        self.assertFalse(tes.puede_borrar_clientes)

    def test_no_entra_al_admin_de_django(self):
        self.assertFalse(usuario(User.TESORERIA).is_staff)

    def test_quienes_pueden_poner_precios(self):
        for role in (User.ADMIN, User.GERENTE, User.TESORERIA):
            with self.subTest(rol=role):
                self.assertTrue(usuario(role, f'{role}@x.com').puede_editar_precios)
        self.assertFalse(usuario(User.EMPLEADO).puede_editar_precios)

    def test_su_casa_es_la_pantalla_de_precios(self):
        """La portada muestra números de consultas: para Tesorería no sirve."""
        self.assertEqual(usuario(User.TESORERIA).pagina_inicial, 'productos:precios')
        self.assertEqual(usuario(User.EMPLEADO).pagina_inicial, 'dashboard')


class AlcanceTest(TestCase):
    """Lo que Tesorería no tiene que poder abrir."""

    def setUp(self):
        self.tes = usuario(User.TESORERIA)
        self.client.force_login(self.tes)
        self.precios = reverse('productos:precios')

    def test_el_dashboard_lo_manda_a_precios(self):
        """Y no puede rebotar contra sí mismo: sería un bucle."""
        self.assertRedirects(self.client.get(reverse('dashboard')), self.precios)

    def test_no_entra_a_consultas(self):
        self.assertRedirects(self.client.get(reverse('consultas:list')), self.precios)

    def test_no_entra_a_clientes(self):
        self.assertRedirects(self.client.get(reverse('clientes:list')), self.precios)

    def test_no_entra_al_alta_de_clientes(self):
        self.assertRedirects(self.client.get(reverse('clientes:create')), self.precios)

    def test_no_entra_a_reportes(self):
        self.assertRedirects(self.client.get(reverse('reportes:equipo')), self.precios)

    def test_no_entra_a_usuarios(self):
        self.assertRedirects(self.client.get(reverse('accounts:user_list')), self.precios)

    def test_si_ve_el_catalogo(self):
        self.assertEqual(self.client.get(reverse('productos:catalogo')).status_code, 200)

    def test_ve_la_ficha_del_articulo_pero_sin_formulario(self):
        producto = Producto.objects.create(codigo='P1', nombre='Pallet')
        respuesta = self.client.get(reverse('productos:detail', args=[producto.pk]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'Guardar cambios')

    def test_no_puede_editar_el_articulo_por_post(self):
        producto = Producto.objects.create(codigo='P1', nombre='Pallet', moneda=ARS)
        self.client.post(reverse('productos:detail', args=[producto.pk]),
                         {'nombre': 'Hackeado', 'moneda': ARS})

        producto.refresh_from_db()
        self.assertEqual(producto.nombre, 'Pallet')

    def test_no_puede_dar_de_alta_articulos(self):
        self.assertRedirects(self.client.get(reverse('productos:create')), self.precios)

    def test_el_menu_no_le_ofrece_ventas(self):
        cuerpo = self.client.get(self.precios).content.decode()
        self.assertNotIn(reverse('consultas:list'), cuerpo)
        self.assertNotIn(reverse('clientes:list'), cuerpo)
        self.assertIn(reverse('productos:catalogo'), cuerpo)
        self.assertIn(self.precios, cuerpo)


class AccesoAPreciosTest(TestCase):
    def setUp(self):
        self.url = reverse('productos:precios')

    def test_entran_tesoreria_gerente_y_admin(self):
        for role in (User.TESORERIA, User.GERENTE, User.ADMIN):
            with self.subTest(rol=role):
                self.client.force_login(usuario(role, f'{role}@x.com'))
                self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_el_empleado_no_entra(self):
        self.client.force_login(usuario(User.EMPLEADO))
        self.assertRedirects(self.client.get(self.url), reverse('dashboard'))

    def test_el_empleado_tampoco_puede_guardar(self):
        producto = Producto.objects.create(codigo='P1', nombre='Pallet',
                                          precio=Decimal('100'), moneda=ARS)
        self.client.force_login(usuario(User.EMPLEADO))
        self.client.post(self.url, {f'precio_{producto.pk}': '999'})

        producto.refresh_from_db()
        self.assertEqual(producto.precio, Decimal('100'))

    def test_el_anonimo_va_al_login(self):
        respuesta = self.client.get(self.url)
        self.assertIn(reverse('accounts:login'), respuesta['Location'])


class GuardarPreciosTest(TestCase):
    def setUp(self):
        self.client.force_login(usuario(User.TESORERIA))
        self.url = reverse('productos:precios')
        self.p1 = Producto.objects.create(codigo='P1', nombre='Pallet',
                                          categoria=Categoria.desde_nombre('pallets plasticos'),
                                          precio=Decimal('100'), moneda=ARS)
        self.p2 = Producto.objects.create(codigo='P2', nombre='Cajón',
                                          categoria=Categoria.desde_nombre('Cajones'),
                                          precio=Decimal('200'), moneda=ARS)

    def payload(self, **overrides):
        base = {
            f'precio_{self.p1.pk}': '100.00', f'moneda_{self.p1.pk}': ARS,
            f'precio_{self.p2.pk}': '200.00', f'moneda_{self.p2.pk}': ARS,
        }
        return {**base, **overrides}

    def test_guarda_el_precio_cambiado(self):
        self.client.post(self.url, self.payload(**{f'precio_{self.p1.pk}': '150.50'}))

        self.p1.refresh_from_db()
        self.assertEqual(self.p1.precio, Decimal('150.50'))

    def test_guarda_varios_de_una_pasada(self):
        self.client.post(self.url, self.payload(**{
            f'precio_{self.p1.pk}': '111', f'precio_{self.p2.pk}': '222'}))

        self.p1.refresh_from_db(); self.p2.refresh_from_db()
        self.assertEqual(self.p1.precio, Decimal('111.00'))
        self.assertEqual(self.p2.precio, Decimal('222.00'))

    def test_acepta_la_coma_como_separador_decimal(self):
        self.client.post(self.url, self.payload(**{f'precio_{self.p1.pk}': '150,75'}))

        self.p1.refresh_from_db()
        self.assertEqual(self.p1.precio, Decimal('150.75'))

    def test_cambia_la_moneda(self):
        self.client.post(self.url, self.payload(**{f'moneda_{self.p1.pk}': USD}))

        self.p1.refresh_from_db()
        self.assertEqual(self.p1.moneda, USD)

    def test_una_moneda_inventada_no_cambia_nada(self):
        self.client.post(self.url, self.payload(**{f'moneda_{self.p1.pk}': 'BTC'}))

        self.p1.refresh_from_db()
        self.assertEqual(self.p1.moneda, ARS)

    def test_un_precio_vacio_deja_el_articulo_sin_precio(self):
        self.client.post(self.url, self.payload(**{f'precio_{self.p1.pk}': ''}))

        self.p1.refresh_from_db()
        self.assertIsNone(self.p1.precio)

    def test_refresca_la_fecha_solo_de_lo_que_cambio(self):
        antes = self.p2.updated_at
        self.client.post(self.url, self.payload(**{f'precio_{self.p1.pk}': '150'}))

        self.p1.refresh_from_db(); self.p2.refresh_from_db()
        self.assertGreater(self.p1.updated_at, antes)
        self.assertEqual(self.p2.updated_at, antes)

    def test_no_toca_nada_mas_de_la_ficha(self):
        self.p1.especificaciones = 'Una spec'
        self.p1.nombre = 'Pallet original'
        self.p1.save()
        self.client.post(self.url, self.payload(**{f'precio_{self.p1.pk}': '150'}))

        self.p1.refresh_from_db()
        self.assertEqual(self.p1.nombre, 'Pallet original')
        self.assertEqual(self.p1.especificaciones, 'Una spec')

    def test_vuelve_a_la_pantalla_conservando_el_filtro(self):
        respuesta = self.client.post(
            f'{self.url}?categoria=Cajones',
            self.payload(**{f'precio_{self.p2.pk}': '250'}))
        self.assertRedirects(respuesta, f'{self.url}?categoria=Cajones')

    def test_avisa_cuando_no_habia_nada_que_guardar(self):
        respuesta = self.client.post(self.url, self.payload(), follow=True)
        self.assertContains(respuesta, 'No había ningún cambio')


class PrecioInvalidoTest(TestCase):
    def setUp(self):
        self.client.force_login(usuario(User.TESORERIA))
        self.url = reverse('productos:precios')
        self.p1 = Producto.objects.create(codigo='P1', nombre='Pallet',
                                          precio=Decimal('100'), moneda=ARS)
        self.p2 = Producto.objects.create(codigo='P2', nombre='Cajón',
                                          precio=Decimal('200'), moneda=ARS)

    def test_no_guarda_nada_si_una_fila_esta_mal(self):
        """Todo o nada: guardar la mitad en silencio es peor."""
        self.client.post(self.url, {
            f'precio_{self.p1.pk}': 'cien',
            f'precio_{self.p2.pk}': '222',
        })

        self.p1.refresh_from_db(); self.p2.refresh_from_db()
        self.assertEqual(self.p1.precio, Decimal('100'))
        self.assertEqual(self.p2.precio, Decimal('200'))

    def test_dice_cual_es_la_fila_mal(self):
        respuesta = self.client.post(self.url, {
            f'precio_{self.p1.pk}': 'cien', f'precio_{self.p2.pk}': '222'})

        self.assertContains(respuesta, 'No se guardó nada')
        self.assertContains(respuesta, 'P1')

    def test_no_pierde_las_otras_ediciones(self):
        """Si se perdieran, habría que tipear todo de nuevo por un error ajeno."""
        respuesta = self.client.post(self.url, {
            f'precio_{self.p1.pk}': 'cien', f'precio_{self.p2.pk}': '222'})

        cuerpo = respuesta.content.decode()
        self.assertIn('value="cien"', cuerpo)   # lo que tipeó, para corregirlo
        self.assertIn('value="222"', cuerpo)    # y lo que había puesto bien

    def test_rechaza_un_precio_negativo(self):
        self.client.post(self.url, {f'precio_{self.p1.pk}': '-50'})

        self.p1.refresh_from_db()
        self.assertEqual(self.p1.precio, Decimal('100'))


class FiltrosTest(TestCase):
    def setUp(self):
        self.client.force_login(usuario(User.TESORERIA))
        self.url = reverse('productos:precios')
        Producto.objects.create(codigo='P1', nombre='Pallet ventilado',
                                categoria=Categoria.desde_nombre('pallets plasticos'), precio=Decimal('100'))
        Producto.objects.create(codigo='C1', nombre='Cajón cerrado',
                                categoria=Categoria.desde_nombre('Cajones'), precio=Decimal('200'))
        Producto.objects.create(codigo='X1', nombre='Dado de baja',
                                categoria=Categoria.desde_nombre('Cajones'), activo=False)

    def test_filtra_por_categoria(self):
        respuesta = self.client.get(self.url, {'categoria': 'Cajones'})
        self.assertContains(respuesta, 'C1')
        self.assertNotContains(respuesta, 'P1')

    def test_busca_por_codigo_y_por_descripcion(self):
        self.assertContains(self.client.get(self.url, {'q': 'P1'}), 'Pallet ventilado')
        self.assertContains(self.client.get(self.url, {'q': 'ventilado'}), 'Pallet ventilado')

    def test_no_lista_los_inactivos(self):
        self.assertNotContains(self.client.get(self.url), 'Dado de baja')

    def test_ofrece_las_categorias_para_filtrar(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'Cajones')
        self.assertContains(respuesta, 'pallets plasticos')
