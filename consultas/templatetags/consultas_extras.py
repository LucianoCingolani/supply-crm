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
