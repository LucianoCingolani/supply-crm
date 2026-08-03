from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .forms import (
    AdminSetPasswordForm,
    CambiarPasswordPropiaForm,
    EmailLoginForm,
    UserCreateForm,
    UserEditForm,
)
from .mixins import CapacidadRequeridaMixin

User = get_user_model()


class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True


class CustomLogoutView(LogoutView):
    next_page = 'accounts:login'


class GestionUsuariosMixin(CapacidadRequeridaMixin):
    """Base de las vistas de usuarios.

    Un Gerente gestiona usuarios, pero no ve ni toca a los Admins: para él
    esas cuentas no existen (404), y no puede asignar el rol Admin.
    """

    capacidad = 'puede_gestionar_usuarios'

    def get_usuarios(self):
        qs = User.objects.exclude(pk=self.request.user.pk)
        if not self.request.user.puede_administrar_admins:
            qs = qs.exclude(role=User.ADMIN)
        return qs

    def get_usuario(self, pk):
        return get_object_or_404(self.get_usuarios(), pk=pk)


class UserListView(GestionUsuariosMixin, View):
    def get(self, request):
        users = self.get_usuarios().order_by('last_name', 'first_name')
        return render(request, 'accounts/users/list.html', {'users': users})


class UserCreateView(GestionUsuariosMixin, View):
    def get(self, request):
        return render(request, 'accounts/users/form.html', {
            'form': UserCreateForm(editor=request.user),
            'title': 'Nuevo usuario',
        })

    def post(self, request):
        form = UserCreateForm(request.POST, editor=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Usuario creado correctamente.')
            return redirect('accounts:user_list')
        return render(request, 'accounts/users/form.html', {'form': form, 'title': 'Nuevo usuario'})


class UserEditView(GestionUsuariosMixin, View):
    def get(self, request, pk):
        user = self.get_usuario(pk)
        return render(request, 'accounts/users/form.html', {
            'form': UserEditForm(instance=user, editor=request.user),
            'title': f'Editar — {user.get_full_name() or user.email}',
            'editing': True,
            'target_user': user,
        })

    def post(self, request, pk):
        user = self.get_usuario(pk)
        form = UserEditForm(request.POST, instance=user, editor=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Usuario actualizado.')
            return redirect('accounts:user_list')
        return render(request, 'accounts/users/form.html', {
            'form': form,
            'title': f'Editar — {user.get_full_name() or user.email}',
            'editing': True,
            'target_user': user,
        })


class UserPasswordView(GestionUsuariosMixin, View):
    def get(self, request, pk):
        user = self.get_usuario(pk)
        return render(request, 'accounts/users/form.html', {
            'form': AdminSetPasswordForm(usuario_objetivo=user),
            'title': f'Cambiar contraseña — {user.get_full_name() or user.email}',
        })

    def post(self, request, pk):
        user = self.get_usuario(pk)
        form = AdminSetPasswordForm(request.POST, usuario_objetivo=user)
        if form.is_valid():
            user.set_password(form.cleaned_data['password1'])
            user.must_change_password = form.cleaned_data['must_change_password']
            user.save()
            if user.must_change_password:
                messages.success(
                    request,
                    f'Contraseña actualizada. {user.get_full_name() or user.email} '
                    'va a tener que elegir una nueva al ingresar.')
            else:
                messages.success(request, 'Contraseña actualizada.')
            return redirect('accounts:user_list')
        return render(request, 'accounts/users/form.html', {
            'form': form,
            'title': f'Cambiar contraseña — {user.get_full_name() or user.email}',
        })


class CambiarPasswordView(LoginRequiredMixin, View):
    """La persona cambia su propia contraseña.

    Es la única vista, junto con login y logout, a la que llega alguien con
    `must_change_password`: el middleware redirige todo lo demás hacia acá.
    """

    def form(self, request, data=None):
        return CambiarPasswordPropiaForm(
            data,
            usuario_objetivo=request.user,
            exigir_actual=not request.user.must_change_password,
        )

    def contexto(self, request, form):
        return {'form': form, 'obligatorio': request.user.must_change_password}

    def get(self, request):
        return render(request, 'accounts/cambiar_password.html',
                      self.contexto(request, self.form(request)))

    def post(self, request):
        form = self.form(request, request.POST)
        if not form.is_valid():
            return render(request, 'accounts/cambiar_password.html',
                          self.contexto(request, form))

        user = request.user
        user.set_password(form.cleaned_data['password1'])
        user.must_change_password = False
        user.save()
        # set_password rota el hash de sesión: sin esto la persona queda deslogueada.
        update_session_auth_hash(request, user)
        messages.success(request, 'Listo, tu contraseña quedó actualizada.')
        return redirect('dashboard')
