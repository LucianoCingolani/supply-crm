from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .forms import EmailLoginForm, PasswordChangeForm, UserCreateForm, UserEditForm
from .mixins import GerenteRequiredMixin

User = get_user_model()


class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True


class CustomLogoutView(LogoutView):
    next_page = 'accounts:login'


class UserListView(GerenteRequiredMixin, View):
    def get(self, request):
        users = User.objects.exclude(pk=request.user.pk).order_by('last_name', 'first_name')
        return render(request, 'accounts/users/list.html', {'users': users})


class UserCreateView(GerenteRequiredMixin, View):
    def get(self, request):
        return render(request, 'accounts/users/form.html', {'form': UserCreateForm(), 'title': 'Nuevo usuario'})

    def post(self, request):
        form = UserCreateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Usuario creado correctamente.')
            return redirect('accounts:user_list')
        return render(request, 'accounts/users/form.html', {'form': form, 'title': 'Nuevo usuario'})


class UserEditView(GerenteRequiredMixin, View):
    def get_user(self, pk):
        return get_object_or_404(User, pk=pk)

    def get(self, request, pk):
        user = self.get_user(pk)
        return render(request, 'accounts/users/form.html', {
            'form': UserEditForm(instance=user),
            'title': f'Editar — {user.get_full_name() or user.email}',
            'editing': True,
            'target_user': user,
        })

    def post(self, request, pk):
        user = self.get_user(pk)
        form = UserEditForm(request.POST, instance=user)
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


class UserPasswordView(GerenteRequiredMixin, View):
    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        return render(request, 'accounts/users/form.html', {
            'form': PasswordChangeForm(),
            'title': f'Cambiar contraseña — {user.get_full_name() or user.email}',
        })

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        form = PasswordChangeForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data['password1'])
            user.save()
            messages.success(request, 'Contraseña actualizada.')
            return redirect('accounts:user_list')
        return render(request, 'accounts/users/form.html', {
            'form': form,
            'title': f'Cambiar contraseña — {user.get_full_name() or user.email}',
        })
