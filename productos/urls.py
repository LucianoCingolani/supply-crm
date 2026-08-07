from django.urls import path
from .views import CatalogoView, ProductoCreateView, ProductoDetailView, ProductoEditView

app_name = 'productos'

urlpatterns = [
    path('', CatalogoView.as_view(), name='catalogo'),
    path('nuevo/', ProductoCreateView.as_view(), name='create'),
    path('<int:pk>/', ProductoDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', ProductoEditView.as_view(), name='edit'),
]
