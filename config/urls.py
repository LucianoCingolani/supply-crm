from django.contrib import admin
from django.urls import path, include

from reportes.views import DashboardView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', DashboardView.as_view(), name='dashboard'),
    path('accounts/', include('accounts.urls')),
    path('clientes/', include('clientes.urls')),
    path('consultas/', include('consultas.urls')),
    path('productos/', include('productos.urls')),
    path('reportes/', include('reportes.urls')),
    path('__reload__/', include('django_browser_reload.urls')),
]
