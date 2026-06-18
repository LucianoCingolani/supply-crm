from django.urls import path
from .views import ClienteDetailView, ClienteEditView, ClienteListView, ClienteSearchView

app_name = 'clientes'

urlpatterns = [
    path('', ClienteListView.as_view(), name='list'),
    path('buscar/', ClienteSearchView.as_view(), name='search'),
    path('<int:pk>/', ClienteDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', ClienteEditView.as_view(), name='edit'),
]
