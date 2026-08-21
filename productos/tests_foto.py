"""Borrar la imagen de un artículo, y que se note.

Dos cosas hacían que pareciera que no se borraba. Una, que era un tilde dentro
del formulario de la ficha que además había que guardar, y el botón de guardar
está al pie de la otra columna. La otra, que la URL de la foto no cambia nunca
y el endpoint la manda con caché de siete días, así que el browser seguía
mostrando la vieja incluso después de reemplazarla.
"""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from productos.models import ARS, Producto

User = get_user_model()

PNG_1PX = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00'
           b'\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc'
           b'\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')


def usuario(role, email=None):
    return User.objects.create_user(
        email or f'{role}@test.com', 'x',
        first_name='Test', last_name=role.title(), role=role)


class BaseTest(TestCase):
    def setUp(self):
        self.producto = Producto.objects.create(
            codigo='SA-001', nombre='Guante', moneda=ARS, precio=100,
            foto=PNG_1PX, foto_tipo='image/png')
        self.url = reverse('productos:borrar_foto', args=[self.producto.pk])
        self.ficha = reverse('productos:detail', args=[self.producto.pk])
        self.client.force_login(usuario(User.GERENTE))

    def mensajes(self, respuesta):
        return ' '.join(str(m) for m in respuesta.context['messages'])


class BorrarTest(BaseTest):
    def test_borra_la_imagen(self):
        self.client.post(self.url)
        self.producto.refresh_from_db()
        self.assertFalse(self.producto.foto)
        self.assertEqual(self.producto.foto_tipo, '')

    def test_no_borra_el_articulo(self):
        self.client.post(self.url)
        self.producto.refresh_from_db()
        self.assertTrue(self.producto.activo)
        self.assertEqual(self.producto.nombre, 'Guante')
        self.assertEqual(self.producto.precio, 100)

    def test_vuelve_a_la_ficha_avisando(self):
        respuesta = self.client.post(self.url, follow=True)
        self.assertRedirects(respuesta, self.ficha)
        self.assertIn('Imagen borrada', self.mensajes(respuesta))

    def test_la_ficha_deja_de_mostrarla(self):
        self.client.post(self.url)
        respuesta = self.client.get(self.ficha)
        self.assertNotContains(
            respuesta, reverse('consultas:producto_foto', args=[self.producto.pk]))
        self.assertContains(respuesta, 'Sin imagen')

    def test_el_endpoint_de_la_foto_da_404(self):
        self.client.post(self.url)
        self.assertEqual(
            self.client.get(
                reverse('consultas:producto_foto', args=[self.producto.pk])).status_code,
            404)

    def test_el_catalogo_deja_de_mostrarla(self):
        self.client.post(self.url)
        respuesta = self.client.get(reverse('productos:catalogo'))
        self.assertContains(respuesta, 'Sin foto')

    def test_de_uno_sin_imagen_avisa_y_no_rompe(self):
        Producto.objects.filter(pk=self.producto.pk).update(foto=None, foto_tipo='')
        respuesta = self.client.post(self.url, follow=True)
        self.assertIn('no tenía imagen', self.mensajes(respuesta))

    def test_un_get_no_borra_nada(self):
        """Solo POST: ni un prefetch ni un link mal pegado se lleva una foto."""
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.producto.refresh_from_db()
        self.assertTrue(self.producto.foto)

    def test_de_uno_que_no_existe_da_404(self):
        self.assertEqual(
            self.client.post(
                reverse('productos:borrar_foto', args=[9999])).status_code, 404)

    def test_de_uno_dado_de_baja_da_404(self):
        self.producto.activo = False
        self.producto.save()
        self.assertEqual(self.client.post(self.url).status_code, 404)


