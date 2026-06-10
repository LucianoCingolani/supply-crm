import re
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand

from productos.models import Producto

MESES = {'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,
         'julio':7,'agosto':8,'septiembre':9,'octubre':10,'noviembre':11,'diciembre':12}


def _get_image(para):
    """Devuelve (bytes, mime_type) si el párrafo tiene imagen embebida, o None."""
    xml = para._element.xml
    if '<w:drawing' not in xml and '<v:imagedata' not in xml:
        return None
    rids = re.findall(r'r:embed="(rId\d+)"', xml) or re.findall(r'r:id="(rId\d+)"', xml)
    for rid in rids:
        try:
            part = para.part.rels[rid].target_part
            ct = part.content_type  # e.g. 'image/png' or 'image/jpeg'
            return bytes(part.blob), ct
        except (KeyError, AttributeError):
            continue
    return None


def _limpiar_precio(texto):
    """Extrae valor numérico de 'Precio unitario: $1.181.950 + IVA'."""
    m = re.search(r'[\$u\$s]?\s*([\d.,]+)', texto.replace('‌', ''))
    if not m:
        return None
    raw = m.group(1).replace('.', '').replace(',', '.')
    try:
        val = Decimal(raw)
        return val if val > 0 else None
    except InvalidOperation:
        return None


def _limpiar_codigo(texto):
    texto = texto.replace('Código', '').replace('Codigo', '').replace('Código', '').strip()
    texto = texto.lstrip(':').strip()
    # quitar aclaraciones entre paréntesis al final  ej: "C259  (Bandeja de pan)"
    texto = re.sub(r'\s*\(.*\)\s*$', '', texto).strip()
    return texto[:50]


class Command(BaseCommand):
    help = 'Importa productos desde un Word de fichas técnicas (ej: BANCO DE TRABAJOS.docx)'

    def add_arguments(self, parser):
        parser.add_argument('archivo', type=str, help='Ruta al archivo .docx')
        parser.add_argument('--categoria', type=str, default='',
                            help='Categoría a asignar a todos los productos (ej: ARMARIOS / BANCOS / BASTIDORES)')

    def handle(self, *args, **options):
        try:
            from docx import Document
        except ImportError:
            self.stderr.write('Instalá python-docx: pip install python-docx')
            return

        categoria = options['categoria']
        doc = Document(options['archivo'])
        paragraphs = doc.paragraphs

        # ── parsear bloques: [IMG] → nombre → código → specs → precio ──
        productos = []
        i = 0
        while i < len(paragraphs):
            img = _get_image(paragraphs[i])
            if img is None:
                i += 1
                continue

            bloque = {'foto': img[0], 'foto_tipo': img[1], 'specs': []}
            i += 1

            # saltar blancos
            while i < len(paragraphs) and not paragraphs[i].text.strip():
                i += 1

            # nombre
            if i < len(paragraphs):
                bloque['nombre'] = paragraphs[i].text.strip().rstrip(':')
                i += 1

            # código (primera línea que lo mencione)
            while i < len(paragraphs) and not paragraphs[i].text.strip():
                i += 1
            if i < len(paragraphs) and re.search(r'[Cc][oó]digo', paragraphs[i].text):
                bloque['codigo'] = _limpiar_codigo(paragraphs[i].text)
                i += 1

            # specs hasta precio o siguiente imagen
            while i < len(paragraphs):
                if _get_image(paragraphs[i]) is not None:
                    break
                txt = paragraphs[i].text.strip()
                if re.search(r'[Pp]recio unitario', txt):
                    bloque['precio'] = _limpiar_precio(txt)
                    i += 1
                    break
                if txt:
                    bloque['specs'].append(txt)
                i += 1

            if bloque.get('codigo') and bloque.get('nombre'):
                productos.append(bloque)

        self.stdout.write(f'Productos encontrados: {len(productos)}')

        creados = actualizados = 0
        for b in productos:
            specs_text = '\n'.join(b['specs'])
            _, created = Producto.objects.update_or_create(
                codigo=b['codigo'],
                defaults={
                    'nombre': b['nombre'],
                    'categoria': categoria,
                    'especificaciones': specs_text,
                    'precio': b.get('precio'),
                    'foto': b['foto'],
                    'foto_tipo': b['foto_tipo'],
                },
            )
            if created:
                creados += 1
                self.stdout.write(f'  + {b["codigo"]} — {b["nombre"][:50]}')
            else:
                actualizados += 1

        self.stdout.write(self.style.SUCCESS(
            f'Listo: {creados} creados, {actualizados} actualizados.'
        ))
