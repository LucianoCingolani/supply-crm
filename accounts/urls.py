from django.urls import path
from .views import (
    CustomLoginView, CustomLogoutView,
    UserListView, UserCreateView, UserEditView, UserPasswordView,
)

app_name = 'accounts'

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', CustomLogoutView.as_view(), name='logout'),
    path('usuarios/', UserListView.as_view(), name='user_list'),
    path('usuarios/nuevo/', UserCreateView.as_view(), name='user_create'),
    path('usuarios/<int:pk>/editar/', UserEditView.as_view(), name='user_edit'),
    path('usuarios/<int:pk>/contrasena/', UserPasswordView.as_view(), name='user_password'),
]
