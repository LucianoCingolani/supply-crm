from django.urls import path
from .views import (
    ClienteRapidoView, ConsultaCreateParaClienteView, ConsultaDetailView,
    ConsultaEditView, ConsultaListView, CotizacionPDFView, CotizacionView,
    NuevaCotizacionView, ProductoFotoView,
)

app_name = 'consultas'

urlpatterns = [
    path('', ConsultaListView.as_view(), name='list'),
    # Toda consulta arranca de un cliente: no hay alta sin cliente elegido. El
    # modal de "Nueva consulta" elige uno existente o carga este mínimo, y
    # recién entonces se llega a las pantallas de abajo.
    path('cliente-rapido/', ClienteRapidoView.as_view(), name='cliente_rapido'),
    path('cliente/<int:cliente_pk>/nueva/', ConsultaCreateParaClienteView.as_view(), name='create'),
    path('cliente/<int:cliente_pk>/cotizacion/', NuevaCotizacionView.as_view(), name='nueva_cotizacion'),
    path('<int:pk>/', ConsultaDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', ConsultaEditView.as_view(), name='edit'),
    path('<int:pk>/cotizacion/', CotizacionView.as_view(), name='cotizacion'),
    path('<int:pk>/cotizacion/pdf/', CotizacionPDFView.as_view(), name='cotizacion_pdf'),
    path('producto/<int:pk>/foto/', ProductoFotoView.as_view(), name='producto_foto'),
]
