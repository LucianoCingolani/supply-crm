"""Importación de la lista de clientes del sistema de facturación.

Los casos replican la suciedad del archivo real: CUIT en dos formatos, DNIs
cargados en la columna del CUIT, entidades HTML sin decodificar, filas sin
identidad y CUITs repetidos.
"""

import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente, normalizar_cuit

User = get_user_model()

ENCABEZADO = [
    'ID Cliente', 'Nombre', 'DNI', 'Razon social', 'CUIT', 'Domicilio',
    'Domicilio fiscal', 'Tipo Doc.', 'Cond. Fiscal', 'Tipo Factura',
    'Provincia', 'Localidad', 'Cod.Postal', 'Email', 'Telefono/s', '',
    'ID Cond. Fiscal', 'ID Tipo Doc.', 'ID Tipo Factura',
]


def fila(id_cliente='', nombre='', dni='', razon='', cuit='', dom_fiscal='',
         cond='', factura='', prov='', loc='', cp='', email='', tel=''):
    f = [''] * 19
    f[0], f[1], f[2], f[3], f[4] = id_cliente, nombre, dni, razon, cuit
    f[6], f[8], f[9] = dom_fiscal, cond, factura
    f[10], f[11], f[12], f[13], f[14] = prov, loc, cp, email, tel
    return f


