from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect


class CapacidadRequeridaMixin(LoginRequiredMixin):
    """Exige una capacidad del usuario para entrar a la vista.

    `capacidad` es el nombre de una property de CustomUser, por ejemplo
    'puede_editar_catalogo'. Si el usuario no la tiene, vuelve a su página
    inicial: para casi todos es el dashboard, pero mandar ahí a quien no puede
    verlo sería un rebote sin fin.
    """

    capacidad = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not self.capacidad:
            raise ValueError(f'{type(self).__name__} no declara `capacidad`.')
        if not getattr(request.user, self.capacidad, False):
            messages.error(request, 'No tenés permisos para acceder a esa sección.')
            return redirect(request.user.pagina_inicial)
        return super().dispatch(request, *args, **kwargs)


class VentasRequeridasMixin(CapacidadRequeridaMixin):
    """Para todo lo del circuito comercial: consultas y clientes.

    Entrar exige `puede_ver_ventas`; escribir exige además `puede_cargar_ventas`.
    Esa segunda mitad es lo que hace que el Coach pueda seguir el trabajo del
    equipo sin poder modificarlo, sin tener que duplicar cada vista en una
    versión de lectura.
    """

    capacidad = 'puede_ver_ventas'

    # Las vistas que existen para escribir lo declaran: ahí el formulario no
    # tiene sentido si el rol no puede guardarlo, así que se corta también el GET.
    exige_carga = False

    METODOS_DE_LECTURA = frozenset(['GET', 'HEAD', 'OPTIONS'])

    def dispatch(self, request, *args, **kwargs):
        escribe = self.exige_carga or request.method not in self.METODOS_DE_LECTURA
        if escribe and request.user.is_authenticated and not request.user.puede_cargar_ventas:
            messages.error(
                request, 'Tu rol puede consultar esta información, no modificarla.')
            return redirect(request.user.pagina_inicial)
        return super().dispatch(request, *args, **kwargs)
