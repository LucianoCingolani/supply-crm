from django.contrib.auth import get_user_model
from django.db.models import Count
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View

from accounts.mixins import CapacidadRequeridaMixin
from consultas.models import Consulta, SeguimientoLog

from .metricas import (
    DIAS_POR_DEFECTO,
    PERIODOS,
    UMBRAL_FRIA,
    calcular_metricas,
    consultas_frias,
    empleados_visibles,
    fecha_desde,
)

User = get_user_model()


class ReporteBaseView(CapacidadRequeridaMixin, View):
    capacidad = 'puede_ver_reportes'

    def periodo(self, request):
        """Días del período pedido, validado contra las opciones del selector."""
        permitidos = {str(dias) for dias, _ in PERIODOS}
        crudo = request.GET.get('dias', '')
        return int(crudo) if crudo in permitidos else DIAS_POR_DEFECTO

    def contexto_periodo(self, dias, hoy):
        return {
            'dias': dias,
            'periodos': PERIODOS,
            'desde': fecha_desde(dias, hoy),
            'umbral_fria': UMBRAL_FRIA,
            'hoy': hoy,
        }


class PanelEquipoView(ReporteBaseView):
    """Vista general: una fila por empleado, los que más atención necesitan arriba."""

    def get(self, request):
        hoy = timezone.localdate()
        dias = self.periodo(request)
        metricas, totales = calcular_metricas(request.user, hoy, dias)

        return render(request, 'reportes/equipo.html', {
            'metricas': metricas,
            'totales': totales,
            'frias': consultas_frias(request.user, hoy, limite=15),
            **self.contexto_periodo(dias, hoy),
        })


class DetalleEmpleadoView(ReporteBaseView):
    """Ficha de un empleado: sus números y sus consultas sin movimiento."""

    # Tope de filas en la tabla de frías; el resto se ve en el listado de consultas.
    MAX_FRIAS = 50

    def get(self, request, pk):
        hoy = timezone.localdate()
        dias = self.periodo(request)
        empleado = get_object_or_404(empleados_visibles(request.user), pk=pk)

        metricas, _ = calcular_metricas(request.user, hoy, dias)
        suyas = next((m for m in metricas if m.empleado.pk == empleado.pk), None)

        frias = consultas_frias(request.user, hoy, vendedor=empleado, limite=self.MAX_FRIAS)
        total_activas = (
            Consulta.objects.visibles_para(request.user)
            .activas().filter(vendedor=empleado).count()
        )

        return render(request, 'reportes/empleado.html', {
            'empleado': empleado,
            'metricas': suyas,
            'desglose': self._desglose_por_estado(request.user, empleado, dias, hoy),
            'frias': frias,
            'total_activas': total_activas,
            'hay_mas_frias': total_activas > len(frias),
            'seguimientos': (
                SeguimientoLog.objects
                .filter(user=empleado)
                .select_related('consulta')[:20]
            ),
            **self.contexto_periodo(dias, hoy),
        })

    def _desglose_por_estado(self, user, empleado, dias, hoy):
        qs = Consulta.objects.visibles_para(user).filter(vendedor=empleado)
        desde = fecha_desde(dias, hoy)
        if desde:
            qs = qs.filter(fecha__gte=desde)

        conteos = dict(qs.values_list('estado').annotate(n=Count('id')))
        return [
            {'estado': valor, 'etiqueta': etiqueta, 'total': conteos.get(valor, 0)}
            for valor, etiqueta in Consulta.ESTADO_CHOICES
        ]
