from django.contrib import admin
from .models import Consulta, CotizacionGenerada, SeguimientoLog


class SeguimientoInline(admin.TabularInline):
    model = SeguimientoLog
    extra = 0
    readonly_fields = ('fecha', 'user')


@admin.register(Consulta)
class ConsultaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'productos', 'razon_social', 'contacto', 'estado', 'vendedor')
    list_filter = ('estado', 'via_entrada', 'vendedor')
    search_fields = ('razon_social', 'contacto', 'productos', 'numero_cotizacion')
    inlines = [SeguimientoInline]


@admin.register(CotizacionGenerada)
class CotizacionGeneradaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'numero', 'consulta', 'generada_por', 'total_neto', 'enviada_at')
    list_filter = ('enviada_at', 'generada_por', 'moneda')
    search_fields = ('numero', 'consulta__razon_social')
    readonly_fields = ('fecha',)
