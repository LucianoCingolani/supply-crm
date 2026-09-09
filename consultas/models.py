from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Count, Max, Q
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

    def a_cargo_de(self, user):
        """Acota a las que `user` tiene que seguir él: las que cargó y las de
        los clientes de su cartera.

        Para un empleado es todo lo que ve. La diferencia aparece con quien ve
        las consultas de todos: el dashboard le muestra su propio seguimiento y
        no el del equipo, que para eso está el panel.

        Se combina con `visibles_para`, que es la que decide el permiso: una
        consulta que cargó y que hoy cuelga de un cliente de otro vendedor
        sigue estando fuera de su alcance.
        """
        return self.filter(Q(vendedor=user) | Q(cliente__vendedor=user))

    def activas(self):
        return self.filter(estado__in=Consulta.ESTADOS_ACTIVOS)

    def con_ultimo_movimiento(self):
        """Anota `ultimo_movimiento`: el último seguimiento registrado, o la
        fecha de alta si nunca se registró ninguno.
        """
        return self.annotate(
            ultimo_movimiento=Coalesce(Max('logs__fecha'), 'created_at'),
        )

    def con_estado_de_cotizacion(self):
        """Anota si a esta consulta ya se le generó una cotización y cuándo se
        mandó la última.

        Es lo que la lista necesita para distinguir de un vistazo la consulta a
        la que ya se le cotizó de la que quedó sin cotizar. `estado` no lo
        contesta: nace en "cotizado" el día que se carga la consulta.
        """
        return self.annotate(
            cotizaciones_count=Count('cotizaciones', distinct=True),
            ultimo_envio=Max('cotizaciones__enviada_at'),
            # Tener la cotización armada y no haberla mandado no es lo mismo que
            # no tener nada: decirle "Sin cotizar" a una consulta con las líneas
            # cargadas es mentirle al que mira la columna.
            lineas_count=Count('lineas', distinct=True),
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


class CotizacionGenerada(models.Model):
    """Un PDF de cotización que salió del sistema.

    Se registra sola cada vez que se genera el PDF: bajarlo es el acto con el
    que se le manda la cotización al cliente, así el rastro no depende de que
    nadie se acuerde de anotarlo. Antes de esto no había manera de saber si a un
    cliente ya se le había cotizado: `Consulta.estado` nace en "cotizado" el día
    que se carga la consulta, sin una sola línea encima, y por eso no sirve para
    responderlo.

    Copia el número y el total del momento porque la cotización se sigue
    editando: lo que se lee acá es lo que se le mandó, no lo que dice la consulta
    hoy.

    "Generada" es lo único que el sistema sabe con certeza. Que además se haya
    mandado lo sella el vendedor de un click en `enviada_at`: el registro
    automático da el piso, la confirmación da la certeza.
    """

    # Dos descargas del mismo PDF en este lapso son el mismo envío: el vendedor
    # que lo mira, lo cierra y lo baja de nuevo para adjuntarlo no tiene que
    # dejar tres filas en la ficha.
    VENTANA_MISMA_DESCARGA = timedelta(hours=1)

    consulta = models.ForeignKey(
        Consulta, on_delete=models.CASCADE, related_name='cotizaciones')
    numero = models.CharField(max_length=20, blank=True, verbose_name='Nº de cotización')
    generada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='cotizaciones_generadas')
    fecha = models.DateTimeField(auto_now_add=True)

    # El total va suelto y no calculado desde las líneas: es una foto del
    # momento, y las líneas de la consulta cambian después.
    total_neto = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    moneda = models.CharField(max_length=3, choices=MONEDAS, default=ARS)

    enviada_at = models.DateTimeField(null=True, blank=True)
    enviada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'cotización generada'
        verbose_name_plural = 'cotizaciones generadas'

    def __str__(self):
        return f"Cotización {self.numero or self.consulta_id} — {self.fecha:%d/%m/%Y %H:%M}"

    @property
    def simbolo_moneda(self):
        return simbolo(self.moneda)

    @property
    def fue_enviada(self):
        return self.enviada_at is not None

    @classmethod
    def registrar(cls, consulta, user, totales):
        """Anota que se generó el PDF de `consulta`, o devuelve el registro que
        ya cubre esta descarga.

        Devuelve el registro en los dos casos, para que quien llama no tenga que
        distinguirlos.
        """
        numero = consulta.numero_cotizacion or ''
        neto = totales.neto if totales else None
        reciente = cls.objects.filter(
            consulta=consulta,
            generada_por=user,
            numero=numero,
            total_neto=neto,
            moneda=consulta.moneda,
            fecha__gte=timezone.now() - cls.VENTANA_MISMA_DESCARGA,
        ).first()
        if reciente:
            return reciente
        return cls.objects.create(
            consulta=consulta, numero=numero, generada_por=user,
            total_neto=neto, moneda=consulta.moneda,
        )

    def marcar_enviada(self, user):
        self.enviada_at = timezone.now()
        self.enviada_por = user
        self.save(update_fields=['enviada_at', 'enviada_por'])

    def desmarcar_enviada(self):
        self.enviada_at = None
        self.enviada_por = None
        self.save(update_fields=['enviada_at', 'enviada_por'])
