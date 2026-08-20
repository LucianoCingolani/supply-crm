"""La pantalla de categorías: que el gerente no dependa de nadie.

Antes la categoría era texto libre en cada artículo y agregar una nueva pasaba
por sistemas. Ahora es una tabla con su propia pantalla: crear, renombrar,
borrar y mover artículos de una a otra.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from productos.models import ARS, Categoria, Producto

User = get_user_model()
URL = reverse('productos:categorias')


def usuario(role):
    return User.objects.create_user(
        f'{role}@test.com', 'x', first_name='Test', last_name=role.title(), role=role)


def producto(codigo, nombre, categoria=None, **extra):
    return Producto.objects.create(
        codigo=codigo, nombre=nombre, categoria=categoria, moneda=ARS, **extra)


class BaseTest(TestCase):
    def setUp(self):
        self.gerente = usuario(User.GERENTE)
        self.client.force_login(self.gerente)
        self.pallets = Categoria.objects.create(nombre='Pallets')
        self.tanques = Categoria.objects.create(nombre='Tanques')
        self.pallet = producto('P1', 'Pallet reforzado', self.pallets)
        self.huerfano = producto('X1', 'Bidon 20L')

    def enviar(self, datos, query=''):
        return self.client.post(URL + query, datos, follow=True)

    def mensajes(self, respuesta):
        return ' '.join(str(m) for m in respuesta.context['messages'])


class PantallaTest(BaseTest):
    def test_lista_las_categorias_con_su_cantidad(self):
        respuesta = self.client.get(URL)
        self.assertContains(respuesta, 'Pallets')
        self.assertContains(respuesta, 'Tanques')
        self.assertEqual(
            {c.nombre: c.total for c in respuesta.context['categorias']},
            {'Pallets': 1, 'Tanques': 0})

    def test_muestra_las_vacias(self):
        """El catálogo las esconde; acá hay que verlas para poder llenarlas."""
        self.assertIn(self.tanques, self.client.get(URL).context['categorias'])

    def test_avisa_cuantos_quedan_sin_clasificar(self):
        self.assertEqual(self.client.get(URL).context['sin_clasificar'], 1)
        self.assertContains(self.client.get(URL), 'sin clasificar')

    def test_sin_categoria_abierta_no_lista_articulos(self):
        respuesta = self.client.get(URL)
        self.assertIsNone(respuesta.context['abierta'])
        self.assertIsNone(respuesta.context['articulos'])

    def test_al_abrir_una_categoria_se_ve_lo_que_tiene(self):
        respuesta = self.client.get(URL, {'abierta': self.pallets.pk})
        self.assertEqual(respuesta.context['abierta'], self.pallets)
        self.assertEqual(list(respuesta.context['miembros']), [self.pallet])
        self.assertContains(respuesta, 'Pallet reforzado')

    def test_al_abrir_ofrece_los_sin_clasificar_para_mover(self):
        respuesta = self.client.get(URL, {'abierta': self.pallets.pk})
        self.assertEqual(list(respuesta.context['articulos']), [self.huerfano])

    def test_no_ofrece_mover_los_que_ya_estan_adentro(self):
        respuesta = self.client.get(URL, {'abierta': self.pallets.pk})
        self.assertNotIn(self.pallet, respuesta.context['articulos'])

    def test_el_buscador_alcanza_a_los_que_ya_tienen_otra_categoria(self):
        otro = producto('T1', 'Tanque 1000L', self.tanques)
        respuesta = self.client.get(URL, {'abierta': self.pallets.pk, 'q': 'tanque'})
        self.assertEqual(list(respuesta.context['articulos']), [otro])

    def test_el_buscador_tambien_toma_el_codigo(self):
        respuesta = self.client.get(URL, {'abierta': self.pallets.pk, 'q': 'x1'})
        self.assertEqual(list(respuesta.context['articulos']), [self.huerfano])

    def test_no_ofrece_articulos_dados_de_baja(self):
        producto('B1', 'Cajon viejo', activo=False)
        respuesta = self.client.get(URL, {'abierta': self.pallets.pk})
        self.assertEqual(list(respuesta.context['articulos']), [self.huerfano])

    def test_una_categoria_inexistente_no_rompe(self):
        respuesta = self.client.get(URL, {'abierta': 9999})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIsNone(respuesta.context['abierta'])


class CrearTest(BaseTest):
    def test_crea_una_categoria_vacia(self):
        respuesta = self.enviar({'accion': 'crear', 'nombre': 'Bidones'})
        self.assertTrue(Categoria.objects.filter(nombre='Bidones').exists())
        self.assertEqual(Categoria.objects.get(nombre='Bidones').productos.count(), 0)
        self.assertIn('creada', self.mensajes(respuesta))

    def test_le_recorta_los_espacios(self):
        self.enviar({'accion': 'crear', 'nombre': '  Bidones  '})
        self.assertTrue(Categoria.objects.filter(nombre='Bidones').exists())

    def test_no_acepta_el_nombre_vacio(self):
        self.enviar({'accion': 'crear', 'nombre': '   '})
        self.assertEqual(Categoria.objects.count(), 2)

    def test_no_duplica_ignorando_mayusculas(self):
        """Que el catálogo se parta en dos por 'pallets' y 'Pallets'."""
        respuesta = self.enviar({'accion': 'crear', 'nombre': 'pallets'})
        self.assertEqual(Categoria.objects.filter(nombre__iexact='pallets').count(), 1)
        self.assertIn('Ya existe', self.mensajes(respuesta))

    def test_la_nueva_no_aparece_en_el_catalogo_hasta_tener_articulos(self):
        self.enviar({'accion': 'crear', 'nombre': 'Bidones'})
        respuesta = self.client.get(reverse('productos:catalogo'),
                                    {'categoria': 'Pallets'})
        self.assertNotContains(respuesta, 'Bidones')


class RenombrarTest(BaseTest):
    def test_renombra_y_los_articulos_la_siguen(self):
        self.enviar({'accion': 'renombrar', 'categoria': self.pallets.pk,
                     'nombre': 'Pallets plasticos'})
        self.pallets.refresh_from_db()
        self.assertEqual(self.pallets.nombre, 'Pallets plasticos')
        self.pallet.refresh_from_db()
        self.assertEqual(self.pallet.categoria.nombre, 'Pallets plasticos')

    def test_el_catalogo_muestra_el_nombre_nuevo(self):
        self.enviar({'accion': 'renombrar', 'categoria': self.pallets.pk,
                     'nombre': 'Pallets plasticos'})
        # El catálogo sin filtro redirige a la primera categoría.
        respuesta = self.client.get(reverse('productos:catalogo'), follow=True)
        self.assertContains(respuesta, 'Pallets plasticos')

    def test_no_lo_deja_chocar_con_otra(self):
        respuesta = self.enviar({'accion': 'renombrar', 'categoria': self.pallets.pk,
                                 'nombre': 'tanques'})
        self.pallets.refresh_from_db()
        self.assertEqual(self.pallets.nombre, 'Pallets')
        self.assertIn('Ya existe otra', self.mensajes(respuesta))

    def test_deja_arreglarle_las_mayusculas_a_la_propia(self):
        """Chocar consigo misma no es chocar."""
        minuscula = Categoria.objects.create(nombre='bidones')
        self.enviar({'accion': 'renombrar', 'categoria': minuscula.pk,
                     'nombre': 'Bidones'})
        minuscula.refresh_from_db()
        self.assertEqual(minuscula.nombre, 'Bidones')

    def test_no_acepta_el_nombre_vacio(self):
        self.enviar({'accion': 'renombrar', 'categoria': self.pallets.pk,
                     'nombre': ''})
        self.pallets.refresh_from_db()
        self.assertEqual(self.pallets.nombre, 'Pallets')


class BorrarTest(BaseTest):
    def test_borra_la_categoria(self):
        self.enviar({'accion': 'borrar', 'categoria': self.tanques.pk})
        self.assertFalse(Categoria.objects.filter(pk=self.tanques.pk).exists())

    def test_no_se_lleva_los_articulos(self):
        """Borrar una sección no es borrar el stock: quedan sin clasificar."""
        respuesta = self.enviar({'accion': 'borrar', 'categoria': self.pallets.pk})
        self.pallet.refresh_from_db()
        self.assertTrue(Producto.objects.filter(pk=self.pallet.pk).exists())
        self.assertIsNone(self.pallet.categoria)
        self.assertIn('sin clasificar', self.mensajes(respuesta))

    def test_de_una_inexistente_avisa_y_no_rompe(self):
        respuesta = self.enviar({'accion': 'borrar', 'categoria': 9999})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('No encontr', self.mensajes(respuesta))


class MoverTest(BaseTest):
    def test_mueve_un_sin_clasificar(self):
        self.enviar({'accion': 'mover', 'categoria': self.tanques.pk,
                     'producto': [self.huerfano.pk]})
        self.huerfano.refresh_from_db()
        self.assertEqual(self.huerfano.categoria, self.tanques)

    def test_mueve_varios_de_una(self):
        otro = producto('X2', 'Bidon 10L')
        self.enviar({'accion': 'mover', 'categoria': self.tanques.pk,
                     'producto': [self.huerfano.pk, otro.pk]})
        self.assertEqual(Producto.objects.filter(categoria=self.tanques).count(), 2)

    def test_lo_saca_de_la_categoria_anterior(self):
        self.enviar({'accion': 'mover', 'categoria': self.tanques.pk,
                     'producto': [self.pallet.pk]})
        self.pallet.refresh_from_db()
        self.assertEqual(self.pallet.categoria, self.tanques)
        self.assertEqual(self.pallets.productos.count(), 0)

    def test_avisa_cuando_no_se_tildo_nada(self):
        respuesta = self.enviar({'accion': 'mover', 'categoria': self.tanques.pk})
        self.assertIn('No tildaste', self.mensajes(respuesta))

    def test_conserva_la_categoria_abierta_y_la_busqueda(self):
        """Mover de a tandas sin volver a filtrar cada vez."""
        respuesta = self.client.post(
            f'{URL}?abierta={self.tanques.pk}&q=bidon',
            {'accion': 'mover', 'categoria': self.tanques.pk,
             'producto': [self.huerfano.pk]})
        self.assertIn(f'abierta={self.tanques.pk}', respuesta['Location'])
        self.assertIn('q=bidon', respuesta['Location'])

    def test_le_toca_la_fecha_de_modificacion(self):
        antes = self.huerfano.updated_at
        self.enviar({'accion': 'mover', 'categoria': self.tanques.pk,
                     'producto': [self.huerfano.pk]})
        self.huerfano.refresh_from_db()
        self.assertGreater(self.huerfano.updated_at, antes)


class AccionDesconocidaTest(BaseTest):
    def test_no_hace_nada(self):
        respuesta = self.enviar({'accion': 'truncar', 'categoria': self.pallets.pk})
        self.assertEqual(Categoria.objects.count(), 2)
        self.assertIn('desconocida', self.mensajes(respuesta))

    def test_sin_accion_tampoco(self):
        self.enviar({'categoria': self.pallets.pk})
        self.assertEqual(Categoria.objects.count(), 2)


class PermisosTest(TestCase):
    """La pantalla es de quien mantiene el catálogo."""

    def setUp(self):
        self.categoria = Categoria.objects.create(nombre='Pallets')

    def entra(self, role):
        self.client.force_login(usuario(role))
        return self.client.get(URL).status_code == 200

    def test_la_ven_los_que_editan_el_catalogo(self):
        for role in (User.ADMIN, User.GERENTE, User.JEFE_VENTAS):
            with self.subTest(role=role):
                self.assertTrue(self.entra(role))

    def test_no_la_ven_los_demas(self):
        for role in (User.EMPLEADO, User.TESORERIA, User.COACH):
            with self.subTest(role=role):
                self.assertFalse(self.entra(role))

    def test_tesoreria_pone_precios_pero_no_ordena_el_catalogo(self):
        self.client.force_login(usuario(User.TESORERIA))
        self.assertEqual(self.client.get(reverse('productos:precios')).status_code, 200)
        self.assertRedirects(self.client.get(URL), reverse('productos:precios'))

    def test_un_empleado_no_crea_categorias_por_post(self):
        self.client.force_login(usuario(User.EMPLEADO))
        self.client.post(URL, {'accion': 'crear', 'nombre': 'Colada'})
        self.assertFalse(Categoria.objects.filter(nombre='Colada').exists())

    def test_un_empleado_no_borra_categorias_por_post(self):
        self.client.force_login(usuario(User.EMPLEADO))
        self.client.post(URL, {'accion': 'borrar', 'categoria': self.categoria.pk})
        self.assertTrue(Categoria.objects.filter(pk=self.categoria.pk).exists())

    def test_sin_sesion_manda_al_login(self):
        respuesta = self.client.get(URL)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('login', respuesta['Location'])


class NavbarTest(TestCase):
    """El acceso vive en el grupo Gestión."""

    def test_el_gerente_lo_tiene_en_el_menu(self):
        self.client.force_login(usuario(User.GERENTE))
        self.assertContains(self.client.get(reverse('productos:catalogo')), URL)

    def test_al_empleado_no_se_le_ofrece(self):
        self.client.force_login(usuario(User.EMPLEADO))
        self.assertNotContains(self.client.get(reverse('productos:catalogo')), URL)

    def test_a_tesoreria_tampoco(self):
        self.client.force_login(usuario(User.TESORERIA))
        self.assertNotContains(self.client.get(reverse('productos:precios')), URL)
