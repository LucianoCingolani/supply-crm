from django.contrib import admin
from .models import Producto


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'nombre', 'categoria', 'subcategoria', 'unidad_medida', 'precio', 'moneda', 'activo']
    list_filter = ['categoria', 'unidad_medida', 'moneda', 'activo']
    search_fields = ['codigo', 'nombre', 'categoria']
    list_editable = ['activo']
    ordering = ['categoria', 'nombre']
