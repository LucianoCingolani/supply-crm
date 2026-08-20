"""La categoría pasa de texto libre en cada artículo a una tabla propia.

Va todo en una migración porque es un solo cambio: sin el paso de datos en el
medio, quitar la columna de texto perdería la categoría de los 740 artículos.
El nombre es la bisagra —los valores distintos de hoy se vuelven las filas de
Categoria— así que las URLs del catálogo, que filtran por nombre, no cambian.
"""

import django.db.models.deletion
from django.db import migrations, models


def texto_a_tabla(apps, schema_editor):
    Producto = apps.get_model('productos', 'Producto')
    Categoria = apps.get_model('productos', 'Categoria')

    nombres = sorted(set(
        Producto.objects.exclude(categoria='')
        .values_list('categoria', flat=True)
    ))
    for nombre in nombres:
        categoria = Categoria.objects.create(nombre=nombre)
        # Un UPDATE por categoría en lugar de uno por artículo.
        Producto.objects.filter(categoria=nombre).update(categoria_ref=categoria)


def tabla_a_texto(apps, schema_editor):
    Producto = apps.get_model('productos', 'Producto')
    Categoria = apps.get_model('productos', 'Categoria')

    for categoria in Categoria.objects.all():
        Producto.objects.filter(categoria_ref=categoria).update(categoria=categoria.nombre)


class Migration(migrations.Migration):

    dependencies = [
        ('productos', '0005_producto_colores'),
    ]

    operations = [
        migrations.CreateModel(
            name='Categoria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=150, unique=True,
                                            verbose_name='Nombre')),
            ],
            options={
                'verbose_name': 'categoría',
                'verbose_name_plural': 'categorías',
                'ordering': ['nombre'],
            },
        ),
        migrations.AddField(
            model_name='producto',
            name='categoria_ref',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='productos', to='productos.categoria',
                verbose_name='Categoría'),
        ),
        migrations.RunPython(texto_a_tabla, tabla_a_texto),
        migrations.RemoveField(model_name='producto', name='categoria'),
        migrations.RenameField(model_name='producto', old_name='categoria_ref',
                               new_name='categoria'),
        migrations.AlterModelOptions(
            name='producto',
            options={'ordering': ['categoria__nombre', 'nombre'],
                     'verbose_name': 'producto',
                     'verbose_name_plural': 'productos'},
        ),
    ]
