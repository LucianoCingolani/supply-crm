from django.urls import path
from .views import CatalogoView, ProductoDetailView

app_name = 'productos'

urlpatterns = [
    path('', CatalogoView.as_view(), name='catalogo'),
    path('<int:pk>/', ProductoDetailView.as_view(), name='detail'),
]
