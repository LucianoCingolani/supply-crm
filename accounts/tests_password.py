"""Cambio de contraseña obligatorio al primer ingreso."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

PROVISORIA = 'Provisoria123!'
NUEVA = 'MiClaveNueva456!'


class BasePasswordTest(TestCase):
    def crear(self, email='user@test.com', role=None, must_change=True, password=PROVISORIA):
        return User.objects.create_user(
            email, password, first_name='Nom', last_name='Ape',
            role=role or User.EMPLEADO, must_change_password=must_change,
        )

    def login(self, user, password=PROVISORIA):
        self.assertTrue(self.client.login(username=user.email, password=password))


class ForzarCambioTest(BasePasswordTest):
    def test_redirige_a_cambiar_password_desde_cualquier_pagina(self):
        user = self.crear()
        self.login(user)
        destino = reverse('accounts:change_password')
        for nombre in ('dashboard', 'consultas:list', 'clientes:list', 'productos:catalogo'):
            with self.subTest(vista=nombre):
                self.assertRedirects(self.client.get(reverse(nombre)), destino)

    def test_tambien_bloquea_el_admin_de_django(self):
        admin = self.crear('admin@test.com', role=User.ADMIN)
        self.login(admin)
        resp = self.client.get('/admin/')
        self.assertRedirects(resp, reverse('accounts:change_password'),
                             fetch_redirect_response=False)

    def test_puede_ver_la_pagina_de_cambio(self):
        self.login(self.crear())
        self.assertEqual(self.client.get(reverse('accounts:change_password')).status_code, 200)

    def test_puede_cerrar_sesion_sin_cambiarla(self):
        """Si logout estuviera bloqueado, el usuario quedaría encerrado."""
        self.login(self.crear())
        resp = self.client.post(reverse('accounts:logout'))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(self.client.session.get('_auth_user_id'))

    def test_sin_el_flag_navega_normal(self):
        self.login(self.crear(must_change=False))
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_el_anonimo_no_se_ve_afectado(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertIn(reverse('accounts:login'), resp['Location'])


class CambioExitosoTest(BasePasswordTest):
    def test_cambiar_limpia_el_flag_y_deja_navegar(self):
        user = self.crear()
        self.login(user)
        resp = self.client.post(reverse('accounts:change_password'),
                                {'password1': NUEVA, 'password2': NUEVA})
        self.assertRedirects(resp, reverse('dashboard'))

        user.refresh_from_db()
        self.assertFalse(user.must_change_password)
        self.assertTrue(user.check_password(NUEVA))
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_la_sesion_sobrevive_al_cambio(self):
        """Sin update_session_auth_hash el usuario quedaría deslogueado."""
        user = self.crear()
        self.login(user)
        self.client.post(reverse('accounts:change_password'),
                         {'password1': NUEVA, 'password2': NUEVA})
        self.assertEqual(str(user.pk), self.client.session.get('_auth_user_id'))

    def test_puede_entrar_con_la_nueva_y_no_con_la_vieja(self):
        user = self.crear()
        self.login(user)
        self.client.post(reverse('accounts:change_password'),
                         {'password1': NUEVA, 'password2': NUEVA})
        self.client.logout()
        self.assertFalse(self.client.login(username=user.email, password=PROVISORIA))
        self.assertTrue(self.client.login(username=user.email, password=NUEVA))


class ValidacionesTest(BasePasswordTest):
    def _intentar(self, user, **datos):
        self.login(user)
        resp = self.client.post(reverse('accounts:change_password'), datos)
        self.assertEqual(resp.status_code, 200)  # se queda en el form
        user.refresh_from_db()
        self.assertTrue(user.must_change_password)
        return resp

    def test_rechaza_si_no_coinciden(self):
        self._intentar(self.crear(), password1=NUEVA, password2='OtraCosa789!')

    def test_rechaza_contrasena_debil(self):
        user = self.crear()
        self._intentar(user, password1='1234', password2='1234')
        self.assertTrue(user.check_password(PROVISORIA))

    def test_rechaza_repetir_la_provisoria(self):
        """Si no, alcanzaría con reescribirla para limpiar el flag sin elegir nada."""
        self._intentar(self.crear(), password1=PROVISORIA, password2=PROVISORIA)

    def test_en_el_cambio_obligatorio_no_pide_la_actual(self):
        self.login(self.crear())
        form = self.client.get(reverse('accounts:change_password')).context['form']
        self.assertNotIn('password_actual', form.fields)


class CambioVoluntarioTest(BasePasswordTest):
    def test_pide_la_contrasena_actual(self):
        user = self.crear(must_change=False)
        self.login(user)
        form = self.client.get(reverse('accounts:change_password')).context['form']
        self.assertIn('password_actual', form.fields)

    def test_rechaza_si_la_actual_es_incorrecta(self):
        user = self.crear(must_change=False)
        self.login(user)
        resp = self.client.post(reverse('accounts:change_password'), {
            'password_actual': 'equivocada', 'password1': NUEVA, 'password2': NUEVA})
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password(PROVISORIA))

    def test_cambia_con_la_actual_correcta(self):
        user = self.crear(must_change=False)
        self.login(user)
        resp = self.client.post(reverse('accounts:change_password'), {
            'password_actual': PROVISORIA, 'password1': NUEVA, 'password2': NUEVA})
        self.assertRedirects(resp, reverse('dashboard'))
        user.refresh_from_db()
        self.assertTrue(user.check_password(NUEVA))


class GestionDesdeElPanelTest(BasePasswordTest):
    def setUp(self):
        self.gerente = self.crear('gerente@test.com', role=User.GERENTE, must_change=False)
        self.client.force_login(self.gerente)

    def test_crear_usuario_marca_el_flag_por_defecto(self):
        form = self.client.get(reverse('accounts:user_create')).context['form']
        self.assertTrue(form.fields['must_change_password'].initial)

    def test_usuario_creado_con_el_check_debe_cambiarla(self):
        resp = self.client.post(reverse('accounts:user_create'), {
            'email': 'nuevo@test.com', 'first_name': 'N', 'last_name': 'N',
            'role': User.EMPLEADO, 'password1': PROVISORIA, 'password2': PROVISORIA,
            'must_change_password': 'on',
        })
        self.assertRedirects(resp, reverse('accounts:user_list'))
        self.assertTrue(User.objects.get(email='nuevo@test.com').must_change_password)

    def test_usuario_creado_sin_el_check_no_debe_cambiarla(self):
        self.client.post(reverse('accounts:user_create'), {
            'email': 'nuevo2@test.com', 'first_name': 'N', 'last_name': 'N',
            'role': User.EMPLEADO, 'password1': PROVISORIA, 'password2': PROVISORIA,
        })
        self.assertFalse(User.objects.get(email='nuevo2@test.com').must_change_password)

    def test_no_se_puede_crear_un_usuario_con_contrasena_debil(self):
        self.client.post(reverse('accounts:user_create'), {
            'email': 'debil@test.com', 'first_name': 'N', 'last_name': 'N',
            'role': User.EMPLEADO, 'password1': 'abc', 'password2': 'abc',
        })
        self.assertFalse(User.objects.filter(email='debil@test.com').exists())

    def test_resetear_contrasena_fuerza_el_cambio(self):
        otro = self.crear('otro@test.com', must_change=False)
        resp = self.client.post(reverse('accounts:user_password', args=[otro.pk]), {
            'password1': NUEVA, 'password2': NUEVA, 'must_change_password': 'on'})
        self.assertRedirects(resp, reverse('accounts:user_list'))
        otro.refresh_from_db()
        self.assertTrue(otro.must_change_password)
        self.assertTrue(otro.check_password(NUEVA))

    def test_resetear_sin_el_check_no_fuerza_nada(self):
        otro = self.crear('otro@test.com', must_change=False)
        self.client.post(reverse('accounts:user_password', args=[otro.pk]),
                         {'password1': NUEVA, 'password2': NUEVA})
        otro.refresh_from_db()
        self.assertFalse(otro.must_change_password)

    def test_el_reset_valida_la_contrasena(self):
        otro = self.crear('otro@test.com', must_change=False)
        resp = self.client.post(reverse('accounts:user_password', args=[otro.pk]),
                                {'password1': '123', 'password2': '123'})
        self.assertEqual(resp.status_code, 200)
        otro.refresh_from_db()
        self.assertTrue(otro.check_password(PROVISORIA))

    def test_editar_usuario_permite_activar_el_flag(self):
        otro = self.crear('otro@test.com', must_change=False)
        self.client.post(reverse('accounts:user_edit', args=[otro.pk]), {
            'email': otro.email, 'first_name': 'N', 'last_name': 'N',
            'role': User.EMPLEADO, 'is_active': 'on', 'must_change_password': 'on'})
        otro.refresh_from_db()
        self.assertTrue(otro.must_change_password)

    def test_el_gerente_con_flag_no_puede_gestionar_usuarios(self):
        """El middleware tiene prioridad sobre cualquier capacidad."""
        self.gerente.must_change_password = True
        self.gerente.save()
        self.assertRedirects(self.client.get(reverse('accounts:user_list')),
                             reverse('accounts:change_password'))
