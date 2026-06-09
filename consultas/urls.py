from django.urls import path
from .views import (
    ConsultaListView, ConsultaCreateView, ConsultaDetailView, ConsultaEditView,
    ConsultaImportPDFView, CotizacionView, CotizacionPDFView,
)

app_name = 'consultas'

urlpatterns = [
    path('', ConsultaListView.as_view(), name='list'),
    path('nueva/', ConsultaCreateView.as_view(), name='create'),
    path('importar-pdf/', ConsultaImportPDFView.as_view(), name='import_pdf'),
    path('<int:pk>/', ConsultaDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', ConsultaEditView.as_view(), name='edit'),
    path('<int:pk>/cotizacion/', CotizacionView.as_view(), name='cotizacion'),
    path('<int:pk>/cotizacion/pdf/', CotizacionPDFView.as_view(), name='cotizacion_pdf'),
]
