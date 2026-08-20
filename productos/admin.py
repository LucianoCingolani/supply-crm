from django.contrib import admin
from .models import Categoria, Producto


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'nombre', 'categoria', 'subcategoria', 'unidad_medida', 'precio', 'moneda', 'activo']
    list_filter = ['categoria', 'unidad_medida', 'moneda', 'activo']
    search_fields = ['codigo', 'nombre', 'categoria__nombre']
    list_editable = ['activo']
    ordering = ['categoria__nombre', 'nombre']


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ['nombre']
    search_fields = ['nombre']
