from django.urls import path
from .views import ConsultaListView, ConsultaCreateView, ConsultaDetailView, ConsultaEditView

app_name = 'consultas'

urlpatterns = [
    path('', ConsultaListView.as_view(), name='list'),
    path('nueva/', ConsultaCreateView.as_view(), name='create'),
    path('<int:pk>/', ConsultaDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', ConsultaEditView.as_view(), name='edit'),
]
