import base64

from django.db import models

# Monedas del sistema. Viven acá porque el precio nace en el catálogo, y de acá
# las toma la cotización.
ARS = 'ARS'
USD = 'USD'

MONEDAS = [
    (ARS, 'Pesos'),
    (USD, 'Dólares'),
]

SIMBOLOS = {ARS: '$', USD: 'u$s'}


def simbolo(moneda):
    return SIMBOLOS.get(moneda, '$')


# El catálogo importado de Enexpro no trae unidad, así que el campo admite
# vacío: solo las altas manuales la cargan.
UNIDADES_MEDIDA = [
    ('UN', 'Unidad'),
    ('PAR', 'Par'),
    ('CAJA', 'Caja'),
    ('PACK', 'Pack'),
    ('BOLSA', 'Bolsa'),
    ('ROLLO', 'Rollo'),
    ('KG', 'Kilogramo'),
    ('GR', 'Gramo'),
    ('TN', 'Tonelada'),
    ('LT', 'Litro'),
    ('M', 'Metro'),
    ('M2', 'Metro cuadrado'),
    ('M3', 'Metro cúbico'),
]


class Producto(models.Model):
    codigo = models.CharField(max_length=50, unique=True, verbose_name='Código')
    nombre = models.CharField(max_length=300, verbose_name='Nombre')
    unidad_medida = models.CharField(
        max_length=10, blank=True,
        choices=UNIDADES_MEDIDA,
        verbose_name='Unidad de medida',
    )
    categoria = models.CharField(max_length=150, blank=True, verbose_name='Categoría')
    subcategoria = models.CharField(max_length=150, blank=True, verbose_name='Subcategoría')
    precio = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        verbose_name='Precio de venta',
    )
    moneda = models.CharField(
        max_length=3, choices=MONEDAS, default=ARS,
        verbose_name='Moneda',
    )
    especificaciones = models.TextField(
        blank=True,
        verbose_name='Especificaciones técnicas',
        help_text='Bullet points separados por salto de línea',
    )
    colores = models.CharField(
        max_length=100, blank=True,
        verbose_name='Colores',
        help_text='Sale en la cotización como "Colores: …". Vacío, no se imprime.',
    )
    foto = models.BinaryField(blank=True, null=True)
    foto_tipo = models.CharField(max_length=30, blank=True)  # 'image/jpeg' | 'image/png'
    activo = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['categoria', 'nombre']
        verbose_name = 'producto'
        verbose_name_plural = 'productos'

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"

    @property
    def simbolo_moneda(self):
        return simbolo(self.moneda)

    @property
    def foto_data_uri(self):
        if self.foto and self.foto_tipo:
            data = base64.b64encode(bytes(self.foto)).decode()
            return f"data:{self.foto_tipo};base64,{data}"
        return ''
