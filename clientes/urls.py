from django.urls import path
from .views import (
    ClienteAsignarView, ClienteDetailView, ClienteEditView,
    ClienteListView, ClienteSearchView,
)

app_name = 'clientes'

urlpatterns = [
    path('', ClienteListView.as_view(), name='list'),
    path('asignar/', ClienteAsignarView.as_view(), name='asignar'),
    path('buscar/', ClienteSearchView.as_view(), name='search'),
    path('<int:pk>/', ClienteDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', ClienteEditView.as_view(), name='edit'),
]
