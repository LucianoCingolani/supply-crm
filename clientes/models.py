import re

from django.db import models
from django.db.models import Count, Q


def normalizar_cuit(valor):
    """Deja el CUIT en formato canónico XX-XXXXXXXX-X.

    La lista de facturación los trae en dos formatos ('20275892859' y
    '30-53723484-5') y el matcheo de clientes compara texto exacto, así que sin
    normalizar el mismo cliente entra dos veces. Se aplica al guardar y al
    buscar, para que ambos lados usen la misma forma.
    """
    digitos = re.sub(r'\D', '', valor or '')
    if len(digitos) == 11:
        return f'{digitos[:2]}-{digitos[2:10]}-{digitos[10]}'
    return (valor or '').strip()


class ClienteQuerySet(models.QuerySet):
    def visibles_para(self, user):
        """Acota a los clientes que `user` tiene permitido ver.

        Un empleado ve únicamente los clientes con los que trabajó, es decir
        aquellos que tienen al menos una consulta suya.
        """
        if user.puede_ver_todos_los_clientes:
            return self
        return self.filter(consultas__vendedor=user).distinct()

    def con_total_consultas_para(self, user):
        """Anota `total_consultas` contando solo las consultas visibles para `user`."""
        filtro = Q() if user.puede_ver_todas_las_consultas else Q(consultas__vendedor=user)
        return self.annotate(total_consultas=Count('consultas', filter=filtro, distinct=True))


class Cliente(models.Model):
    # Condición fiscal — valores tal como los exporta el sistema de facturación
    RESPONSABLE_INSCRIPTO = 'Responsable Inscripto'
    RESPONSABLE_MONOTRIBUTO = 'Responsable Monotributo'
    EXENTO = 'Exento'
    CONSUMIDOR_FINAL = 'Consumidor final'
    NO_CATEGORIZADO = 'No Categorizado'

    CONDICION_FISCAL_CHOICES = [
        (RESPONSABLE_INSCRIPTO, 'Responsable Inscripto'),
        (RESPONSABLE_MONOTRIBUTO, 'Responsable Monotributo'),
        (EXENTO, 'Exento'),
        (CONSUMIDOR_FINAL, 'Consumidor final'),
        (NO_CATEGORIZADO, 'No Categorizado'),
    ]

    FACTURA_A = 'Factura A'
    FACTURA_B = 'Factura B'
    REMITO_X = 'Remito X'
    SIN_ESPECIFICAR = 'Sin especificar'

    TIPO_FACTURA_CHOICES = [
        (FACTURA_A, 'Factura A'),
        (FACTURA_B, 'Factura B'),
        (REMITO_X, 'Remito X'),
        (SIN_ESPECIFICAR, 'Sin especificar'),
    ]

    # ── Identidad ──────────────────────────────────────────────────
    razon_social = models.CharField(max_length=200, verbose_name='Razón social')
    contacto = models.CharField(max_length=150, blank=True, verbose_name='Contacto')
    cuit = models.CharField(max_length=30, blank=True, db_index=True, verbose_name='CUIT / CUIL')
    dni = models.CharField(max_length=15, blank=True, verbose_name='DNI')
    id_facturacion = models.PositiveIntegerField(
        null=True, blank=True, unique=True,
        verbose_name='ID en facturación',
        help_text='Número de cliente en el sistema de facturación. Permite re-sincronizar la lista.',
    )

    # ── Contacto ───────────────────────────────────────────────────
    telefono = models.CharField(max_length=30, blank=True, verbose_name='Teléfono')
    email = models.EmailField(blank=True)

    # ── Domicilio ──────────────────────────────────────────────────
    domicilio = models.CharField(max_length=200, blank=True, verbose_name='Domicilio')
    localidad = models.CharField(max_length=100, blank=True, verbose_name='Localidad')
    provincia = models.CharField(max_length=60, blank=True, verbose_name='Provincia')
    codigo_postal = models.CharField(max_length=10, blank=True, verbose_name='Código postal')

    # ── Datos fiscales ─────────────────────────────────────────────
    condicion_fiscal = models.CharField(
        max_length=30, blank=True, choices=CONDICION_FISCAL_CHOICES,
        verbose_name='Condición fiscal',
    )
    tipo_factura = models.CharField(
        max_length=20, blank=True, choices=TIPO_FACTURA_CHOICES,
        verbose_name='Tipo de factura',
    )

    notas = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ClienteQuerySet.as_manager()

    class Meta:
        ordering = ['razon_social']
        verbose_name = 'cliente'
        verbose_name_plural = 'clientes'

    def __str__(self):
        return self.razon_social

    def save(self, *args, **kwargs):
        # Todo CUIT queda guardado en la forma canónica, así el matcheo por
        # texto exacto no depende de cómo vino escrito.
        self.cuit = normalizar_cuit(self.cuit)
        super().save(*args, **kwargs)

    @property
    def ubicacion(self):
        """Localidad y provincia en una línea, para mostrar en las fichas."""
        partes = [p for p in (self.localidad, self.provincia) if p]
        return ', '.join(partes)