def excel(filas):
    """Arma un .xlsx en memoria con el layout del export real."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Lista de clientes'
    ws.append(ENCABEZADO)
    ws.append([''] * 19)          # la fila 2 viene en blanco
    for f in filas:
        ws.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class NormalizarCuitTest(TestCase):
    def test_pone_los_guiones_en_el_formato_canonico(self):
        self.assertEqual(normalizar_cuit('20275892859'), '20-27589285-9')

    def test_respeta_el_que_ya_venia_con_guiones(self):
        self.assertEqual(normalizar_cuit('30-53723484-5'), '30-53723484-5')

    def test_los_dos_formatos_convergen(self):
        self.assertEqual(normalizar_cuit('30537234845'), normalizar_cuit('30-53723484-5'))

    def test_deja_pasar_lo_que_no_es_cuit(self):
        self.assertEqual(normalizar_cuit('14263202'), '14263202')
        self.assertEqual(normalizar_cuit(''), '')
        self.assertEqual(normalizar_cuit(None), '')

    def test_el_modelo_normaliza_al_guardar(self):
        c = Cliente.objects.create(razon_social='X', cuit='20275892859')
        c.refresh_from_db()
        self.assertEqual(c.cuit, '20-27589285-9')


class BaseImportarTest(TestCase):
    """Helper compartido. No trae tests, así las subclases no los reejecutan."""

    def importar(self, filas, *extra):
        import os
        import tempfile
        buf = excel(filas)
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            tmp.write(buf.read())
            ruta = tmp.name
        try:
            salida = io.StringIO()
            call_command('importar_clientes', ruta, *extra, stdout=salida)
            return salida.getvalue()
        finally:
            os.unlink(ruta)


class ImportarClientesTest(BaseImportarTest):
    def test_importa_las_columnas_elegidas(self):
        self.importar([fila(
            id_cliente='34', nombre='Maria Ines', dni='21104645',
            razon='Ayala Alberto Dario', cuit='20275892859',
            dom_fiscal='Pellegrini 756', cond='Responsable Inscripto',
            factura='Factura A', prov='Buenos Aires', loc='San Justo',
            cp='1754', email='a@b.com', tel='1132556655',
        )])
        c = Cliente.objects.get()
        self.assertEqual(c.id_facturacion, 34)
        self.assertEqual(c.contacto, 'Maria Ines')
        self.assertEqual(c.dni, '21104645')
        self.assertEqual(c.razon_social, 'Ayala Alberto Dario')
        self.assertEqual(c.cuit, '20-27589285-9')
        self.assertEqual(c.domicilio, 'Pellegrini 756')
        self.assertEqual(c.condicion_fiscal, 'Responsable Inscripto')
        self.assertEqual(c.tipo_factura, 'Factura A')
        self.assertEqual(c.provincia, 'Buenos Aires')
        self.assertEqual(c.localidad, 'San Justo')
        self.assertEqual(c.codigo_postal, '1754')
        self.assertEqual(c.email, 'a@b.com')
        self.assertEqual(c.telefono, '1132556655')

    def test_normaliza_los_dos_formatos_de_cuit(self):
        self.importar([
            fila(id_cliente='1', razon='Uno', cuit='20275892859'),
            fila(id_cliente='2', razon='Dos', cuit='30-53723484-5'),
        ])
        self.assertEqual(
            set(Cliente.objects.values_list('cuit', flat=True)),
            {'20-27589285-9', '30-53723484-5'})

    def test_un_cuit_de_8_digitos_es_en_realidad_un_dni(self):
        self.importar([fila(id_cliente='1', razon='Karina Sarmiento', cuit='24231834')])
        c = Cliente.objects.get()
        self.assertEqual(c.dni, '24231834')
        self.assertEqual(c.cuit, '')

    def test_decodifica_las_entidades_html(self):
        self.importar([fila(id_cliente='1', razon='Los Grobo',
                            cuit='30604456475', dom_fiscal='Ruta Nacional N&#176;5')])
        self.assertEqual(Cliente.objects.get().domicilio, 'Ruta Nacional N°5')

    def test_saltea_las_filas_sin_nombre_ni_cuit(self):
        salida = self.importar([
            fila(id_cliente='1', razon='Válido', cuit='30604456475'),
            fila(id_cliente='2', cond='Responsable Inscripto'),   # sin identidad
        ])
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertIn('sin nombre ni CUIT    : 1', salida)

    def test_usa_el_contacto_como_razon_social_si_falta(self):
        self.importar([fila(id_cliente='1', nombre='Juan Perez', cuit='20275892859')])
        self.assertEqual(Cliente.objects.get().razon_social, 'Juan Perez')

    def test_rescata_la_fila_cuyo_unico_dato_es_un_dni_en_la_columna_cuit(self):
        """3 filas del archivo real: sin razón social y con un DNI donde va el CUIT."""
        self.importar([fila(id_cliente='1', cuit='14263202')])
        c = Cliente.objects.get()
        self.assertEqual(c.dni, '14263202')
        self.assertEqual(c.cuit, '')
        self.assertEqual(c.razon_social, '14263202')

    def test_une_las_filas_con_el_mismo_cuit(self):
        """El facturador tenía 22 CUITs repetidos: la primera fila manda y las
        siguientes solo completan lo que esté vacío."""
        salida = self.importar([
            fila(id_cliente='1', razon='Empresa SA', cuit='30604456475', prov='Buenos Aires'),
            fila(id_cliente='2', razon='Empresa S.A.', cuit='30-60445647-5',
                 tel='1122334455', loc='San Justo'),
        ])
        self.assertEqual(Cliente.objects.count(), 1)
        c = Cliente.objects.get()
        self.assertEqual(c.razon_social, 'Empresa SA')     # la primera gana
        self.assertEqual(c.provincia, 'Buenos Aires')
        self.assertEqual(c.telefono, '1122334455')         # la segunda completa
        self.assertEqual(c.localidad, 'San Justo')
        self.assertIn('unidas por CUIT igual : 1', salida)

    def test_descarta_emails_invalidos_sin_perder_la_fila(self):
        self.importar([fila(id_cliente='1', razon='X', cuit='30604456475',
                            email='yolanda,jimenez1967@gmail')])
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertEqual(Cliente.objects.get().email, '')

    def test_trunca_lo_que_excede_el_campo(self):
        self.importar([fila(id_cliente='1', razon='R', cuit='30604456475',
                            loc='L' * 250)])
        self.assertEqual(len(Cliente.objects.get().localidad), 100)


class ReimportarTest(BaseImportarTest):
    """Se puede volver a correr con una exportación más nueva."""

    def test_reimportar_no_duplica(self):
        filas = [fila(id_cliente='34', razon='Ayala', cuit='20275892859')]
        self.importar(filas)
        self.importar(filas)
        self.assertEqual(Cliente.objects.count(), 1)

    def test_reimportar_actualiza_por_id_de_facturacion(self):
        self.importar([fila(id_cliente='34', razon='Ayala', cuit='20275892859')])
        self.importar([fila(id_cliente='34', razon='Ayala Alberto Dario',
                            cuit='20275892859', tel='1132556655')])
        c = Cliente.objects.get()
        self.assertEqual(c.razon_social, 'Ayala Alberto Dario')
        self.assertEqual(c.telefono, '1132556655')

    def test_matchea_por_cuit_si_el_cliente_no_tenia_id(self):
        Cliente.objects.create(razon_social='Cargado a mano', cuit='30-60445647-5')
        self.importar([fila(id_cliente='7', razon='Los Grobo', cuit='30604456475')])
        self.assertEqual(Cliente.objects.count(), 1)
        c = Cliente.objects.get()
        self.assertEqual(c.id_facturacion, 7)
        self.assertEqual(c.razon_social, 'Los Grobo')

    def test_no_pisa_las_consultas_del_cliente(self):
        from consultas.models import Consulta
        vendedor = User.objects.create_user('v@test.com', 'x', role=User.EMPLEADO)
        cliente = Cliente.objects.create(razon_social='Los Grobo', cuit='30-60445647-5')
        Consulta.objects.create(productos='Pallets', cliente=cliente, vendedor=vendedor)

        self.importar([fila(id_cliente='7', razon='Los Grobo SA', cuit='30604456475')])
        self.assertEqual(Consulta.objects.count(), 1)
        self.assertEqual(Consulta.objects.get().cliente_id, cliente.pk)

    def test_dry_run_no_escribe(self):
        salida = self.importar(
            [fila(id_cliente='1', razon='X', cuit='30604456475')], '--dry-run')
        self.assertEqual(Cliente.objects.count(), 0)
        self.assertIn('SIMULACIÓN', salida)
        self.assertIn('clientes nuevos       : 1', salida)


class ListaClientesTest(TestCase):
    """Con 3900 clientes, paginar y buscar bien dejan de ser opcionales."""

    @classmethod
    def setUpTestData(cls):
        cls.gerente = User.objects.create_user(
            'g@test.com', 'x', first_name='G', last_name='G', role=User.GERENTE)
        Cliente.objects.bulk_create([
            Cliente(razon_social=f'Empresa {i:03d}', cuit=normalizar_cuit(f'30{i:08d}5'))
            for i in range(120)
        ])
        Cliente.objects.create(razon_social='Los Grobo', cuit='30-60445647-5',
                               localidad='Carlos Casares', provincia='Buenos Aires',
                               dni='', contacto='Ana')

    def setUp(self):
        self.client.force_login(self.gerente)

    def test_pagina_los_resultados(self):
        from clientes.views import ClienteListView
        resp = self.client.get(reverse('clientes:list'))
        self.assertEqual(len(resp.context['clientes']), ClienteListView.POR_PAGINA)
        self.assertEqual(resp.context['total'], 121)
        self.assertTrue(resp.context['pagina'].has_next())

    def test_la_segunda_pagina_trae_otros_clientes(self):
        primera = self.client.get(reverse('clientes:list')).context['clientes']
        segunda = self.client.get(reverse('clientes:list'), {'pagina': 2}).context['clientes']
        self.assertFalse({c.pk for c in primera} & {c.pk for c in segunda})

    def test_una_pagina_invalida_no_rompe(self):
        resp = self.client.get(reverse('clientes:list'), {'pagina': 'ninguna'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['pagina'].number, 1)

    def test_encuentra_el_cuit_pegado_sin_guiones(self):
        """El facturador los exporta sin guiones; guardados quedan con guiones."""
        resp = self.client.get(reverse('clientes:list'), {'q': '30604456475'})
        self.assertEqual([c.razon_social for c in resp.context['clientes']], ['Los Grobo'])

    def test_encuentra_el_cuit_con_guiones(self):
        resp = self.client.get(reverse('clientes:list'), {'q': '30-60445647-5'})
        self.assertEqual([c.razon_social for c in resp.context['clientes']], ['Los Grobo'])

    def test_busca_por_localidad_y_provincia(self):
        for termino in ('Carlos Casares', 'Buenos Aires'):
            with self.subTest(termino=termino):
                resp = self.client.get(reverse('clientes:list'), {'q': termino})
                self.assertIn('Los Grobo', [c.razon_social for c in resp.context['clientes']])

    def test_el_autocomplete_encuentra_el_cuit_sin_guiones(self):
        resp = self.client.get(reverse('clientes:search'), {'q': '30604456475'})
        self.assertEqual([c['razon_social'] for c in resp.json()], ['Los Grobo'])

    def test_la_busqueda_se_mantiene_al_paginar(self):
        resp = self.client.get(reverse('clientes:list'), {'q': 'Empresa'})
        self.assertEqual(resp.context['total'], 120)
        self.assertContains(resp, 'q=Empresa&amp;pagina=2')


class AsignarCarteraTest(TestCase):
    """El Gerente reparte la cartera; el vendedor trabaja lo que le tocó."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user('ad@test.com', 'x', first_name='Ana',
                                             last_name='Admin', role=User.ADMIN)
        cls.gerente = User.objects.create_user('g@test.com', 'x', first_name='Gaby',
                                               last_name='Gerente', role=User.GERENTE)
        cls.emp_a = User.objects.create_user('a@test.com', 'x', first_name='Ana',
                                             last_name='Alfa', role=User.EMPLEADO)
        cls.emp_b = User.objects.create_user('b@test.com', 'x', first_name='Beto',
                                             last_name='Beta', role=User.EMPLEADO)

    def setUp(self):
        self.c1 = Cliente.objects.create(razon_social='Uno', cuit='30-11111111-1')
        self.c2 = Cliente.objects.create(razon_social='Dos', cuit='30-22222222-2')
        self.c3 = Cliente.objects.create(razon_social='Tres', cuit='30-33333333-3')

    def asignar(self, ids, vendedor):
        return self.client.post(reverse('clientes:asignar'),
                                {'cliente': ids, 'vendedor': vendedor})

    # ── permisos ──────────────────────────────────────────────────

    def test_el_empleado_no_puede_asignar(self):
        self.client.force_login(self.emp_a)
        resp = self.asignar([self.c1.pk], self.emp_a.pk)
        self.assertRedirects(resp, reverse('dashboard'))
        self.c1.refresh_from_db()
        self.assertIsNone(self.c1.vendedor)

    def test_el_empleado_no_ve_los_checkboxes(self):
        self.c1.vendedor = self.emp_a
        self.c1.save()
        self.client.force_login(self.emp_a)
        resp = self.client.get(reverse('clientes:list'))
        self.assertFalse(resp.context['puede_asignar'])
        self.assertNotContains(resp, 'name="cliente"')

    def test_el_gerente_ve_los_checkboxes(self):
        self.client.force_login(self.gerente)
        resp = self.client.get(reverse('clientes:list'))
        self.assertTrue(resp.context['puede_asignar'])
        self.assertContains(resp, 'name="cliente"')

    # ── asignación ────────────────────────────────────────────────

    def test_asigna_varios_de_una(self):
        self.client.force_login(self.gerente)
        self.asignar([self.c1.pk, self.c3.pk], self.emp_a.pk)
        self.c1.refresh_from_db(); self.c2.refresh_from_db(); self.c3.refresh_from_db()
        self.assertEqual(self.c1.vendedor, self.emp_a)
        self.assertEqual(self.c3.vendedor, self.emp_a)
        self.assertIsNone(self.c2.vendedor)

    def test_reasigna_uno_que_ya_tenia_vendedor(self):
        self.c1.vendedor = self.emp_a
        self.c1.save()
        self.client.force_login(self.gerente)
        self.asignar([self.c1.pk], self.emp_b.pk)
        self.c1.refresh_from_db()
        self.assertEqual(self.c1.vendedor, self.emp_b)

    def test_puede_quitar_la_asignacion(self):
        self.c1.vendedor = self.emp_a
        self.c1.save()
        self.client.force_login(self.gerente)
        self.asignar([self.c1.pk], 'ninguno')
        self.c1.refresh_from_db()
        self.assertIsNone(self.c1.vendedor)

    def test_sin_seleccionar_nada_avisa(self):
        self.client.force_login(self.gerente)
        resp = self.client.post(reverse('clientes:asignar'), {'vendedor': self.emp_a.pk})
        self.assertRedirects(resp, reverse('clientes:list'))
        self.assertIsNone(Cliente.objects.get(pk=self.c1.pk).vendedor)

    def test_un_vendedor_invalido_no_asigna_nada(self):
        self.client.force_login(self.gerente)
        self.asignar([self.c1.pk], 'cualquiera')
        self.c1.refresh_from_db()
        self.assertIsNone(self.c1.vendedor)

    def test_el_gerente_no_puede_asignarle_a_un_admin(self):
        self.client.force_login(self.gerente)
        self.asignar([self.c1.pk], self.admin.pk)
        self.c1.refresh_from_db()
        self.assertIsNone(self.c1.vendedor)

    def test_el_admin_si_puede_asignarse_a_si_mismo(self):
        self.client.force_login(self.admin)
        self.asignar([self.c1.pk], self.admin.pk)
        self.c1.refresh_from_db()
        self.assertEqual(self.c1.vendedor, self.admin)

    def test_vuelve_al_filtro_desde_el_que_se_asigno(self):
        self.client.force_login(self.gerente)
        destino = reverse('clientes:list') + '?vendedor=sin'
        resp = self.client.post(reverse('clientes:asignar'), {
            'cliente': [self.c1.pk], 'vendedor': self.emp_a.pk, 'volver': destino})
        self.assertRedirects(resp, destino)

    # ── filtro por vendedor ───────────────────────────────────────

    def test_filtra_los_sin_asignar(self):
        self.c1.vendedor = self.emp_a
        self.c1.save()
        self.client.force_login(self.gerente)
        resp = self.client.get(reverse('clientes:list'), {'vendedor': 'sin'})
        self.assertEqual({c.razon_social for c in resp.context['clientes']}, {'Dos', 'Tres'})
        self.assertEqual(resp.context['sin_asignar_total'], 2)

    def test_filtra_por_un_vendedor(self):
        self.c1.vendedor = self.emp_a
        self.c1.save()
        self.client.force_login(self.gerente)
        resp = self.client.get(reverse('clientes:list'), {'vendedor': self.emp_a.pk})
        self.assertEqual([c.razon_social for c in resp.context['clientes']], ['Uno'])

    def test_el_empleado_no_puede_filtrar_por_otro_vendedor(self):
        self.c1.vendedor = self.emp_a
        self.c2.vendedor = self.emp_b
        self.c1.save(); self.c2.save()
        self.client.force_login(self.emp_a)
        resp = self.client.get(reverse('clientes:list'), {'vendedor': self.emp_b.pk})
        self.assertEqual([c.razon_social for c in resp.context['clientes']], ['Uno'])


