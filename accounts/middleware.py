from django.shortcuts import redirect
from django.urls import reverse


class ForzarCambioPasswordMiddleware:
    """Si el usuario tiene `must_change_password`, lo manda a elegir una nueva.

    Se aplica a todo el sitio, incluido el admin de Django. Las únicas vistas
    accesibles son las de la lista blanca: sin ellas el usuario quedaría
    encerrado en un redirect sin poder ni cambiar la contraseña ni salir.
    """

    EXENTAS = {
        'accounts:change_password',
        'accounts:login',
        'accounts:logout',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated or not user.must_change_password:
            return None

        match = request.resolver_match
        if match and match.view_name in self.EXENTAS:
            return None
        # django_browser_reload y cualquier otra ruta de infra no deben redirigir
        if match and match.app_name == 'django_browser_reload':
            return None

        return redirect(reverse('accounts:change_password'))
