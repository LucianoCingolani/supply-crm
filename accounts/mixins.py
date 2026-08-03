from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect


class CapacidadRequeridaMixin(LoginRequiredMixin):
    """Exige una capacidad del usuario para entrar a la vista.

    `capacidad` es el nombre de una property de CustomUser, por ejemplo
    'puede_editar_catalogo'. Si el usuario no la tiene, vuelve al dashboard.
    """

    capacidad = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not self.capacidad:
            raise ValueError(f'{type(self).__name__} no declara `capacidad`.')
        if not getattr(request.user, self.capacidad, False):
            messages.error(request, 'No tenés permisos para acceder a esa sección.')
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)
