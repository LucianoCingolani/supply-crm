"""Ayudas del navbar: saber en qué sección estamos y qué items mostrar."""

from django import template
from django.urls import reverse

register = template.Library()

CLASES_BASE = 'px-3 py-2 text-sm font-medium rounded-md'
CLASES_ACTIVA = 'bg-blue-50 text-blue-700'
CLASES_INACTIVA = 'text-gray-600 hover:text-blue-600 hover:bg-gray-50'

# Los items que van agrupados bajo "Gestión", en orden. Una sola fuente: de acá
# salen tanto el contenido del menú como el resaltado del botón que lo abre.
GESTION = {
    'precios': ('Precios', 'productos:precios'),
    'equipo': ('Equipo', 'reportes:equipo'),
    'usuarios': ('Usuarios', 'accounts:user_list'),
}
CLAVES_GESTION = tuple(GESTION)


def _seccion(request):
    """La sección del navbar a la que corresponde la URL actual.

    Se resuelve por app y no por URL exacta, así las pantallas internas marcan
    su sección: la ficha de un cliente marca Clientes y una cotización marca
    Consultas. Catálogo y Precios comparten la app `productos`, así que ahí hace
    falta mirar el nombre de la ruta.
    """
    match = getattr(request, 'resolver_match', None)
    if match is None:
        return ''
    espacio = match.namespace or ''
    nombre = match.url_name or ''

    if espacio == 'productos':
        return 'precios' if nombre == 'precios' else 'catalogo'
    if espacio == 'reportes':
        return 'equipo'
    if espacio == 'accounts':
        # Cambiar la propia contraseña no es la sección Usuarios.
        return 'usuarios' if nombre.startswith('user_') else ''
    if espacio in ('consultas', 'clientes'):
        return espacio
    return 'dashboard' if nombre == 'dashboard' else ''


@register.simple_tag(takes_context=True)
def seccion_activa(context):
    return _seccion(context.get('request'))


@register.simple_tag(takes_context=True)
def clase_nav(context, nombre):
    """Las clases de un item del navbar, resaltado si es la sección actual."""
    activa = _seccion(context.get('request')) == nombre
    return f'{CLASES_BASE} {CLASES_ACTIVA if activa else CLASES_INACTIVA}'


@register.simple_tag(takes_context=True)
def clase_nav_gestion(context):
    """El botón del grupo se resalta cuando estás en cualquiera de sus items."""
    activa = _seccion(context.get('request')) in CLAVES_GESTION
    return f'{CLASES_BASE} {CLASES_ACTIVA if activa else CLASES_INACTIVA}'


@register.simple_tag(takes_context=True)
def items_gestion(context):
    """Los items administrativos que el usuario puede ver.

    Se devuelven juntos para que el template decida: con más de uno van en un
    desplegable, y con uno solo se muestra suelto — meter el único acceso de un
    rol detrás de un menú lo empeora, que es el caso de Tesorería con Precios y
    del Coach con Equipo.
    """
    user = getattr(context.get('request'), 'user', None)
    if user is None or not user.is_authenticated:
        return []

    permitido = {
        'precios': user.puede_editar_precios,
        'equipo': user.puede_ver_reportes,
        'usuarios': user.puede_gestionar_usuarios,
    }
    return [
        {'clave': clave, 'etiqueta': etiqueta, 'url': reverse(ruta)}
        for clave, (etiqueta, ruta) in GESTION.items() if permitido[clave]
    ]
