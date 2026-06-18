from django.contrib import admin
from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('razon_social', 'cuit', 'contacto', 'telefono', 'email')
    search_fields = ('razon_social', 'cuit', 'contacto', 'email')
    ordering = ('razon_social',)
