from django.db import migrations, models

# Mapeo acordado de las cuentas existentes a los nuevos roles.
ROLES_INICIALES = {
    'lucianocingolani9@gmail.com': 'admin',
    'comercial3@supplyargentina.com.ar': 'gerente',
    'lcingolani@rioplatense.com': 'empleado',
}


def migrar_roles(apps, schema_editor):
    User = apps.get_model('accounts', 'CustomUser')

    # 'vendedor' pasa a llamarse 'empleado'
    User.objects.filter(role='vendedor').update(role='empleado')

    for email, role in ROLES_INICIALES.items():
        User.objects.filter(email=email).update(role=role)

    # El acceso al admin de Django ahora lo determina el rol. Un empleado o
    # gerente con is_staff/is_superuser heredado quedaría entrando igual.
    User.objects.exclude(role='admin').update(is_staff=False, is_superuser=False)
    User.objects.filter(role='admin').update(is_staff=True)


def revertir_roles(apps, schema_editor):
    User = apps.get_model('accounts', 'CustomUser')
    User.objects.filter(role='empleado').update(role='vendedor')
    User.objects.filter(role='admin').update(role='gerente')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_customuser_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(
                choices=[('admin', 'Admin'), ('gerente', 'Gerente'), ('empleado', 'Empleado')],
                default='empleado',
                max_length=20,
                verbose_name='rol',
            ),
        ),
        migrations.RunPython(migrar_roles, revertir_roles),
    ]
