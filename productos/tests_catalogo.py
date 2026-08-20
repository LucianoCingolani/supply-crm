"""El catálogo: buscador global, «Todos» y paginado.

Antes entrabas y caías en la primera categoría, y el buscador se limitaba a la
que tuvieras abierta: para encontrar un artículo había que acertar la categoría
primero. Con 740 artículos eso era el camino largo para todo.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from productos.models import ARS, Categoria, Producto
from productos.views import CatalogoView

User = get_user_model()
URL = reverse('productos:catalogo')

PNG_1PX = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00'
           b'\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc'
           b'\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')


class BaseTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'vendedor@test.com', 'x', first_name='V', last_name='E',
            role=User.EMPLEADO)
        self.client.force_login(self.user)
        self.cajones = Categoria.objects.create(nombre='Cajones')
        self.tanques = Categoria.objects.create(nombre='Tanques')
        self.cajon = self.crear('C1', 'Cajón cosechero', self.cajones)
        self.tanque = self.crear('T1', 'Tanque 1000L', self.tanques)
        self.huerfano = self.crear('X1', 'Bidón 20L')

    def crear(self, codigo, nombre, categoria=None, **extra):
        return Producto.objects.create(
            codigo=codigo, nombre=nombre, categoria=categoria, moneda=ARS, **extra)

    def listados(self, respuesta):
        return list(respuesta.context['pagina'].object_list)

    def barra(self, respuesta):
        return {c['nombre']: c['total'] for c in respuesta.context['categorias']}


class TodosTest(BaseTest):
    def test_entrar_al_catalogo_muestra_todo(self):
        """Ya no redirige a la primera categoría."""
        respuesta = self.client.get(URL)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(self.listados(respuesta)), 3)

    def test_incluye_los_que_no_tienen_categoria(self):
        self.assertIn(self.huerfano, self.listados(self.client.get(URL)))

    def test_todos_figura_en_la_barra_con_el_total(self):
        respuesta = self.client.get(URL)
        self.assertEqual(respuesta.context['total_general'], 3)
        self.assertContains(respuesta, 'Todos')

    def test_no_cuenta_los_dados_de_baja(self):
        self.crear('B1', 'Cajón viejo', self.cajones, activo=False)
        self.assertEqual(self.client.get(URL).context['total_general'], 3)

    def test_una_categoria_sigue_filtrando(self):
        respuesta = self.client.get(URL, {'categoria': 'Cajones'})
        self.assertEqual(self.listados(respuesta), [self.cajon])
        self.assertEqual(respuesta.context['categoria_activa'], 'Cajones')

    def test_la_barra_no_lista_categorias_vacias(self):
        Categoria.objects.create(nombre='Bidones')
        self.assertNotIn('Bidones', self.barra(self.client.get(URL)))

    def test_la_barra_cuenta_los_articulos_de_cada_una(self):
        self.crear('C2', 'Cajón multiuso', self.cajones)
        self.assertEqual(self.barra(self.client.get(URL)),
                         {'Cajones': 2, 'Tanques': 1})


class BuscadorGlobalTest(BaseTest):
    def test_busca_en_todo_el_catalogo(self):
        self.assertEqual(self.listados(self.client.get(URL, {'q': 'tanque'})),
                         [self.tanque])

    def test_encuentra_uno_de_otra_categoria_estando_en_una(self):
        """El caso que motivó el cambio: buscar sin acertar la categoría."""
        respuesta = self.client.get(URL, {'q': 'tanque', 'categoria': ''})
        self.assertEqual(self.listados(respuesta), [self.tanque])

    def test_el_formulario_no_arrastra_la_categoria_abierta(self):
        cuerpo = self.client.get(URL, {'categoria': 'Cajones'}).content.decode()
        formulario = cuerpo.split('<form method="get"')[1].split('</form>')[0]
        self.assertNotIn('name="categoria"', formulario)

    def test_encuentra_los_sin_categoria(self):
        self.assertEqual(self.listados(self.client.get(URL, {'q': 'bidon'})), [])
        self.assertEqual(self.listados(self.client.get(URL, {'q': 'Bidón'})),
                         [self.huerfano])

    def test_busca_por_codigo(self):
        self.assertEqual(self.listados(self.client.get(URL, {'q': 't1'})),
                         [self.tanque])

    def test_busca_en_las_especificaciones(self):
        self.cajon.especificaciones = 'Polietileno de alta densidad'
        self.cajon.save()
        self.assertEqual(self.listados(self.client.get(URL, {'q': 'polietileno'})),
                         [self.cajon])

    def test_la_barra_muestra_donde_cayeron_los_resultados(self):
        self.crear('C2', 'Cajón para tanque', self.cajones)
        self.assertEqual(self.barra(self.client.get(URL, {'q': 'tanque'})),
                         {'Cajones': 1, 'Tanques': 1})

    def test_la_barra_esconde_las_que_no_tienen_resultados(self):
        self.assertEqual(self.barra(self.client.get(URL, {'q': 'tanque'})),
                         {'Tanques': 1})

    def test_una_categoria_acota_la_busqueda(self):
        self.crear('C2', 'Cajón para tanque', self.cajones)
        respuesta = self.client.get(URL, {'q': 'tanque', 'categoria': 'Cajones'})
        self.assertEqual(len(self.listados(respuesta)), 1)
        self.assertEqual(respuesta.context['total'], 1)
        # El total general sigue contando la búsqueda entera.
        self.assertEqual(respuesta.context['total_general'], 2)

    def test_los_enlaces_de_la_barra_conservan_la_busqueda(self):
        cuerpo = self.client.get(URL, {'q': 'tanque'}).content.decode()
        self.assertIn('q=tanque', cuerpo)

    def test_una_busqueda_sin_resultados_no_rompe(self):
        respuesta = self.client.get(URL, {'q': 'zzzz'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'No se encontraron productos')

    def test_limpiar_vuelve_a_todos(self):
        respuesta = self.client.get(URL, {'q': 'tanque'})
        self.assertContains(respuesta, f'href="{URL}"')


class PaginadoTest(BaseTest):
    def test_no_pagina_cuando_no_hace_falta(self):
        pagina = self.client.get(URL).context['pagina']
        self.assertFalse(pagina.has_other_pages())

    def test_corta_en_sesenta_por_pagina(self):
        for i in range(CatalogoView.POR_PAGINA + 5):
            self.crear(f'M{i}', f'Masivo {i:03}', self.cajones)
        respuesta = self.client.get(URL)
        self.assertEqual(len(self.listados(respuesta)), CatalogoView.POR_PAGINA)
        self.assertEqual(respuesta.context['pagina'].paginator.num_pages, 2)

    def test_la_segunda_pagina_trae_el_resto(self):
        for i in range(CatalogoView.POR_PAGINA + 5):
            self.crear(f'M{i}', f'Masivo {i:03}', self.cajones)
        respuesta = self.client.get(URL, {'pagina': 2})
        self.assertEqual(len(self.listados(respuesta)), 8)  # 65 + los 3 del setUp

    def test_el_paginado_conserva_el_filtro(self):
        for i in range(CatalogoView.POR_PAGINA + 5):
            self.crear(f'M{i}', f'Masivo {i:03}', self.cajones)
        respuesta = self.client.get(URL, {'categoria': 'Cajones', 'pagina': 2})
        self.assertEqual(respuesta.context['categoria_activa'], 'Cajones')
        self.assertEqual(len(self.listados(respuesta)), 6)

    def test_una_pagina_inexistente_cae_en_la_ultima(self):
        self.assertEqual(self.client.get(URL, {'pagina': 99}).status_code, 200)

    def test_una_pagina_no_numerica_no_rompe(self):
        self.assertEqual(self.client.get(URL, {'pagina': 'x'}).status_code, 200)


class FotosTest(BaseTest):
    """Pesan medio mega cada una: la grilla las pide por URL, no embebidas."""

    def setUp(self):
        super().setUp()
        self.cajon.foto = PNG_1PX
        self.cajon.foto_tipo = 'image/png'
        self.cajon.save()

    def test_la_grilla_apunta_al_endpoint_de_la_foto(self):
        self.assertContains(
            self.client.get(URL),
            reverse('consultas:producto_foto', args=[self.cajon.pk]))

    def test_no_embebe_el_binario_en_el_html(self):
        self.assertNotContains(self.client.get(URL), 'data:image/png;base64')

    def test_las_pide_en_diferido(self):
        self.assertContains(self.client.get(URL), 'loading="lazy"')

    def test_sabe_quien_tiene_foto_sin_traerse_los_bytes(self):
        productos = {p.codigo: p for p in self.listados(self.client.get(URL))}
        self.assertTrue(productos['C1'].bytes_de_foto)
        self.assertFalse(productos['T1'].bytes_de_foto)

    def test_no_carga_las_fotos_en_memoria(self):
        """`only()` las deja afuera; tocarlas dispararía otra consulta."""
        producto = self.listados(self.client.get(URL))[0]
        self.assertNotIn('foto', producto.__dict__)

    def test_el_que_no_tiene_foto_muestra_el_placeholder(self):
        self.assertContains(self.client.get(URL), 'Sin foto')


class ConsultasSqlTest(BaseTest):
    def test_no_hace_una_consulta_por_articulo(self):
        for i in range(20):
            self.crear(f'M{i}', f'Masivo {i:03}', self.cajones)
        with self.assertNumQueries(5):
            # sesión + usuario + conteo de la barra + total + página
            self.client.get(URL)

    def test_con_una_categoria_abierta_cuenta_una_vez_mas(self):
        """El total general deja de coincidir con el de la página."""
        with self.assertNumQueries(6):
            self.client.get(URL, {'categoria': 'Cajones'})