class ElBotonTest(BaseTest):
    """Un botón, no un tilde que además hay que guardar."""

    def test_la_ficha_lo_ofrece(self):
        respuesta = self.client.get(self.ficha)
        self.assertContains(respuesta, 'Borrar la imagen')
        self.assertContains(respuesta, self.url)

    def test_no_queda_el_tilde_viejo(self):
        self.assertNotContains(self.client.get(self.ficha), 'borrar_foto"')

    def test_no_va_dentro_del_formulario_de_la_ficha(self):
        """Su propio form: apretarlo no arrastra ni pisa lo que se esté editando."""
        cuerpo = self.client.get(self.ficha).content.decode()
        # El primer form del cuerpo es el de salir, del navbar.
        ficha = cuerpo.split('enctype="multipart/form-data"')[1].split('</form>')[0]
        self.assertNotIn(self.url, ficha)
        self.assertIn('form="form-borrar-foto"', ficha)
        self.assertIn('id="form-borrar-foto"', cuerpo)

    def test_no_aparece_si_no_hay_imagen(self):
        Producto.objects.filter(pk=self.producto.pk).update(foto=None, foto_tipo='')
        respuesta = self.client.get(self.ficha)
        self.assertNotContains(respuesta, 'Borrar la imagen')
        self.assertNotContains(respuesta, self.url)

    def test_guardar_la_ficha_no_toca_la_imagen(self):
        self.client.post(self.ficha, {
            'nombre': 'Guante nuevo', 'unidad_medida': '', 'precio': '100',
            'moneda': ARS, 'categoria': '', 'colores': '', 'especificaciones': '',
        })
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.nombre, 'Guante nuevo')
        self.assertEqual(bytes(self.producto.foto), PNG_1PX)


class VersionDeLaUrlTest(BaseTest):
    """La URL de la foto no cambia nunca y el endpoint la cachea 7 días."""

    def test_el_endpoint_sigue_cacheando(self):
        respuesta = self.client.get(
            reverse('consultas:producto_foto', args=[self.producto.pk]))
        self.assertIn('max-age=604800', respuesta['Cache-Control'])

    def test_la_version_sale_del_updated_at(self):
        self.assertEqual(self.producto.foto_version,
                         int(self.producto.updated_at.timestamp() * 1000))

    def test_dos_guardados_en_el_mismo_segundo_dan_versiones_distintas(self):
        """Con resolución de segundo, la foto nueva se quedaba en el caché."""
        primera = self.producto.foto_version
        self.producto.save()
        self.producto.refresh_from_db()
        self.assertNotEqual(self.producto.foto_version, primera)

    def test_la_ficha_versiona_la_url(self):
        self.assertContains(self.client.get(self.ficha),
                            f'?v={self.producto.foto_version}')

    def test_el_catalogo_versiona_la_url(self):
        self.assertContains(self.client.get(reverse('productos:catalogo')),
                            f'?v={self.producto.foto_version}')

    def test_cambiar_la_foto_cambia_la_version(self):
        """Lo que la saca del caché del browser."""
        antes = self.producto.foto_version
        self.client.post(self.ficha, {
            'nombre': 'Guante', 'unidad_medida': '', 'precio': '100',
            'moneda': ARS, 'categoria': '', 'colores': '', 'especificaciones': '',
            'imagen': SimpleUploadedFile('otra.png', b'otros-bytes',
                                         content_type='image/png'),
        })
        self.producto.refresh_from_db()
        self.assertEqual(bytes(self.producto.foto), b'otros-bytes')
        self.assertGreater(self.producto.foto_version, antes)

    def test_borrarla_tambien_mueve_la_version(self):
        antes = self.producto.foto_version
        self.client.post(self.url)
        self.producto.refresh_from_db()
        self.assertGreater(self.producto.foto_version, antes)

    def test_el_selector_al_cotizar_la_lleva(self):
        from consultas.views import productos_para_selector
        datos = productos_para_selector([self.producto])
        self.assertEqual(datos[0]['foto_v'], self.producto.foto_version)


class PermisosTest(BaseTest):
    """Los mismos roles que editan el catálogo."""

    def test_pueden_los_que_editan_el_catalogo(self):
        for role in (User.ADMIN, User.GERENTE, User.JEFE_VENTAS):
            with self.subTest(role=role):
                Producto.objects.filter(pk=self.producto.pk).update(
                    foto=PNG_1PX, foto_tipo='image/png')
                self.client.force_login(usuario(role, f'foto-{role}@test.com'))
                self.client.post(self.url)
                self.producto.refresh_from_db()
                self.assertFalse(self.producto.foto)

    def test_no_pueden_los_demas(self):
        for role in (User.EMPLEADO, User.TESORERIA, User.COACH):
            with self.subTest(role=role):
                self.client.force_login(usuario(role, f'foto-{role}@test.com'))
                self.client.post(self.url)
                self.producto.refresh_from_db()
                self.assertTrue(self.producto.foto)

    def test_al_empleado_la_ficha_no_le_ofrece_el_boton(self):
        self.client.force_login(usuario(User.EMPLEADO))
        self.assertNotContains(self.client.get(self.ficha), self.url)

    def test_sin_sesion_manda_al_login(self):
        self.client.logout()
        respuesta = self.client.post(self.url)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('login', respuesta['Location'])
