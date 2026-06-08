from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from consultas.models import Consulta


@login_required
def dashboard(request):
    qs = Consulta.objects.all() if request.user.is_gerente else Consulta.objects.filter(vendedor=request.user)
    today = timezone.now().date()
    stats = {
        'cotizado': qs.filter(estado='cotizado').count(),
        'facturado': qs.filter(estado='facturado').count(),
        'recontactar': qs.filter(estado='recontactar').count(),
        'total': qs.count(),
    }
    pendientes = qs.filter(estado__in=['cotizado', 'recontactar'], fecha_seguimiento__lte=today).order_by('fecha_seguimiento')[:10]
    return render(request, 'dashboard.html', {'stats': stats, 'pendientes': pendientes})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', dashboard, name='dashboard'),
    path('accounts/', include('accounts.urls')),
    path('consultas/', include('consultas.urls')),
    path('__reload__/', include('django_browser_reload.urls')),
]
