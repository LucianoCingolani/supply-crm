"""Alta manual de artículos del catálogo."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from productos.models import ARS, USD, Producto

User = get_user_model()

# Un PNG de 1x1 real: alcanza para verificar que los bytes llegan a la fila.
PNG_1PX = bytes.fromhex(
    '89504e470d0a1a0a0000000d494844520000000100000001080600000'
    '01f15c4890000000a49444154789c6300010000050001'
    '0d0a2db40000000049454e44ae426082'
)


def usuario(role, email):
    return User.objects.create_user(
        email=email, password='x', first_name='Test', last_name='User', role=role,
    )


def datos(**overrides):
    base = {
        'codigo': 'SA-001',
        'nombre': 'Guante de nitrilo azul talle L',
        'unidad_medida': 'PAR',
        'precio': '1500.50',
        'moneda': ARS,
        'categoria': 'Protección de manos',
    }
    return {**base, **overrides}


class AltaArticuloPermisosTest(TestCase):
    def setUp(self):
        self.url = reverse('productos:create')

    def test_el_empleado_no_entra(self):
        self.client.force_login(usuario(User.EMPLEADO, 'empleado@test.com'))
        respuesta = self.client.get(self.url)
        self.assertRedirects(respuesta, reverse('dashboard'))

    def test_el_empleado_tampoco_puede_crear_por_post(self):
        self.client.force_login(usuario(User.EMPLEADO, 'empleado@test.com'))
        self.client.post(self.url, datos())
        self.assertFalse(Producto.objects.exists())

    def test_el_gerente_entra(self):
        self.client.force_login(usuario(User.GERENTE, 'gerente@test.com'))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_el_admin_entra(self):
        self.client.force_login(usuario(User.ADMIN, 'admin@test.com'))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_el_anonimo_va_al_login(self):
        respuesta = self.client.get(self.url)
        self.assertIn(reverse('accounts:login'), respuesta['Location'])


class AltaArticuloTest(TestCase):
    def setUp(self):
        self.url = reverse('productos:create')
        self.client.force_login(usuario(User.GERENTE, 'gerente@test.com'))

    def test_crea_el_articulo_y_lleva_a_su_ficha(self):
        respuesta = self.client.post(self.url, datos())

        producto = Producto.objects.get(codigo='SA-001')
        self.assertRedirects(respuesta, reverse('productos:detail', args=[producto.pk]))
        self.assertEqual(producto.nombre, 'Guante de nitrilo azul talle L')
        self.assertEqual(producto.unidad_medida, 'PAR')
        self.assertEqual(producto.precio, Decimal('1500.50'))
        self.assertEqual(producto.categoria, 'Protección de manos')
        self.assertTrue(producto.activo)

    def test_nace_visible_en_el_catalogo(self):
        self.client.post(self.url, datos())
        respuesta = self.client.get(reverse('productos:catalogo'), {'categoria': 'Protección de manos'})
        self.assertContains(respuesta, 'SA-001')

    def test_guarda_la_imagen_en_la_fila(self):
        imagen = SimpleUploadedFile('foto.png', PNG_1PX, content_type='image/png')
        self.client.post(self.url, datos(imagen=imagen))

        producto = Producto.objects.get(codigo='SA-001')
        self.assertEqual(bytes(producto.foto), PNG_1PX)
        self.assertEqual(producto.foto_tipo, 'image/png')

    def test_la_imagen_es_opcional(self):
        self.client.post(self.url, datos())
        self.assertFalse(Producto.objects.get(codigo='SA-001').foto)

    def test_rechaza_un_archivo_que_no_es_imagen(self):
        archivo = SimpleUploadedFile('lista.pdf', b'%PDF-1.4', content_type='application/pdf')
        respuesta = self.client.post(self.url, datos(imagen=archivo))

        self.assertFalse(Producto.objects.exists())
        self.assertContains(respuesta, 'tiene que ser una imagen')

    def test_rechaza_una_imagen_demasiado_grande(self):
        grande = SimpleUploadedFile('grande.png', b'x' * (5 * 1024 * 1024 + 1), content_type='image/png')
        respuesta = self.client.post(self.url, datos(imagen=grande))

        self.assertFalse(Producto.objects.exists())
        self.assertContains(respuesta, 'no puede superar los 5 MB')

    def test_no_permite_repetir_el_codigo(self):
        Producto.objects.create(codigo='SA-001', nombre='El que ya estaba')
        respuesta = self.client.post(self.url, datos(nombre='El nuevo'))

        self.assertEqual(Producto.objects.filter(codigo='SA-001').count(), 1)
        self.assertEqual(Producto.objects.get(codigo='SA-001').nombre, 'El que ya estaba')
        self.assertEqual(respuesta.status_code, 200)

    def test_acepta_la_coma_como_separador_decimal(self):
        self.client.post(self.url, datos(precio='1500,50'))
        self.assertEqual(Producto.objects.get(codigo='SA-001').precio, Decimal('1500.50'))

    def test_el_precio_puede_quedar_vacio(self):
        self.client.post(self.url, datos(precio=''))
        self.assertIsNone(Producto.objects.get(codigo='SA-001').precio)

    def test_rechaza_un_precio_que_no_es_numero(self):
        respuesta = self.client.post(self.url, datos(precio='mil quinientos'))
        self.assertFalse(Producto.objects.exists())
        self.assertEqual(respuesta.status_code, 200)

    def test_exige_codigo_y_descripcion(self):
        self.client.post(self.url, datos(codigo='', nombre=''))
        self.assertFalse(Producto.objects.exists())

    def test_exige_la_unidad_de_medida(self):
        respuesta = self.client.post(self.url, datos(unidad_medida=''))
        self.assertFalse(Producto.objects.exists())
        self.assertEqual(respuesta.status_code, 200)

    def test_guarda_la_moneda_elegida(self):
        self.client.post(self.url, datos(moneda=USD))
        self.assertEqual(Producto.objects.get(codigo='SA-001').moneda, USD)

    def test_rechaza_una_moneda_inventada(self):
        respuesta = self.client.post(self.url, datos(moneda='BTC'))
        self.assertFalse(Producto.objects.exists())
        self.assertEqual(respuesta.status_code, 200)

    def test_sugiere_las_categorias_que_ya_existen(self):
        Producto.objects.create(codigo='SA-999', nombre='Otro', categoria='Calzado de seguridad')
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'Calzado de seguridad')

    def test_no_pierde_lo_cargado_cuando_el_formulario_falla(self):
        Producto.objects.create(codigo='SA-001', nombre='El que ya estaba')
        respuesta = self.client.post(self.url, datos(nombre='Casco tipo minero'))
        self.assertContains(respuesta, 'Casco tipo minero')


class EditarUnidadMedidaTest(TestCase):
    """La unidad tiene que poder corregirse después del alta."""

    def setUp(self):
        self.producto = Producto.objects.create(codigo='SA-001', nombre='Guante', unidad_medida='PAR')
        self.url = reverse('productos:edit', args=[self.producto.pk])
        self.client.force_login(usuario(User.GERENTE, 'gerente@test.com'))

    def test_la_cambia(self):
        self.client.post(self.url, {'nombre': 'Guante', 'precio': '', 'unidad_medida': 'CAJA'})
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.unidad_medida, 'CAJA')

    def test_ignora_una_unidad_inventada(self):
        self.client.post(self.url, {'nombre': 'Guante', 'precio': '', 'unidad_medida': 'BANANAS'})
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.unidad_medida, 'PAR')

    def test_cambia_la_moneda(self):
        self.client.post(self.url, {'nombre': 'Guante', 'precio': '250', 'moneda': USD})
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.moneda, USD)

    def test_ignora_una_moneda_inventada(self):
        self.client.post(self.url, {'nombre': 'Guante', 'precio': '250', 'moneda': 'BTC'})
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.moneda, ARS)
