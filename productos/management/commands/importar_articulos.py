from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand

from productos.models import Producto


def _limpiar(valor):
    if valor is None:
        return ''
    return str(valor).replace('­', '').strip()  # elimina soft-hyphen y espacios


class Command(BaseCommand):
    help = 'Importa o actualiza el catálogo de productos desde el Excel de Enexpro'

    def add_arguments(self, parser):
        parser.add_argument('archivo', type=str, help='Ruta al archivo .xlsx exportado de Enexpro')

    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError:
            self.stderr.write('Instalá openpyxl: pip install openpyxl')
            return

        wb = openpyxl.load_workbook(options['archivo'])
        ws = wb.active

        creados = actualizados = saltados = 0

        for row in ws.iter_rows(values_only=True, min_row=3):
            codigo_raw, nombre_raw, cat_raw, subcat_raw, precio_raw = (row + (None,) * 5)[:5]

            codigo = _limpiar(codigo_raw)
            nombre = _limpiar(nombre_raw)

            if not codigo or not nombre:
                saltados += 1
                continue

            precio = None
            if precio_raw is not None:
                try:
                    val = Decimal(str(precio_raw))
                    if val > 0:
                        precio = val
                except InvalidOperation:
                    pass

            _, created = Producto.objects.update_or_create(
                codigo=codigo,
                defaults={
                    'nombre': nombre,
                    'categoria': _limpiar(cat_raw),
                    'subcategoria': _limpiar(subcat_raw),
                    'precio': precio,
                },
            )

            if created:
                creados += 1
            else:
                actualizados += 1

        self.stdout.write(self.style.SUCCESS(
            f'Importación completada: {creados} creados, {actualizados} actualizados, {saltados} saltados.'
        ))
