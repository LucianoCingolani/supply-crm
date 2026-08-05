"""Cálculo de métricas de seguimiento por empleado.

Separado de las views para poder testearlo sin pasar por HTTP.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncMonth

from consultas.models import Consulta, SeguimientoLog

User = get_user_model()

MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
                'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

# Períodos ofrecidos en el selector. 0 significa "sin límite".
PERIODOS = [
    (30, 'Últimos 30 días'),
    (90, 'Últimos 90 días'),
    (365, 'Último año'),
    (0, 'Todo el historial'),
]
DIAS_POR_DEFECTO = 90

# A partir de cuántos días sin seguimiento una consulta activa se considera fría.
UMBRAL_FRIA = 30


@dataclass
class MetricasEmpleado:
    """Resumen de un empleado.

    Hay dos clases de número acá y no conviene mezclarlas:

    - Del período (`nuevas`, `facturadas`, `perdidas`, `seguimientos`): cuánto
      trabajó en la ventana elegida.
    - Del estado actual (`activas`, `frias`): cómo está su cartera hoy. No se
      filtran por período, porque una consulta fría lo es independientemente de
      cuándo entró; si se filtraran, elegir "últimos 30 días" daría siempre
      cero frías y escondería justamente el problema que el panel busca mostrar.
    """

    empleado: object
    nuevas: int = 0
    activas: int = 0
    facturadas: int = 0
    perdidas: int = 0
    seguimientos: int = 0
    frias: int = 0
    ventas_mes: int = 0
    dias_ultima_actividad: int | None = None
    _dias_frias: list = field(default_factory=list, repr=False)

    @property
    def conversion(self):
        """Porcentaje de consultas del período que terminaron facturadas."""
        cerradas = self.facturadas + self.perdidas
        if not cerradas:
            return None
        return round(self.facturadas * 100 / cerradas)

    @property
    def pct_facturado(self):
        """Facturadas sobre el total del período. Es la barra del panel.

        A diferencia de `conversion`, el denominador incluye las consultas
        todavía abiertas: responde "de todo lo que cotizó, cuánto vendió".
        """
        if not self.nuevas:
            return 0
        return round(self.facturadas * 100 / self.nuevas)

    @property
    def pct_facturado_texto(self):
        return f'{self.pct_facturado}%'

    @property
    def detalle_facturado(self):
        return f'{self.facturadas} de {self.nuevas}'

    @property
    def dias_frias_promedio(self):
        if not self._dias_frias:
            return None
        return round(sum(self._dias_frias) / len(self._dias_frias))

    @property
    def sin_actividad_registrada(self):
        return self.dias_ultima_actividad is None


def empleados_visibles(user):
    """Usuarios que `user` puede ver en el panel.

    Un Gerente no ve a los Admins, igual que en la gestión de usuarios.
    """
    qs = User.objects.filter(is_active=True)
    if not user.puede_administrar_admins:
        qs = qs.exclude(role=User.ADMIN)
    return qs.order_by('last_name', 'first_name')


def fecha_desde(dias, hoy):
    return hoy - timedelta(days=dias) if dias else None


def calcular_metricas(user, hoy, dias=DIAS_POR_DEFECTO):
    """Devuelve (metricas_por_empleado, totales) para el período pedido.

    Se resuelve con pocas queries y una pasada en Python: a la escala de este
    CRM (cientos de consultas) es más claro y más barato que media docena de
    agregaciones condicionales sobre joins múltiples.
    """
    desde = fecha_desde(dias, hoy)
    empleados = list(empleados_visibles(user))
    por_id = {e.pk: MetricasEmpleado(empleado=e) for e in empleados}
    visibles = Consulta.objects.visibles_para(user)

    # 1) Producción del período.
    consultas = visibles.filter(fecha__gte=desde) if desde else visibles
    for estado, vendedor_id in consultas.values_list('estado', 'vendedor'):
        metricas = por_id.get(vendedor_id)
        if metricas is None:
            continue  # vendedor inactivo o fuera del alcance del usuario
        metricas.nuevas += 1
        if estado in Consulta.ESTADOS_GANADOS:
            metricas.facturadas += 1
        elif estado in Consulta.ESTADOS_PERDIDOS:
            metricas.perdidas += 1

    # 2) Estado actual de la cartera: activas y cuántas están frías. Sin período.
    activas = visibles.activas().con_ultimo_movimiento()
    for vendedor_id, ultimo in activas.values_list('vendedor', 'ultimo_movimiento'):
        metricas = por_id.get(vendedor_id)
        if metricas is None:
            continue
        metricas.activas += 1
        dias_quieta = (hoy - ultimo.date()).days
        if dias_quieta >= UMBRAL_FRIA:
            metricas.frias += 1
            metricas._dias_frias.append(dias_quieta)

    # 3) Seguimientos registrados por cada empleado en el período.
    logs = SeguimientoLog.objects.all()
    if desde:
        logs = logs.filter(fecha__date__gte=desde)
    for user_id, total in logs.values_list('user').annotate(n=Count('id')):
        if user_id in por_id:
            por_id[user_id].seguimientos = total

    # 4) Ventas del mes calendario en curso — "cómo les está yendo este mes".
    ventas = (
        visibles
        .filter(estado__in=Consulta.ESTADOS_GANADOS,
                fecha__year=hoy.year, fecha__month=hoy.month)
        .values_list('vendedor').annotate(n=Count('id'))
    )
    for user_id, total in ventas:
        if user_id in por_id:
            por_id[user_id].ventas_mes = total

    # 5) Última señal de actividad de cada empleado, sin límite de período.
    _cargar_ultima_actividad(por_id, hoy)

    # Los que más atención necesitan, primero.
    orden = sorted(
        por_id.values(),
        key=lambda m: (-m.frias, -m.activas, m.empleado.last_name.lower()),
    )
    return orden, _totales(orden)


def _cargar_ultima_actividad(por_id, hoy):
    ultimo_log = dict(
        SeguimientoLog.objects.values_list('user').annotate(ultima=Max('fecha'))
    )
    ultima_consulta = dict(
        Consulta.objects.values_list('vendedor').annotate(ultima=Max('created_at'))
    )
    for user_id, metricas in por_id.items():
        fechas = [f for f in (ultimo_log.get(user_id), ultima_consulta.get(user_id)) if f]
        if fechas:
            metricas.dias_ultima_actividad = (hoy - max(fechas).date()).days


def _totales(metricas):
    facturadas = sum(m.facturadas for m in metricas)
    perdidas = sum(m.perdidas for m in metricas)
    nuevas = sum(m.nuevas for m in metricas)
    cerradas = facturadas + perdidas
    return {
        'nuevas': nuevas,
        'activas': sum(m.activas for m in metricas),
        'facturadas': facturadas,
        'perdidas': perdidas,
        'seguimientos': sum(m.seguimientos for m in metricas),
        'frias': sum(m.frias for m in metricas),
        'ventas_mes': sum(m.ventas_mes for m in metricas),
        'conversion': round(facturadas * 100 / cerradas) if cerradas else None,
        'pct_facturado': round(facturadas * 100 / nuevas) if nuevas else 0,
    }


def reparto_por_estado(user, hoy, dias=DIAS_POR_DEFECTO):
    """Parte-de-un-todo: cómo se reparten las consultas del período.

    No es un embudo: una consulta está en un estado y solo uno, no atraviesa
    etapas acumulativas. Cada fila se dibuja como su propia barra de un solo
    tono y va rotulada, así el color refuerza pero nunca es el único canal.
    """
    qs = Consulta.objects.visibles_para(user)
    desde = fecha_desde(dias, hoy)
    if desde:
        qs = qs.filter(fecha__gte=desde)

    total = qs.count()
    grupos = [
        ('facturadas', 'Facturadas', Consulta.ESTADOS_GANADOS),
        ('activas', 'Activas', Consulta.ESTADOS_ACTIVOS),
        ('perdidas', 'Perdidas', Consulta.ESTADOS_PERDIDOS),
    ]
    filas = []
    for clave, etiqueta, estados in grupos:
        n = qs.filter(estado__in=estados).count()
        pct = round(n * 100 / total) if total else 0
        filas.append({
            'clave': clave,
            'etiqueta': etiqueta,
            'total': n,
            'pct': pct,
            # Ya formateado: el meter no lo arma con `default`, que trata al 0 como ausente.
            'pct_texto': f'{pct}%',
        })
    return {'total': total, 'filas': filas}


def _meses_hacia_atras(hoy, cantidad):
    """Lista de primeros-de-mes, del más viejo al actual."""
    año, mes = hoy.year, hoy.month
    meses = []
    for _ in range(cantidad):
        meses.append(date(año, mes, 1))
        mes -= 1
        if mes == 0:
            año, mes = año - 1, 12
    return list(reversed(meses))


def evolucion_mensual(user, hoy, cantidad_meses=6):
    """Consultas y facturadas por mes. Misma unidad, así que comparten un eje."""
    meses = _meses_hacia_atras(hoy, cantidad_meses)
    qs = (
        Consulta.objects.visibles_para(user)
        .filter(fecha__gte=meses[0])
        .annotate(mes=TruncMonth('fecha'))
        .values('mes')
        .annotate(
            total=Count('id'),
            facturadas=Count('id', filter=Q(estado__in=Consulta.ESTADOS_GANADOS)),
        )
    )
    por_mes = {d['mes']: d for d in qs}
    return [
        {
            'mes': m,
            'etiqueta': f'{MESES_CORTOS[m.month - 1]} {str(m.year)[2:]}',
            'total': por_mes.get(m, {}).get('total', 0),
            'facturadas': por_mes.get(m, {}).get('facturadas', 0),
        }
        for m in meses
    ]


def consultas_frias(user, hoy, vendedor=None, limite=None):
    """Consultas activas ordenadas por tiempo sin movimiento, las más frías primero."""
    qs = (
        Consulta.objects.visibles_para(user)
        .activas()
        .con_ultimo_movimiento()
        .select_related('vendedor', 'cliente')
        .order_by('ultimo_movimiento')
    )
    if vendedor is not None:
        qs = qs.filter(vendedor=vendedor)

    consultas = list(qs[:limite] if limite else qs)
    for consulta in consultas:
        consulta.dias_sin_movimiento = (hoy - consulta.ultimo_movimiento.date()).days
    return consultas
