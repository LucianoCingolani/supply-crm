from django.db import migrations


def populate_clientes(apps, schema_editor):
    Consulta = apps.get_model('consultas', 'Consulta')
    Cliente = apps.get_model('clientes', 'Cliente')

    seen = {}  # key -> Cliente pk

    for consulta in Consulta.objects.order_by('created_at'):
        razon = (consulta.razon_social or '').strip()
        cuit = (consulta.cuit or '').strip()

        if not razon and not cuit:
            continue

        # Use CUIT as primary key, else normalized name
        key = cuit if cuit else razon.lower()

        if key not in seen:
            cliente = Cliente.objects.create(
                razon_social=razon or cuit,
                contacto=consulta.contacto or '',
                cuit=cuit,
                telefono=consulta.telefono or '',
                email=consulta.email or '',
            )
            seen[key] = cliente.pk

        consulta.cliente_id = seen[key]
        consulta.save(update_fields=['cliente_id'])


def reverse_populate(apps, schema_editor):
    Cliente = apps.get_model('clientes', 'Cliente')
    Cliente.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('consultas', '0003_consulta_cliente'),
    ]

    operations = [
        migrations.RunPython(populate_clientes, reverse_populate),
    ]
