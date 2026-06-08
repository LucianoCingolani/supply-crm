from django.contrib.auth.mixins import LoginRequiredMixin, AccessMixin
from django.shortcuts import redirect


class GerenteRequiredMixin(LoginRequiredMixin, AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_gerente:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)
