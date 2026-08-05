from django.contrib import admin
from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('razon_social', 'cuit', 'contacto', 'provincia', 'localidad',
                    'condicion_fiscal', 'vendedor', 'telefono', 'email')
    list_filter = ('vendedor', 'condicion_fiscal', 'tipo_factura', 'provincia')
    search_fields = ('razon_social', 'cuit', 'dni', 'contacto', 'email',
                     'localidad', 'id_facturacion')
    ordering = ('razon_social',)
