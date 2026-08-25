"""El catálogo pasa a ordenarse por código en lugar de por descripción.

`codigo_orden` es el código con los números rellenados con ceros, que es lo que
hace que 'SA-2' salga antes de 'SA-10'. El campo lo mantiene solo en cada
escritura, pero los 740 artículos que ya están se cargaron antes de que
existiera: sin el paso de datos quedarían todos con la clave vacía y el orden
sería el del `id`.
"""

import productos.models
from django.db import migrations

from productos.models import clave_de_orden


def llenar_claves(apps, schema_editor):
    Producto = apps.get_model('productos', 'Producto')
    # only(): el modelo tiene la foto encima, medio mega por artículo, y traer
    # los 740 binarios para calcular una clave de texto son cientos de megas al
    # vacío. bulk_update no dispara el pre_save del campo, así que la clave se
    # calcula acá con la misma función.
    pendientes = []
    for producto in Producto.objects.only('id', 'codigo').iterator(chunk_size=500):
        producto.codigo_orden = clave_de_orden(producto.codigo)
        pendientes.append(producto)
    Producto.objects.bulk_update(pendientes, ['codigo_orden'], batch_size=500)


def vaciar_claves(apps, schema_editor):
    """Para atrás no hay nada que deshacer: la columna se va con AddField."""


class Migration(migrations.Migration):

    dependencies = [
        ('productos', '0006_categoria'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='producto',
            options={'ordering': ['categoria__nombre', 'codigo_orden'], 'verbose_name': 'producto', 'verbose_name_plural': 'productos'},
        ),
        migrations.AddField(
            model_name='producto',
            name='codigo_orden',
            field=productos.models.ClaveDeOrdenField(db_index=True, default='', editable=False, max_length=450),
        ),
        migrations.RunPython(llenar_claves, vaciar_claves),
    ]
