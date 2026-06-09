from django.conf import settings
from django.db import models
from django.utils import timezone


class Consulta(models.Model):
    # Estados
    COTIZADO = 'cotizado'
    FACTURADO = 'facturado'
    COMPRO_OTRO = 'compro_otro'
    NO_COMPRA = 'no_compra'
    CANCELADO = 'cancelado'
    RECONTACTAR = 'recontactar'

    ESTADO_CHOICES = [
        (COTIZADO, 'Cotizado'),
        (FACTURADO, 'Facturado'),
        (COMPRO_OTRO, 'Compró en otro lado'),
        (NO_COMPRA, 'No va a comprar'),
        (CANCELADO, 'Cancelado'),
        (RECONTACTAR, 'Recontactar más adelante'),
    ]

    ESTADOS_ACTIVOS = [COTIZADO, RECONTACTAR]
    ESTADOS_GANADOS = [FACTURADO]
    ESTADOS_PERDIDOS = [COMPRO_OTRO, NO_COMPRA, CANCELADO]

    # Vías de entrada
    MAIL = 'mail'
    WHATSAPP = 'whatsapp'
    TELEFONO = 'telefono'
    RECUPERO = 'recupero'

    VIA_CHOICES = [
        (MAIL, 'Mail'),
        (WHATSAPP, 'WhatsApp'),
        (TELEFONO, 'Teléfono'),
        (RECUPERO, 'Recuperé contacto'),
    ]

    # Datos de la consulta
    fecha = models.DateField(default=timezone.now)
    productos = models.CharField(max_length=300)
    cantidad = models.CharField(max_length=50, blank=True)
    numero_cotizacion = models.CharField(max_length=20, blank=True)
    via_entrada = models.CharField(max_length=20, choices=VIA_CHOICES, default=WHATSAPP)

    # Datos del cliente
    razon_social = models.CharField(max_length=200, blank=True)
    contacto = models.CharField(max_length=150, blank=True)
    cuit = models.CharField(max_length=30, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)

    # Estado y seguimiento
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=COTIZADO)
    notas = models.TextField(blank=True)
    fecha_seguimiento = models.DateField(null=True, blank=True)

    # Relaciones
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='consultas',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha', '-created_at']
        verbose_name = 'consulta'
        verbose_name_plural = 'consultas'

    def __str__(self):
        return f"{self.fecha} — {self.productos[:50]} ({self.razon_social or 'Sin empresa'})"

    @property
    def es_activa(self):
        return self.estado in self.ESTADOS_ACTIVOS

    @property
    def es_ganada(self):
        return self.estado in self.ESTADOS_GANADOS

    @property
    def es_perdida(self):
        return self.estado in self.ESTADOS_PERDIDOS

    @property
    def seguimiento_vencido(self):
        if self.fecha_seguimiento and self.es_activa:
            return self.fecha_seguimiento <= timezone.now().date()
        return False


class SeguimientoLog(models.Model):
    consulta = models.ForeignKey(Consulta, on_delete=models.CASCADE, related_name='logs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    nota = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y %H:%M} — {self.user}"


class LineaCotizacion(models.Model):
    consulta = models.ForeignKey(Consulta, on_delete=models.CASCADE, related_name='lineas')
    producto = models.ForeignKey(
        'productos.Producto', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    descripcion = models.CharField(max_length=300)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'id']

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def __str__(self):
        return f"{self.descripcion} x{self.cantidad}"
