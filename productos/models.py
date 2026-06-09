from django.db import models


class Producto(models.Model):
    codigo = models.CharField(max_length=50, unique=True, verbose_name='Código')
    nombre = models.CharField(max_length=300, verbose_name='Nombre')
    categoria = models.CharField(max_length=150, blank=True, verbose_name='Categoría')
    subcategoria = models.CharField(max_length=150, blank=True, verbose_name='Subcategoría')
    precio = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        verbose_name='Precio de venta',
    )
    activo = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['categoria', 'nombre']
        verbose_name = 'producto'
        verbose_name_plural = 'productos'

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"
