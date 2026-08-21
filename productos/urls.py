from django.urls import path
from django.views.generic import RedirectView

from .views import (
    BajasView, CatalogoView, CategoriasView, PreciosView, ProductoBorrarView,
    ProductoCreateView, ProductoDetailView, ProductoFotoBorrarView,
)

app_name = 'productos'

urlpatterns = [
    path('', CatalogoView.as_view(), name='catalogo'),
    path('precios/', PreciosView.as_view(), name='precios'),
    path('categorias/', CategoriasView.as_view(), name='categorias'),
    path('nuevo/', ProductoCreateView.as_view(), name='create'),
    path('bajas/', BajasView.as_view(), name='bajas'),
    path('<int:pk>/', ProductoDetailView.as_view(), name='detail'),
    path('<int:pk>/borrar/', ProductoBorrarView.as_view(), name='borrar'),
    path('<int:pk>/foto/borrar/', ProductoFotoBorrarView.as_view(), name='borrar_foto'),
    # La edición vive en la ficha. La URL vieja sigue viva para los enlaces
    # que ya estaban dando vueltas.
    path('<int:pk>/editar/',
         RedirectView.as_view(pattern_name='productos:detail', permanent=True),
         name='edit'),
]
