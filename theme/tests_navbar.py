"""El navbar: marcar dónde estás y agrupar lo administrativo.

Antes los links se veían todos iguales en cualquier pantalla, y el gerente
tenía siete sueltos en una fila.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from consultas.models import Consulta
from productos.models import ARS, Producto
from theme.templatetags.navegacion import CLASES_ACTIVA

User = get_user_model()


def usuario(role, email=None):
    return User.objects.create_user(
        email or f'{role}@test.com', 'x',
        first_name='Test', last_name='User', role=role)


class SeccionActivaTest(TestCase):
    """La sección se resuelve por app, así las pantallas internas también marcan."""

    def setUp(self):
        self.user = usuario(User.GERENTE)
        self.emp = usuario(User.EMPLEADO)
        self.cliente = Cliente.objects.create(razon_social='ACME SRL', vendedor=self.emp)
        self.consulta = Consulta.objects.create(
            productos='Pallets', cliente=self.cliente, vendedor=self.emp, moneda=ARS)
        self.producto = Producto.objects.create(codigo='P1', nombre='Pallet', moneda=ARS)
        self.client.force_login(self.user)

    def activos(self, url):
        """Las etiquetas del navbar que quedaron resaltadas en esa URL."""
        import re
        cuerpo = self.client.get(url).content.decode()
        nav = cuerpo[cuerpo.index('<nav'):cuerpo.index('</nav>')]
        return re.findall(r'class="[^"]*%s[^"]*"[^>]*>\s*([^<\s][^<]*?)\s*<'
                          % re.escape(CLASES_ACTIVA), nav)

    def test_cada_seccion_se_marca_a_si_misma(self):
        casos = {
            reverse('dashboard'): 'Dashboard',
            reverse('consultas:list'): 'Consultas',
            reverse('clientes:list'): 'Clientes',
            reverse('productos:catalogo'): 'Catálogo',
        }
        for url, etiqueta in casos.items():
            with self.subTest(url=url):
                self.assertIn(etiqueta, self.activos(url))

    def test_solo_una_seccion_a_la_vez(self):
        self.assertEqual(self.activos(reverse('clientes:list')), ['Clientes'])

    def test_la_ficha_de_un_cliente_marca_clientes(self):
        self.assertIn('Clientes',
                      self.activos(reverse('clientes:detail', args=[self.cliente.pk])))

    def test_una_cotizacion_marca_consultas(self):
        self.assertIn('Consultas',
                      self.activos(reverse('consultas:cotizacion', args=[self.consulta.pk])))

    def test_la_ficha_de_un_articulo_marca_catalogo(self):
        self.assertIn('Catálogo',
                      self.activos(reverse('productos:detail', args=[self.producto.pk])))

    def test_precios_no_marca_catalogo_aunque_compartan_app(self):
        activos = self.activos(reverse('productos:precios'))
        self.assertNotIn('Catálogo', activos)

    def test_cambiar_la_propia_contrasena_no_marca_usuarios(self):
        self.assertEqual(self.activos(reverse('accounts:change_password')), [])


class GrupoGestionTest(TestCase):
    def cuerpo(self, role):
        self.client.force_login(usuario(role, f'{role}@x.com'))
        destino = (reverse('productos:precios') if role == User.TESORERIA
                   else reverse('productos:catalogo'))
        return self.client.get(destino).content.decode()

    def test_el_gerente_ve_el_desplegable_y_no_los_tres_sueltos(self):
        cuerpo = self.cuerpo(User.GERENTE)
        self.assertIn('Gestión', cuerpo)
        for item in ('Precios', 'Equipo', 'Usuarios'):
            self.assertIn(item, cuerpo)

    def test_el_empleado_no_ve_nada_de_gestion(self):
        cuerpo = self.cuerpo(User.EMPLEADO)
        self.assertNotIn('Gestión', cuerpo)
        self.assertNotIn('Usuarios', cuerpo)

    def test_con_un_solo_acceso_va_suelto_y_no_en_un_menu(self):
        """Esconder el único acceso de un rol detrás de un menú lo empeora."""
        cuerpo = self.cuerpo(User.TESORERIA)
        self.assertIn('Precios', cuerpo)
        self.assertNotIn('Gestión', cuerpo)

    def test_el_coach_tiene_equipo_suelto(self):
        cuerpo = self.cuerpo(User.COACH)
        self.assertIn('Equipo', cuerpo)
        self.assertNotIn('Gestión', cuerpo)

    def test_el_jefe_de_ventas_agrupa_precios_y_equipo(self):
        cuerpo = self.cuerpo(User.JEFE_VENTAS)
        self.assertIn('Gestión', cuerpo)
        self.assertNotIn('Usuarios', cuerpo)

    def test_el_boton_del_grupo_se_marca_desde_adentro(self):
        self.client.force_login(usuario(User.GERENTE))
        cuerpo = self.client.get(reverse('reportes:equipo')).content.decode()
        nav = cuerpo[cuerpo.index('<nav'):cuerpo.index('</nav>')]
        boton = nav[nav.index('Gestión') - 400:nav.index('Gestión')]
        self.assertIn(CLASES_ACTIVA, boton)


class MenuDelUsuarioTest(TestCase):
    def test_agrupa_contrasena_y_salida_bajo_el_nombre(self):
        self.client.force_login(usuario(User.EMPLEADO))
        cuerpo = self.client.get(reverse('productos:catalogo')).content.decode()

        self.assertIn('Cambiar contraseña', cuerpo)
        self.assertIn('Salir', cuerpo)
        self.assertIn(reverse('accounts:logout'), cuerpo)

    def test_muestra_el_rol(self):
        self.client.force_login(usuario(User.JEFE_VENTAS))
        self.assertContains(self.client.get(reverse('productos:catalogo')),
                            'Jefe de ventas')
