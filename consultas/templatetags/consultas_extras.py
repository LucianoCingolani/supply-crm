from django import template

register = template.Library()


@register.filter
def precio_ar(value):
    """Format a number as Argentine currency: 6.000,00"""
    try:
        formatted = f"{float(value):,.2f}"
        # US format (1,234.56) → AR format (1.234,56)
        return formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return value


# El nombre del mes se escribe acá y no se toma del locale: la traducción es_AR
# de Django dice "setiembre", y en la cotización se quiere "septiembre".
MESES = [
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]


@register.filter
def fecha_larga(fecha):
    """La fecha con el mes en palabras: 11 de septiembre de 2026."""
    try:
        return f'{fecha.day} de {MESES[fecha.month - 1]} de {fecha.year}'
    except (AttributeError, IndexError, TypeError):
        return fecha
