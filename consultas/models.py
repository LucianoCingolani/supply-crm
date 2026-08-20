from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Max, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from productos.models import ARS, MONEDAS, USD, simbolo

CENTAVOS = Decimal('0.01')
IVA = Decimal('0.21')


@dataclass(frozen=True)
class Totales:
    """Los tres números del pie de la cotización, en su moneda."""
    neto: Decimal
    iva: Decimal
    con_iva: Decimal


class ConsultaQuerySet(models.QuerySet):
    def visibles_para(self, user):
        """Acota a las consultas que `user` tiene permitido ver.

        Las consultas siguen al cliente: un empleado ve las de su cartera
        asignada, así al recibir un cliente hereda el historial y el contexto
        en lugar de arrancar a ciegas.

        Se agregan las propias que todavía no tienen cliente, para que nada de
        lo que cargó él mismo desaparezca de su vista.
        """
        if user.puede_ver_todas_las_consultas:
            return self
        return self.filter(
            Q(cliente__vendedor=user) | Q(cliente__isnull=True, vendedor=user)
        )

    def activas(self):
        return self.filter(estado__in=Consulta.ESTADOS_ACTIVOS)

    def con_ultimo_movimiento(self):
        """Anota `ultimo_movimiento`: el último seguimiento registrado, o la
        fecha de alta si nunca se registró ninguno.
        """
        return self.annotate(
            ultimo_movimiento=Coalesce(Max('logs__fecha'), 'created_at'),
        )


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

    # Moneda de la cotización. Las líneas guardan el precio en la moneda en que
    # se cargó; el total se expresa en esta, convirtiendo lo que haga falta.
    moneda = models.CharField(max_length=3, choices=MONEDAS, default=ARS, verbose_name='Moneda')
    tipo_cambio = models.DecimalField(
        max_digits=12, decimal_places=4,
        null=True, blank=True,
        verbose_name='Tipo de cambio',
        help_text='Pesos por dólar. Solo hace falta si la cotización mezcla monedas.',
    )

    # Estado y seguimiento
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=COTIZADO)
    notas = models.TextField(blank=True)
    fecha_seguimiento = models.DateField(null=True, blank=True)

    # Relaciones
    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='consultas',
        verbose_name='cliente',
    )
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='consultas',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ConsultaQuerySet.as_manager()

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

    @property
    def nombre_del_cliente(self):
        """A quién se le está cotizando, para el PDF.

        La consulta guarda una copia de la razón social al cargarse y esa es la
        fuente: sobrevive incluso si después se borra el cliente. La ficha queda
        como respaldo para las consultas que nunca la copiaron, y el contacto
        para las que no tienen razón social en ninguna parte.
        """
        copiada = (self.razon_social or '').strip()
        if copiada:
            return copiada
        if self.cliente_id and self.cliente and self.cliente.razon_social.strip():
            return self.cliente.razon_social.strip()
        return (self.contacto or '').strip()

    # ── Moneda y totales ───────────────────────────────────────────

    @property
    def simbolo_moneda(self):
        return simbolo(self.moneda)

    @property
    def mezcla_monedas(self):
        """True si hay líneas cargadas en una moneda distinta a la de la cotización."""
        return any(l.moneda != self.moneda for l in self.lineas.all())

    @property
    def falta_tipo_cambio(self):
        """Hay que convertir pero no se sabe a cuánto. El total no se puede calcular."""
        return self.mezcla_monedas and not self.tipo_cambio

    def convertir(self, monto, desde):
        """Pasa `monto` a la moneda de la cotización.

        Devuelve None si la conversión hace falta y no hay tipo de cambio: es
        preferible no mostrar número a mostrar uno inventado.
        """
        if monto is None:
            return None
        if desde == self.moneda:
            return monto
        if not self.tipo_cambio:
            return None
        if desde == USD:
            return (monto * self.tipo_cambio).quantize(CENTAVOS)
        return (monto / self.tipo_cambio).quantize(CENTAVOS)

    def totales(self):
        """Los totales en la moneda de la cotización, o None si falta el tipo de cambio."""
        neto = Decimal('0')
        for linea in self.lineas.all():
            convertido = self.convertir(linea.subtotal, linea.moneda)
            if convertido is None:
                return None
            neto += convertido
        neto = neto.quantize(CENTAVOS)
        iva = (neto * IVA).quantize(CENTAVOS)
        return Totales(neto=neto, iva=iva, con_iva=neto + iva)


class SeguimientoLog(models.Model):
    """Una nota de seguimiento.

    Cuelga del cliente, no de la cotización: así toda la conversación con el
    cliente queda en una sola línea de tiempo, que es como se trabaja en la
    práctica ("llamé, no contesta", "quedó en confirmar"). `consulta` queda
    opcional, para las notas que sí son sobre una cotización puntual.
    """

    cliente = models.ForeignKey(
        'clientes.Cliente', on_delete=models.CASCADE,
        null=True, blank=True, related_name='seguimientos',
    )
    consulta = models.ForeignKey(
        Consulta, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='logs',
    )
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
    # La línea guarda la moneda en la que se cargó el precio, no la de la
    # cotización: así cambiar el tipo de cambio recalcula todo sin perder el
    # dato original de cuánto costaba el artículo.
    moneda = models.CharField(max_length=3, choices=MONEDAS, default=ARS, verbose_name='Moneda')
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'id']

    @property
    def subtotal(self):
        """En la moneda de la línea."""
        return self.cantidad * self.precio_unitario

    @property
    def simbolo_moneda(self):
        return simbolo(self.moneda)

    @property
    def descripcion_del_articulo(self):
        """La descripción del catálogo, solo si difiere de la de la línea.

        La línea nace con la descripción copiada del artículo, pero el vendedor
        puede ajustarla al armar la cotización. Si la ajustó, la descripción del
        artículo tiene que salir igual en el PDF: es la que lo identifica. Si son
        la misma, devuelve vacío para no imprimirla dos veces.
        """
        if not self.producto:
            return ''
        catalogo = (self.producto.nombre or '').strip()
        return catalogo if catalogo != (self.descripcion or '').strip() else ''

    @property
    def es_de_otra_moneda(self):
        return self.moneda != self.consulta.moneda

    @property
    def precio_convertido(self):
        return self.consulta.convertir(self.precio_unitario, self.moneda)

    @property
    def subtotal_convertido(self):
        return self.consulta.convertir(self.subtotal, self.moneda)

    def __str__(self):
        return f"{self.descripcion} x{self.cantidad}"
