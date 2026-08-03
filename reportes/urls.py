from django.urls import path

from .views import DetalleEmpleadoView, PanelEquipoView

app_name = 'reportes'

urlpatterns = [
    path('equipo/', PanelEquipoView.as_view(), name='equipo'),
    path('equipo/<int:pk>/', DetalleEmpleadoView.as_view(), name='empleado'),
]
