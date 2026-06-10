from django.urls import path
from .views import CatalogoView, ProductoDetailView, ProductoEditView

app_name = 'productos'

urlpatterns = [
    path('', CatalogoView.as_view(), name='catalogo'),
    path('<int:pk>/', ProductoDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', ProductoEditView.as_view(), name='edit'),
]
