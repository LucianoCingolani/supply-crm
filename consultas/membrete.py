"""Las imágenes fijas del PDF de cotización, listas para embeber.

WeasyPrint no resuelve URLs de `{% static %}`: necesita el archivo o los bytes.
Se embeben como data URI, igual que la foto del producto, así el PDF no depende
de que el static esté servido ni de que haya red al generarlo.

Las imágenes son las del modelo que aprobó el gerente, extraídas de su .docx.
"""

import base64
import functools
import mimetypes
import pathlib

from django.conf import settings

DIRECTORIO = pathlib.Path(settings.BASE_DIR) / 'theme' / 'static' / 'img' / 'cotizacion'

MEMBRETE = 'membrete.jpg'
# Las tres tiras de familias de producto que van al pie, en orden de izquierda
# a derecha, tal como están en el modelo.
FAMILIAS = ['familias1.jpeg', 'familias2.jpeg', 'familias3.jpeg']


@functools.lru_cache(maxsize=8)
def data_uri(nombre):
    """El archivo como data URI. Cacheado: son los mismos bytes en cada PDF."""
    ruta = DIRECTORIO / nombre
    if not ruta.is_file():
        return ''
    tipo = mimetypes.guess_type(ruta.name)[0] or 'image/jpeg'
    return f'data:{tipo};base64,{base64.b64encode(ruta.read_bytes()).decode()}'


def contexto():
    """Lo que el template necesita para dibujar membrete y pie."""
    return {
        'img_membrete': data_uri(MEMBRETE),
        'img_familias': [data_uri(n) for n in FAMILIAS],
    }
