"""Tests del panel del equipo: acceso, métricas y cálculo de consultas frías."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from consultas.models import Consulta, SeguimientoLog
from reportes.metricas import UMBRAL_FRIA, calcular_metricas, consultas_frias

User = get_user_model()


class PanelEquipoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hoy = timezone.localdate()
        cls.admin = User.objects.create_user(
            'admin@test.com', 'x', first_name='Ana', last_name='Admin', role=User.ADMIN)
        cls.gerente = User.objects.create_user(
            'gerente@test.com', 'x', first_name='Gaby', last_name='Gerente', role=User.GERENTE)
        cls.emp = User.objects.create_user(
            'emp@test.com', 'x', first_name='Emi', last_name='Empleado', role=User.EMPLEADO)

    def crear_consulta(self, vendedor, estado=Consulta.COTIZADO, dias_atras=0, creada_hace=None):
        consulta = Consulta.objects.create(
            productos='Pallets', estado=estado, vendedor=vendedor,
            fecha=self.hoy - timedelta(days=dias_atras),
        )
        if creada_hace is not None:
            nuevo = timezone.now() - timedelta(days=creada_hace)
            Consulta.objects.filter(pk=consulta.pk).update(created_at=nuevo)
            consulta.refresh_from_db()
        return consulta

    # ── Acceso ────────────────────────────────────────────────────

    def test_empleado_no_entra_al_panel(self):
        self.client.force_login(self.emp)
        self.assertRedirects(self.client.get(reverse('reportes:equipo')), reverse('dashboard'))
        self.assertRedirects(
            self.client.get(reverse('reportes:empleado', args=[self.emp.pk])),
            reverse('dashboard'))

    def test_admin_y_gerente_entran(self):
        for user in (self.admin, self.gerente):
            with self.subTest(rol=user.role):
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse('reportes:equipo')).status_code, 200)

    def test_anonimo_va_al_login(self):
        resp = self.client.get(reverse('reportes:equipo'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('accounts:login'), resp['Location'])

    def test_gerente_no_ve_la_ficha_de_un_admin(self):
        self.client.force_login(self.gerente)
        self.assertEqual(
            self.client.get(reverse('reportes:empleado', args=[self.admin.pk])).status_code, 404)

    def test_gerente_no_ve_admins_en_la_tabla(self):
        self.client.force_login(self.gerente)
        resp = self.client.get(reverse('reportes:equipo'))
        emails = {m.empleado.email for m in resp.context['metricas']}
        self.assertNotIn(self.admin.email, emails)
        self.assertIn(self.emp.email, emails)

    # ── Métricas ──────────────────────────────────────────────────

    def test_cuenta_por_estado_y_conversion(self):
        for _ in range(3):
            self.crear_consulta(self.emp, Consulta.FACTURADO)
        self.crear_consulta(self.emp, Consulta.NO_COMPRA)
        self.crear_consulta(self.emp, Consulta.COTIZADO)

        metricas, totales = calcular_metricas(self.admin, self.hoy, dias=90)
        suyas = next(m for m in metricas if m.empleado == self.emp)

        self.assertEqual(suyas.nuevas, 5)
        self.assertEqual(suyas.facturadas, 3)
        self.assertEqual(suyas.perdidas, 1)
        self.assertEqual(suyas.activas, 1)
        self.assertEqual(suyas.conversion, 75)  # 3 de 4 cerradas
        self.assertEqual(totales['facturadas'], 3)

    def test_empleado_inactivo_no_aporta_a_la_cartera(self):
        self.crear_consulta(self.emp, creada_hace=200)
        self.emp.is_active = False
        self.emp.save()
        _, totales = calcular_metricas(self.admin, self.hoy, dias=0)
        self.assertEqual(totales['activas'], 0)
        self.assertEqual(totales['frias'], 0)

    def test_conversion_es_none_sin_consultas_cerradas(self):
        self.crear_consulta(self.emp, Consulta.COTIZADO)
        metricas, _ = calcular_metricas(self.admin, self.hoy, dias=90)
        suyas = next(m for m in metricas if m.empleado == self.emp)
        self.assertIsNone(suyas.conversion)

    def test_el_periodo_recorta_las_consultas(self):
        self.crear_consulta(self.emp, dias_atras=5)
        self.crear_consulta(self.emp, dias_atras=200)

        metricas, _ = calcular_metricas(self.admin, self.hoy, dias=30)
        self.assertEqual(next(m for m in metricas if m.empleado == self.emp).nuevas, 1)

        metricas, _ = calcular_metricas(self.admin, self.hoy, dias=0)  # todo
        self.assertEqual(next(m for m in metricas if m.empleado == self.emp).nuevas, 2)

    def test_activas_y_frias_no_dependen_del_periodo(self):
        """La cartera es estado actual: acortar el período no debe esconder las frías."""
        self.crear_consulta(self.emp, dias_atras=200, creada_hace=200)

        for dias in (30, 90, 365, 0):
            with self.subTest(dias=dias):
                metricas, totales = calcular_metricas(self.admin, self.hoy, dias=dias)
                suyas = next(m for m in metricas if m.empleado == self.emp)
                self.assertEqual(suyas.activas, 1)
                self.assertEqual(suyas.frias, 1)
                self.assertEqual(totales['frias'], 1)

        # Pero la producción sí se recorta.
        metricas, _ = calcular_metricas(self.admin, self.hoy, dias=30)
        self.assertEqual(next(m for m in metricas if m.empleado == self.emp).nuevas, 0)

    def test_consulta_vieja_sin_seguimiento_cuenta_como_fria(self):
        self.crear_consulta(self.emp, creada_hace=UMBRAL_FRIA + 10)
        metricas, totales = calcular_metricas(self.admin, self.hoy, dias=0)
        suyas = next(m for m in metricas if m.empleado == self.emp)
        self.assertEqual(suyas.frias, 1)
        self.assertEqual(totales['frias'], 1)

    def test_un_seguimiento_reciente_descongela_la_consulta(self):
        consulta = self.crear_consulta(self.emp, creada_hace=UMBRAL_FRIA + 10)
        SeguimientoLog.objects.create(consulta=consulta, user=self.emp, nota='Llamé hoy')

        metricas, _ = calcular_metricas(self.admin, self.hoy, dias=0)
        suyas = next(m for m in metricas if m.empleado == self.emp)
        self.assertEqual(suyas.frias, 0)
        self.assertEqual(suyas.seguimientos, 1)

    def test_las_consultas_cerradas_nunca_son_frias(self):
        self.crear_consulta(self.emp, Consulta.FACTURADO, creada_hace=200)
        self.crear_consulta(self.emp, Consulta.NO_COMPRA, creada_hace=200)
        metricas, _ = calcular_metricas(self.admin, self.hoy, dias=0)
        suyas = next(m for m in metricas if m.empleado == self.emp)
        self.assertEqual(suyas.frias, 0)
        self.assertEqual(suyas.activas, 0)

    def test_empleado_sin_nada_aparece_en_cero(self):
        metricas, _ = calcular_metricas(self.admin, self.hoy, dias=90)
        suyas = next(m for m in metricas if m.empleado == self.emp)
        self.assertEqual(suyas.nuevas, 0)
        self.assertTrue(suyas.sin_actividad_registrada)

    def test_los_empleados_con_mas_frias_van_primero(self):
        otro = User.objects.create_user(
            'otro@test.com', 'x', first_name='Otro', last_name='Zeta', role=User.EMPLEADO)
        self.crear_consulta(otro, creada_hace=200)
        self.crear_consulta(otro, creada_hace=200)
        self.crear_consulta(self.emp, creada_hace=200)

        metricas, _ = calcular_metricas(self.admin, self.hoy, dias=0)
        self.assertEqual(metricas[0].empleado, otro)

    def test_empleado_inactivo_queda_fuera(self):
        self.crear_consulta(self.emp)
        self.emp.is_active = False
        self.emp.save()
        metricas, totales = calcular_metricas(self.admin, self.hoy, dias=90)
        self.assertNotIn(self.emp, [m.empleado for m in metricas])
        self.assertEqual(totales['nuevas'], 0)

    # ── Consultas frías ───────────────────────────────────────────

    def test_frias_ordenadas_de_mas_vieja_a_mas_nueva(self):
        vieja = self.crear_consulta(self.emp, creada_hace=120)
        media = self.crear_consulta(self.emp, creada_hace=60)
        nueva = self.crear_consulta(self.emp, creada_hace=2)

        frias = consultas_frias(self.admin, self.hoy)
        self.assertEqual([c.pk for c in frias], [vieja.pk, media.pk, nueva.pk])
        self.assertEqual(frias[0].dias_sin_movimiento, 120)
        self.assertEqual(frias[2].dias_sin_movimiento, 2)

    def test_frias_se_pueden_filtrar_por_vendedor(self):
        otro = User.objects.create_user('otro@test.com', 'x', role=User.EMPLEADO)
        mia = self.crear_consulta(self.emp, creada_hace=50)
        self.crear_consulta(otro, creada_hace=50)

        frias = consultas_frias(self.admin, self.hoy, vendedor=self.emp)
        self.assertEqual([c.pk for c in frias], [mia.pk])

    def test_el_limite_recorta_el_listado(self):
        for _ in range(5):
            self.crear_consulta(self.emp, creada_hace=50)
        self.assertEqual(len(consultas_frias(self.admin, self.hoy, limite=3)), 3)

    def test_la_ficha_topea_las_frias_y_avisa_que_hay_mas(self):
        from reportes.views import DetalleEmpleadoView
        total = DetalleEmpleadoView.MAX_FRIAS + 4
        for _ in range(total):
            self.crear_consulta(self.emp, creada_hace=50)

        self.client.force_login(self.admin)
        resp = self.client.get(reverse('reportes:empleado', args=[self.emp.pk]))
        self.assertEqual(len(resp.context['frias']), DetalleEmpleadoView.MAX_FRIAS)
        self.assertEqual(resp.context['total_activas'], total)
        self.assertTrue(resp.context['hay_mas_frias'])


class FiltroVendedorTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gerente = User.objects.create_user(
            'g@test.com', 'x', first_name='G', last_name='G', role=User.GERENTE)
        cls.emp_a = User.objects.create_user(
            'a@test.com', 'x', first_name='A', last_name='A', role=User.EMPLEADO)
        cls.emp_b = User.objects.create_user(
            'b@test.com', 'x', first_name='B', last_name='B', role=User.EMPLEADO)
        cls.con_a = Consulta.objects.create(productos='X', vendedor=cls.emp_a)
        cls.con_b = Consulta.objects.create(productos='Y', vendedor=cls.emp_b)

    def test_el_gerente_puede_filtrar_por_vendedor(self):
        self.client.force_login(self.gerente)
        resp = self.client.get(reverse('consultas:list'), {'vendedor': self.emp_a.pk})
        self.assertEqual([c.pk for c in resp.context['consultas']], [self.con_a.pk])

    def test_el_selector_solo_lista_vendedores_con_consultas(self):
        self.client.force_login(self.gerente)
        resp = self.client.get(reverse('consultas:list'))
        self.assertEqual(
            {v.pk for v in resp.context['vendedores']}, {self.emp_a.pk, self.emp_b.pk})

    def test_un_vendedor_invalido_no_rompe_la_lista(self):
        self.client.force_login(self.gerente)
        resp = self.client.get(reverse('consultas:list'), {'vendedor': 'undefined'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['consultas']), 2)

    def test_el_empleado_no_puede_espiar_via_querystring(self):
        self.client.force_login(self.emp_a)
        resp = self.client.get(reverse('consultas:list'), {'vendedor': self.emp_b.pk})
        self.assertEqual([c.pk for c in resp.context['consultas']], [self.con_a.pk])
        self.assertIsNone(resp.context['vendedores'])
