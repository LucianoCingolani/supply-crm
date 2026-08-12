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


@register.filter
def precio_cotizacion(value):
    """Como precio_ar pero sin centavos cuando son cero.

    El modelo de cotización escribe "$ 87.500 + IVA", no "87.500,00". Los
    centavos igual quedan cuando existen, que es el caso de los precios en
    dólares ("u$s 49,50").
    """
    texto = precio_ar(value)
    if isinstance(texto, str) and texto.endswith(',00'):
        return texto[:-3]
    return texto
