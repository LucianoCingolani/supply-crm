import base64
import re

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


# Ancho al que se rellenan los números del código para ordenar. Nueve dígitos
# alcanzan para cualquier código real y dejan margen de sobra.
ANCHO_NUMERO = 9


def clave_de_orden(codigo):
    """El código en la forma que lo hace ordenar por medida y no por dígito.

    La base compara texto carácter por carácter, así que 'SA-10' cae antes de
    'SA-2' —'1' es menor que '2'— y una familia sale desordenada justo en la
    parte que interesa, que es la medida. Rellenando con ceros cada tanda de
    dígitos a un ancho fijo, el orden alfabético pasa a ser el numérico sin que
    la base tenga que saber nada del formato del código: 'SA-000000002' antes
    de 'SA-000000010'.

    En mayúsculas porque 'sa-1' y 'SA-1' son la misma familia escrita distinto,
    y si difieren solo en eso tienen que quedar juntas igual.
    """
    partes = re.split(r'(\d+)', (codigo or '').upper())
    return ''.join(p.zfill(ANCHO_NUMERO) if p.isdigit() else p for p in partes)


class ClaveDeOrdenField(models.CharField):
    """Mantiene la clave derivada del código en todos los caminos de escritura.

    Es un campo propio y no un `save()` sobreescrito porque el importador crea
    los artículos con `bulk_create`, que no llama a `save()` pero sí al
    `pre_save()` de cada campo. Así no queda forma de dar de alta un artículo
    sin clave. El que no cubre es `bulk_update`, pero ninguno de los que hay
    toca el código.
    """

    def pre_save(self, model_instance, add):
        valor = clave_de_orden(model_instance.codigo)
        setattr(model_instance, self.attname, valor)
        return valor


class Categoria(models.Model):
    """Las secciones del catálogo.

    Antes era texto libre en cada artículo: cada tipeo creaba una categoría
    nueva en silencio, no había forma de renombrar sin editar artículo por
    artículo, y no se podía crear una antes de tener algo que ponerle adentro.
    """

    nombre = models.CharField(max_length=150, unique=True, verbose_name='Nombre')

    class Meta:
        ordering = ['nombre']
        verbose_name = 'categoría'
        verbose_name_plural = 'categorías'

    def __str__(self):
        return self.nombre

    @classmethod
    def desde_nombre(cls, nombre):
        """La categoría con ese nombre, creándola si no existe.

        Un nombre vacío devuelve None, que es cómo se representa "sin
        clasificar". Lo usan el importador —los archivos traen categorías
        nuevas— y los tests.
        """
        nombre = (nombre or '').strip()
        if not nombre:
            return None
        return cls.objects.get_or_create(nombre=nombre)[0]


class Producto(models.Model):
    codigo = models.CharField(max_length=50, unique=True, verbose_name='Código')
    # Derivado de `codigo`, lo mantiene el propio campo. Está en la base y no
    # se calcula al vuelo porque es la columna por la que ordena y pagina el
    # catálogo, y eso lo tiene que hacer la base.
    codigo_orden = ClaveDeOrdenField(
        max_length=450, default='', editable=False, db_index=True)
    nombre = models.CharField(max_length=300, verbose_name='Nombre')
    unidad_medida = models.CharField(
        max_length=10, blank=True,
        choices=UNIDADES_MEDIDA,
        verbose_name='Unidad de medida',
    )
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='productos',
        verbose_name='Categoría',
    )
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
        ordering = ['categoria__nombre', 'codigo_orden']
        verbose_name = 'producto'
        verbose_name_plural = 'productos'

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"

    @property
    def simbolo_moneda(self):
        return simbolo(self.moneda)

    @property
    def foto_version(self):
        """Para versionar la URL de la foto.

        La sirve un endpoint con caché de 7 días y la URL no cambia nunca, así
        que sin esto el browser sigue mostrando la foto vieja después de
        cambiarla o borrarla. Con el timestamp, la que no cambió se sigue
        cacheando y la que cambió se pide de nuevo.

        En milisegundos y no en segundos: dos guardados dentro del mismo
        segundo dejarían la misma URL y la foto nueva no se vería.
        """
        return int(self.updated_at.timestamp() * 1000) if self.updated_at else 0

    @property
    def foto_data_uri(self):
        if self.foto and self.foto_tipo:
            data = base64.b64encode(bytes(self.foto)).decode()
            return f"data:{self.foto_tipo};base64,{data}"
        return ''
