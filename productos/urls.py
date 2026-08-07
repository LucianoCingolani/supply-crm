from django.urls import path
from django.views.generic import RedirectView

from .views import CatalogoView, ProductoCreateView, ProductoDetailView

app_name = 'productos'

urlpatterns = [
    path('', CatalogoView.as_view(), name='catalogo'),
    path('nuevo/', ProductoCreateView.as_view(), name='create'),
    path('<int:pk>/', ProductoDetailView.as_view(), name='detail'),
    # La edición vive en la ficha. La URL vieja sigue viva para los enlaces
    # que ya estaban dando vueltas.
    path('<int:pk>/editar/',
         RedirectView.as_view(pattern_name='productos:detail', permanent=True),
         name='edit'),
]