class ImportadorNoPisaAsignacionTest(BaseImportarTest):
    def test_reimportar_conserva_el_vendedor(self):
        """La lista del facturador no trae vendedor: no debe borrar la cartera."""
        vendedor = User.objects.create_user('v@test.com', 'x', role=User.EMPLEADO)
        self.importar([fila(id_cliente='7', razon='Los Grobo', cuit='30604456475')])
        cliente = Cliente.objects.get()
        cliente.vendedor = vendedor
        cliente.save()

        self.importar([fila(id_cliente='7', razon='Los Grobo SA', cuit='30604456475')])
        cliente.refresh_from_db()
        self.assertEqual(cliente.razon_social, 'Los Grobo SA')   # se actualiza
        self.assertEqual(cliente.vendedor, vendedor)             # pero no se pisa


class UbicacionTest(TestCase):
    def test_arma_localidad_y_provincia(self):
        c = Cliente(razon_social='X', localidad='San Justo', provincia='Buenos Aires')
        self.assertEqual(c.ubicacion, 'San Justo, Buenos Aires')

    def test_tolera_los_campos_vacios(self):
        self.assertEqual(Cliente(razon_social='X', provincia='Salta').ubicacion, 'Salta')
        self.assertEqual(Cliente(razon_social='X').ubicacion, '')
