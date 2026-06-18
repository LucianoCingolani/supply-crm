from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Cliente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('razon_social', models.CharField(max_length=200, verbose_name='Razón social')),
                ('contacto', models.CharField(blank=True, max_length=150, verbose_name='Contacto')),
                ('cuit', models.CharField(blank=True, db_index=True, max_length=30, verbose_name='CUIT / CUIL')),
                ('telefono', models.CharField(blank=True, max_length=30, verbose_name='Teléfono')),
                ('email', models.EmailField(blank=True)),
                ('notas', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'cliente',
                'verbose_name_plural': 'clientes',
                'ordering': ['razon_social'],
            },
        ),
    ]
