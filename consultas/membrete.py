"""El membrete del PDF de cotización, listo para embeber.

WeasyPrint no resuelve URLs de `{% static %}`: necesita el archivo o los bytes.
Se embebe como data URI, igual que la foto del producto, así el PDF no depende
de que el static esté servido ni de que haya red al generarlo.

Es la imagen que usa la empresa, con la marca, el CUIT, la dirección y los tres
sitios: el documento no dibuja un logo propio.
"""

import base64
import functools
import mimetypes
import pathlib

from django.conf import settings

DIRECTORIO = pathlib.Path(settings.BASE_DIR) / 'theme' / 'static' / 'img' / 'cotizacion'

MEMBRETE = 'membrete.jpg'


@functools.lru_cache(maxsize=8)
def data_uri(nombre):
    """El archivo como data URI. Cacheado: son los mismos bytes en cada PDF."""
    ruta = DIRECTORIO / nombre
    if not ruta.is_file():
        return ''
    tipo = mimetypes.guess_type(ruta.name)[0] or 'image/jpeg'
    return f'data:{tipo};base64,{base64.b64encode(ruta.read_bytes()).decode()}'


def contexto():
    """Lo que el template necesita para dibujar el membrete."""
    return {'img_membrete': data_uri(MEMBRETE)}
