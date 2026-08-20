"""Dashboard con gráficos: alcance por rol, métricas y geometría del SVG."""

import re
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from consultas.models import Consulta
from reportes.graficos import PALETA, grafico_evolucion
from reportes.metricas import (
    calcular_metricas,
    evolucion_mensual,
    reparto_por_estado,
)

User = get_user_model()


class BaseDashboardTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hoy = timezone.localdate()
        cls.gerente = User.objects.create_user(
            'g@test.com', 'x', first_name='Gaby', last_name='Gerente', role=User.GERENTE)
        cls.emp_a = User.objects.create_user(
            'a@test.com', 'x', first_name='Ana', last_name='Alfa', role=User.EMPLEADO)
        cls.emp_b = User.objects.create_user(
            'b@test.com', 'x', first_name='Beto', last_name='Beta', role=User.EMPLEADO)

    def consulta(self, vendedor, estado=Consulta.COTIZADO, fecha=None):
        return Consulta.objects.create(
            productos='Pallets', estado=estado, vendedor=vendedor,
            fecha=fecha or self.hoy,
        )


class AlcanceDashboardTest(BaseDashboardTest):
    def test_el_gerente_ve_la_comparativa_por_empleado(self):
        self.consulta(self.emp_a)
        self.client.force_login(self.gerente)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('metricas', resp.context)
        self.assertIn('Cotizado vs. vendido por empleado', resp.content.decode())

    def test_el_empleado_no_ve_la_comparativa(self):
        self.consulta(self.emp_a)
        self.consulta(self.emp_b)
        self.client.force_login(self.emp_a)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.context.get('metricas'))
        self.assertNotIn('Cotizado vs. vendido por empleado', resp.content.decode())

    def test_el_empleado_no_ve_el_nombre_de_sus_companeros(self):
        self.consulta(self.emp_b)
        self.client.force_login(self.emp_a)
        cuerpo = self.client.get(reverse('dashboard')).content.decode()
        self.assertNotIn('Beto', cuerpo)

    def test_el_reparto_del_empleado_cuenta_solo_lo_suyo(self):
        self.consulta(self.emp_a)
        self.consulta(self.emp_b)
        self.consulta(self.emp_b)
        self.client.force_login(self.emp_a)
        self.assertEqual(self.client.get(reverse('dashboard')).context['reparto']['total'], 1)

    def test_la_evolucion_del_empleado_cuenta_solo_lo_suyo(self):
        self.consulta(self.emp_a)
        self.consulta(self.emp_b)
        self.client.force_login(self.emp_a)
        filas = self.client.get(reverse('dashboard')).context['evolucion']
        self.assertEqual(sum(f['total'] for f in filas), 1)

    def test_el_dashboard_vacio_no_rompe(self):
        self.client.force_login(self.gerente)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['reparto']['total'], 0)

    def test_anonimo_va_al_login(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertIn(reverse('accounts:login'), resp['Location'])


class RepartoPorEstadoTest(BaseDashboardTest):
    def test_porcentajes_sobre_el_total(self):
        for _ in range(5):
            self.consulta(self.emp_a, Consulta.FACTURADO)
        for _ in range(14):
            self.consulta(self.emp_a, Consulta.COTIZADO)
        self.consulta(self.emp_a, Consulta.NO_COMPRA)

        reparto = reparto_por_estado(self.gerente, self.hoy, dias=0)
        self.assertEqual(reparto['total'], 20)
        por_clave = {f['clave']: f for f in reparto['filas']}
        self.assertEqual(por_clave['facturadas']['total'], 5)
        self.assertEqual(por_clave['facturadas']['pct'], 25)
        self.assertEqual(por_clave['activas']['total'], 14)
        self.assertEqual(por_clave['activas']['pct'], 70)
        self.assertEqual(por_clave['perdidas']['pct'], 5)

    def test_sin_consultas_los_porcentajes_son_cero(self):
        reparto = reparto_por_estado(self.gerente, self.hoy, dias=0)
        self.assertEqual(reparto['total'], 0)
        self.assertTrue(all(f['pct'] == 0 for f in reparto['filas']))

    def test_recontactar_cuenta_como_activa(self):
        self.consulta(self.emp_a, Consulta.RECONTACTAR)
        reparto = reparto_por_estado(self.gerente, self.hoy, dias=0)
        por_clave = {f['clave']: f for f in reparto['filas']}
        self.assertEqual(por_clave['activas']['total'], 1)


class PorcentajeVendidoTest(BaseDashboardTest):
    def test_pct_facturado_usa_el_total_no_solo_las_cerradas(self):
        self.consulta(self.emp_a, Consulta.FACTURADO)
        for _ in range(3):
            self.consulta(self.emp_a, Consulta.COTIZADO)

        metricas, totales = calcular_metricas(self.gerente, self.hoy, dias=0)
        suyas = next(m for m in metricas if m.empleado == self.emp_a)
        self.assertEqual(suyas.pct_facturado, 25)   # 1 de 4
        self.assertEqual(suyas.conversion, 100)     # 1 de 1 cerrada
        self.assertEqual(totales['pct_facturado'], 25)

    def test_pct_facturado_es_cero_sin_consultas(self):
        metricas, _ = calcular_metricas(self.gerente, self.hoy, dias=0)
        self.assertEqual(next(m for m in metricas if m.empleado == self.emp_a).pct_facturado, 0)

    def test_detalle_facturado(self):
        self.consulta(self.emp_a, Consulta.FACTURADO)
        self.consulta(self.emp_a)
        metricas, _ = calcular_metricas(self.gerente, self.hoy, dias=0)
        self.assertEqual(
            next(m for m in metricas if m.empleado == self.emp_a).detalle_facturado, '1 de 2')


class VentasDelMesTest(BaseDashboardTest):
    def test_cuenta_solo_las_facturadas_del_mes_en_curso(self):
        self.consulta(self.emp_a, Consulta.FACTURADO, fecha=self.hoy)
        mes_pasado = self.hoy.replace(day=1) - timedelta(days=1)
        self.consulta(self.emp_a, Consulta.FACTURADO, fecha=mes_pasado)
        self.consulta(self.emp_a, Consulta.COTIZADO, fecha=self.hoy)

        metricas, totales = calcular_metricas(self.gerente, self.hoy, dias=0)
        suyas = next(m for m in metricas if m.empleado == self.emp_a)
        self.assertEqual(suyas.ventas_mes, 1)
        self.assertEqual(totales['ventas_mes'], 1)

    def test_es_por_empleado(self):
        self.consulta(self.emp_a, Consulta.FACTURADO)
        self.consulta(self.emp_b, Consulta.FACTURADO)
        self.consulta(self.emp_b, Consulta.FACTURADO)
        metricas, _ = calcular_metricas(self.gerente, self.hoy, dias=0)
        por_emp = {m.empleado: m.ventas_mes for m in metricas}
        self.assertEqual(por_emp[self.emp_a], 1)
        self.assertEqual(por_emp[self.emp_b], 2)


class EvolucionMensualTest(BaseDashboardTest):
    def test_devuelve_la_cantidad_de_meses_pedida_en_orden(self):
        filas = evolucion_mensual(self.gerente, date(2026, 6, 15), cantidad_meses=6)
        self.assertEqual(len(filas), 6)
        self.assertEqual([f['mes'].month for f in filas], [1, 2, 3, 4, 5, 6])
        self.assertEqual(filas[0]['etiqueta'], 'ene 26')
        self.assertEqual(filas[-1]['etiqueta'], 'jun 26')

    def test_cruza_el_cambio_de_anio(self):
        filas = evolucion_mensual(self.gerente, date(2026, 2, 10), cantidad_meses=4)
        self.assertEqual([(f['mes'].year, f['mes'].month) for f in filas],
                         [(2025, 11), (2025, 12), (2026, 1), (2026, 2)])

    def test_los_meses_sin_datos_van_en_cero(self):
        filas = evolucion_mensual(self.gerente, self.hoy, cantidad_meses=6)
        self.assertTrue(all(f['total'] == 0 for f in filas))

    def test_cuenta_totales_y_facturadas_por_mes(self):
        hoy = date(2026, 6, 15)
        self.consulta(self.emp_a, Consulta.FACTURADO, fecha=date(2026, 6, 2))
        self.consulta(self.emp_a, Consulta.COTIZADO, fecha=date(2026, 6, 3))
        self.consulta(self.emp_a, Consulta.COTIZADO, fecha=date(2026, 5, 9))

        filas = {f['mes'].month: f for f in evolucion_mensual(self.gerente, hoy, 6)}
        self.assertEqual((filas[6]['total'], filas[6]['facturadas']), (2, 1))
        self.assertEqual((filas[5]['total'], filas[5]['facturadas']), (1, 0))


class GeometriaGraficoTest(BaseDashboardTest):
    def filas(self, totales, facturadas=None):
        facturadas = facturadas or [0] * len(totales)
        return [{'mes': date(2026, i + 1, 1), 'etiqueta': f'm{i}',
                 'total': t, 'facturadas': f}
                for i, (t, f) in enumerate(zip(totales, facturadas))]

    def test_dos_series_con_leyenda_y_un_solo_eje(self):
        g = grafico_evolucion(self.filas([10, 20, 30], [1, 2, 3]))
        self.assertEqual([s.nombre for s in g.series], ['Consultas', 'Facturadas'])
        # Un solo eje: el mismo tope escala las dos series.
        y_consultas_30 = g.series[0].puntos[2].y
        y_facturadas_30 = None
        g2 = grafico_evolucion(self.filas([30, 30, 30], [30, 30, 30]))
        y_facturadas_30 = g2.series[1].puntos[0].y
        self.assertAlmostEqual(y_consultas_30, y_facturadas_30, places=5)

    def test_el_valor_mas_alto_toca_el_tope_del_plot(self):
        g = grafico_evolucion(self.filas([0, 0, 10]))
        alto = g.series[0].puntos[2].y
        bajo = g.series[0].puntos[0].y
        self.assertLess(alto, bajo)   # menor Y = más arriba en SVG
        self.assertAlmostEqual(bajo, g.base_y, places=5)

    def test_todo_cae_dentro_del_viewbox(self):
        g = grafico_evolucion(self.filas([3, 17, 8, 21, 5, 12], [0, 4, 1, 9, 2, 6]))
        for s in g.series:
            for p in s.puntos:
                self.assertGreaterEqual(p.x, 0)
                self.assertLessEqual(p.x, g.ancho)
                self.assertGreaterEqual(p.y, 0)
                self.assertLessEqual(p.y, g.alto)

    def test_un_solo_mes_se_centra_sin_dividir_por_cero(self):
        g = grafico_evolucion(self.filas([5]))
        self.assertEqual(len(g.series[0].puntos), 1)
        self.assertGreater(g.series[0].puntos[0].x, g.izq)

    def test_todo_en_cero_no_divide_por_cero(self):
        g = grafico_evolucion(self.filas([0, 0, 0]))
        for p in g.series[0].puntos:
            self.assertAlmostEqual(p.y, g.base_y, places=5)

    def test_la_polilinea_tiene_un_par_por_mes(self):
        g = grafico_evolucion(self.filas([1, 2, 3, 4]))
        self.assertEqual(len(g.series[0].polilinea.split(' ')), 4)

    def test_los_ticks_arrancan_en_cero(self):
        g = grafico_evolucion(self.filas([7]))
        self.assertEqual(g.grillas[0][1], 0)

    def test_si_las_series_convergen_solo_una_lleva_rotulo_final(self):
        """Dos rótulos a 9 unidades se pisarían; apilarlos los despega de su línea."""
        g = grafico_evolucion(self.filas([80, 60, 7], [2, 3, 1]))
        consultas, facturadas = g.series
        self.assertLess(abs(consultas.ultimo.y - facturadas.ultimo.y), 12)
        self.assertTrue(consultas.etiquetar_final)     # la serie mayor lo conserva
        self.assertFalse(facturadas.etiquetar_final)   # la menor cae a leyenda + tabla

    def test_si_las_series_estan_separadas_ambas_llevan_rotulo(self):
        g = grafico_evolucion(self.filas([100, 100, 100], [5, 5, 5]))
        self.assertTrue(all(s.etiquetar_final for s in g.series))

    def test_el_rotulo_suprimido_no_sale_en_el_svg(self):
        g = grafico_evolucion(self.filas([80, 60, 7], [2, 3, 1]))
        self.assertEqual(sum(1 for s in g.series if s.etiquetar_final), 1)


class RenderSVGTest(BaseDashboardTest):
    """Regresiones encontradas mirando el dashboard en el navegador."""

    def svg_del_dashboard(self):
        self.consulta(self.emp_a, Consulta.FACTURADO)
        self.consulta(self.emp_a, Consulta.COTIZADO)
        self.client.force_login(self.gerente)
        cuerpo = self.client.get(reverse('dashboard')).content.decode()

        # El navbar también trae <svg> (los chevrones de los desplegables), así
        # que hay que buscar el del gráfico y no el primero de la página: con
        # `index('<svg')` estos tests analizaban un icono y pasaban en vacío.
        for encontrado in re.finditer(r'<svg', cuerpo):
            bloque = cuerpo[encontrado.start():cuerpo.index('</svg>', encontrado.start())]
            if 'polyline' in bloque:
                return bloque
        self.fail('el dashboard no trajo el gráfico de evolución')

    def test_las_coordenadas_no_llevan_coma_decimal(self):
        """Con LANGUAGE_CODE='es-ar' Django escribía x="38,0".

        En SVG eso no es 38.0 sino la lista [38, 0]: cada carácter del texto se
        posiciona por separado y el dibujo se destruye. Lo evita {% localize off %}.
        """
        svg = self.svg_del_dashboard()
        coordenadas = re.findall(r'\b(?:x|y|cx|cy|x1|y1|x2|y2)="([^"]*)"', svg)
        self.assertTrue(coordenadas, 'el SVG no trajo coordenadas')
        con_coma = [c for c in coordenadas if ',' in c]
        self.assertEqual(con_coma, [], f'coordenadas con coma decimal: {con_coma}')

    def test_las_coordenadas_no_arrastran_ruido_de_punto_flotante(self):
        svg = self.svg_del_dashboard()
        for valor in re.findall(r'\b(?:cx|cy|x|y)="([\d.]+)"', svg):
            if '.' in valor:
                self.assertLessEqual(len(valor.split('.')[1]), 1, f'sin redondear: {valor}')

    def test_la_polilinea_usa_punto_decimal(self):
        svg = self.svg_del_dashboard()
        puntos = re.search(r'points="([^"]+)"', svg).group(1)
        for par in puntos.split(' '):
            x, y = par.split(',')
            float(x), float(y)   # revienta si el separador decimal se rompió


class ValorDisplayTest(BaseDashboardTest):
    """El filtro `default` trata al 0 como ausente: un empleado con 0 ventas
    mostraba "0%" en lugar de "0"."""

    def test_cero_ventas_del_mes_se_muestra_como_cero(self):
        self.consulta(self.emp_a, Consulta.FACTURADO)
        self.consulta(self.emp_b, Consulta.COTIZADO)   # aparece con 0 ventas
        self.client.force_login(self.gerente)
        cuerpo = self.client.get(reverse('dashboard')).content.decode()

        seccion = cuerpo[cuerpo.index('Ventas de'):]
        etiquetas = dict(
            e.split(': ', 1) for e in
            re.findall(r'role="meter"[^>]*aria-label="([^"]*)"', seccion)
        )
        self.assertEqual(etiquetas['Ana Alfa'], '1')
        self.assertEqual(etiquetas['Beto Beta'], '0')   # "0", nunca "0%"

    def test_el_reparto_trae_el_porcentaje_ya_formateado(self):
        self.consulta(self.emp_a, Consulta.FACTURADO)
        reparto = reparto_por_estado(self.gerente, self.hoy, dias=0)
        por_clave = {f['clave']: f for f in reparto['filas']}
        self.assertEqual(por_clave['facturadas']['pct_texto'], '100%')
        self.assertEqual(por_clave['perdidas']['pct_texto'], '0%')

    def test_todos_los_meters_reciben_valor_display(self):
        """Si un include no lo pasa, el número sale vacío."""
        self.consulta(self.emp_a, Consulta.FACTURADO)
        self.client.force_login(self.gerente)
        cuerpo = self.client.get(reverse('dashboard')).content.decode()
        meters = re.findall(r'role="meter"[^>]*aria-label="([^"]*)"', cuerpo)
        self.assertTrue(meters)
        for etiqueta in meters:
            self.assertRegex(etiqueta, r':\s*\S+$', f'meter sin valor: {etiqueta!r}')


class PaletaTest(TestCase):
    def test_cada_rol_tiene_relleno_y_pista(self):
        for rol, colores in PALETA.items():
            with self.subTest(rol=rol):
                self.assertIn('relleno', colores)
                self.assertIn('pista', colores)
                for hexa in colores.values():
                    self.assertRegex(hexa, r'^#[0-9a-f]{6}$')

    def test_los_rellenos_son_todos_distintos(self):
        rellenos = [c['relleno'] for c in PALETA.values()]
        self.assertEqual(len(rellenos), len(set(rellenos)))
