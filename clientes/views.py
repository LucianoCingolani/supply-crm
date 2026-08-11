from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from accounts.mixins import CapacidadRequeridaMixin
from consultas.forms import SeguimientoForm
from consultas.models import Consulta
from .forms import ClienteForm
from .models import Cliente, normalizar_cuit


class ClienteAccesoMixin(LoginRequiredMixin):
    """Da acceso solo a los clientes visibles para el usuario."""

    def get_clientes(self):
        return Cliente.objects.visibles_para(self.request.user)

    def get_cliente(self, pk):
        return get_object_or_404(self.get_clientes(), pk=pk)


class ClienteListView(ClienteAccesoMixin, View):
    POR_PAGINA = 50
    SIN_ASIGNAR = 'sin'

    def get(self, request):
        q = request.GET.get('q', '').strip()
        vendedor = request.GET.get('vendedor', '')
        qs = self.get_clientes().con_total_consultas()
        if q:
            qs = qs.filter(self._filtro_busqueda(q))
        qs = self._filtrar_por_vendedor(qs, vendedor, request.user)
        # Orden explícito: el annotate agrega un GROUP BY y con eso Django deja
        # de considerar aplicable el ordering del Meta, así que paginar sin esto
        # puede repetir o saltear filas entre páginas.
        qs = qs.order_by('razon_social', 'pk').select_related('vendedor')

        pagina = Paginator(qs, self.POR_PAGINA).get_page(request.GET.get('pagina'))
        clientes = list(pagina)
        self._adjuntar_ultima_consulta(clientes, request.user)

        return render(request, 'clientes/list.html', {
            'clientes': clientes,
            'pagina': pagina,
            'q': q,
            'total': pagina.paginator.count,
            'vendedor_activo': vendedor,
            'vendedores': self._vendedores(request.user),
            'puede_asignar': request.user.puede_asignar_clientes,
            'sin_asignar_valor': self.SIN_ASIGNAR,
            'sin_asignar_total': self._sin_asignar_total(request.user),
        })

    def _vendedores(self, user):
        if not user.puede_asignar_clientes:
            return None
        qs = get_user_model().objects.filter(is_active=True)
        if not user.puede_administrar_admins:
            qs = qs.exclude(role=get_user_model().ADMIN)
        return qs.order_by('last_name', 'first_name')

    def _filtrar_por_vendedor(self, qs, vendedor, user):
        if not user.puede_asignar_clientes:
            return qs
        if vendedor == self.SIN_ASIGNAR:
            return qs.sin_asignar()
        if vendedor.isdigit():
            return qs.filter(vendedor_id=vendedor)
        return qs

    def _sin_asignar_total(self, user):
        if not user.puede_asignar_clientes:
            return None
        return Cliente.objects.sin_asignar().count()

    def _filtro_busqueda(self, q):
        filtro = (
            Q(razon_social__icontains=q) |
            Q(cuit__icontains=q) |
            Q(dni__icontains=q) |
            Q(contacto__icontains=q) |
            Q(email__icontains=q) |
            Q(localidad__icontains=q) |
            Q(provincia__icontains=q)
        )
        # Los CUIT quedan guardados con guiones. Si alguien pega uno sin ellos
        # (que es como los exporta el facturador), hay que buscar la forma canónica.
        normalizado = normalizar_cuit(q)
        if normalizado != q:
            filtro |= Q(cuit=normalizado)
        return filtro

    def _adjuntar_ultima_consulta(self, clientes, user):
        """Setea `ultima_visible` en cada cliente con una sola query extra."""
        if not clientes:
            return
        consultas = (
            Consulta.objects.visibles_para(user)
            .filter(cliente__in=clientes)
            .order_by('cliente_id', '-fecha', '-created_at')
        )
        ultimas = {}
        for consulta in consultas:
            ultimas.setdefault(consulta.cliente_id, consulta)
        for cliente in clientes:
            cliente.ultima_visible = ultimas.get(cliente.pk)


class ClienteDetailView(ClienteAccesoMixin, View):
    """Centro del flujo: desde acá se registra la consulta y el seguimiento."""

    def contexto(self, request, cliente, seg_form=None):
        return {
            'cliente': cliente,
            'consultas': (
                Consulta.objects.visibles_para(request.user)
                .filter(cliente=cliente)
                .select_related('vendedor')
                .order_by('-fecha', '-created_at')
            ),
            'seguimientos': (
                cliente.seguimientos
                .select_related('user', 'consulta')
                .order_by('-fecha')
            ),
            'seg_form': seg_form or SeguimientoForm(),
        }

    def get(self, request, pk):
        cliente = self.get_cliente(pk)
        return render(request, 'clientes/detail.html', self.contexto(request, cliente))

    def post(self, request, pk):
        """Alta de un seguimiento del cliente."""
        cliente = self.get_cliente(pk)
        form = SeguimientoForm(request.POST)
        if form.is_valid():
            log = form.save(commit=False)
            log.cliente = cliente
            log.user = request.user
            log.save()
            messages.success(request, 'Seguimiento registrado.')
            return redirect('clientes:detail', pk=pk)
        return render(request, 'clientes/detail.html',
                      self.contexto(request, cliente, seg_form=form))


class ClienteCreateView(LoginRequiredMixin, View):
    """Alta de un cliente que consulta por primera vez.

    Cualquiera puede cargarlo: el que atiende la consulta es el que tiene los
    datos. Avisa si el CUIT ya está en la base, que es la forma en que este
    listado de 3900 clientes se llena de duplicados.
    """

    def get(self, request):
        return self.render_form(request, ClienteForm(
            editor=request.user, initial=self.inicial(request)))

    def post(self, request):
        form = ClienteForm(request.POST, editor=request.user)
        if not form.is_valid():
            return self.render_form(request, form)

        duplicados = self.duplicados(request, form.cleaned_data.get('cuit', ''))
        # Frenar en el primer intento y mostrar con quién choca. Forzar el alta
        # queda para quien reparte la cartera: un empleado que ve un duplicado
        # casi siempre está por cargar de nuevo un cliente que ya existe.
        if duplicados and not (request.POST.get('confirmar')
                               and request.user.puede_asignar_clientes):
            return self.render_form(request, form, duplicados)

        cliente = form.save(commit=False)
        # El que lo trae se lo queda. Sin esto un empleado carga un cliente y
        # lo pierde de vista, porque solo ve lo que tiene asignado.
        if not request.user.puede_asignar_clientes:
            cliente.vendedor = request.user
        cliente.save()
        messages.success(request, f'Cliente "{cliente.razon_social}" creado.')
        return redirect('clientes:detail', pk=cliente.pk)

    def inicial(self, request):
        """Al que puede elegir vendedor se le propone él mismo, sin obligarlo."""
        if request.user.puede_asignar_clientes:
            return {'vendedor': request.user}
        return {}

    def duplicados(self, request, cuit):
        """Clientes con ese mismo CUIT, marcando los que el usuario puede ver.

        Uno que no ve no lo puede abrir: está en la cartera de otro y eso lo
        resuelve el gerente asignándoselo.
        """
        cuit = normalizar_cuit(cuit)
        if not cuit:
            return []
        visibles = set(
            Cliente.objects.visibles_para(request.user)
            .filter(cuit=cuit).values_list('pk', flat=True)
        )
        return [
            {'cliente': c, 'visible': c.pk in visibles}
            for c in Cliente.objects.filter(cuit=cuit).select_related('vendedor')
        ]

    def render_form(self, request, form, duplicados=None):
        return render(request, 'clientes/form.html', {
            'form': form,
            'titulo': 'Nuevo cliente',
            'volver_url': reverse('clientes:list'),
            'duplicados': duplicados,
            'puede_forzar': request.user.puede_asignar_clientes,
        })


class ClienteEditView(ClienteAccesoMixin, View):
    def get(self, request, pk):
        cliente = self.get_cliente(pk)
        return self.render_form(request, cliente,
                                ClienteForm(instance=cliente, editor=request.user))

    def post(self, request, pk):
        cliente = self.get_cliente(pk)
        form = ClienteForm(request.POST, instance=cliente, editor=request.user)
        if form.is_valid():
            form.save()
            return redirect('clientes:detail', pk=pk)
        return self.render_form(request, cliente, form)

    def render_form(self, request, cliente, form):
        return render(request, 'clientes/form.html', {
            'form': form,
            'cliente': cliente,
            'titulo': 'Editar cliente',
            'volver_url': reverse('clientes:detail', args=[cliente.pk]),
        })


class ClienteBorrarView(CapacidadRequeridaMixin, View):
    """Baja definitiva de un cliente, con una pantalla que dice qué se pierde.

    No es una operación inocente: las consultas quedan sin cliente (SET_NULL) y
    los seguimientos se borran con él (CASCADE). Por eso el GET nunca borra, y
    la confirmación muestra los números concretos de ese cliente.
    """

    capacidad = 'puede_borrar_clientes'

    def get(self, request, pk):
        cliente = self.get_cliente(pk)
        return render(request, 'clientes/confirmar_borrado.html', {
            'cliente': cliente,
            'consultas': cliente.consultas.count(),
            'seguimientos': cliente.seguimientos.count(),
        })

    def post(self, request, pk):
        cliente = self.get_cliente(pk)
        nombre = cliente.razon_social
        cliente.delete()
        messages.success(request, f'Cliente "{nombre}" borrado.')
        return redirect('clientes:list')

    def get_cliente(self, pk):
        # Por la capacidad acá solo entran Admin y Gerente, que ven todo; pasa
        # igual por visibles_para para no depender de eso.
        return get_object_or_404(
            Cliente.objects.visibles_para(self.request.user), pk=pk)


class ClienteAsignarView(CapacidadRequeridaMixin, View):
    """Asigna en lote los clientes tildados en la lista."""

    capacidad = 'puede_asignar_clientes'

    def post(self, request):
        volver = request.POST.get('volver') or reverse('clientes:list')
        ids = request.POST.getlist('cliente')
        if not ids:
            messages.error(request, 'No seleccionaste ningún cliente.')
            return redirect(volver)

        vendedor, etiqueta = self._destino(request)
        if vendedor is False:
            messages.error(request, 'Elegí a quién asignárselos.')
            return redirect(volver)

        actualizados = Cliente.objects.filter(pk__in=ids).update(vendedor=vendedor)
        messages.success(
            request,
            f'{actualizados} cliente{"s" if actualizados != 1 else ""} '
            f'{"asignados" if actualizados != 1 else "asignado"} a {etiqueta}.')
        return redirect(volver)

    def _destino(self, request):
        """Devuelve (vendedor, etiqueta). vendedor False si la elección es inválida."""
        crudo = request.POST.get('vendedor', '')
        if crudo == 'ninguno':
            return None, 'nadie (quedaron sin asignar)'
        if not crudo.isdigit():
            return False, ''

        candidatos = get_user_model().objects.filter(is_active=True)
        if not request.user.puede_administrar_admins:
            candidatos = candidatos.exclude(role=get_user_model().ADMIN)
        vendedor = candidatos.filter(pk=crudo).first()
        if not vendedor:
            return False, ''
        return vendedor, vendedor.get_full_name() or vendedor.email


class ClienteSearchView(ClienteAccesoMixin, View):
    """Endpoint JSON para el autocomplete en formularios de consulta."""
    def get(self, request):
        q = request.GET.get('q', '').strip()
        qs = self.get_clientes()
        if q:
            filtro = (
                Q(razon_social__icontains=q) |
                Q(cuit__icontains=q) |
                Q(contacto__icontains=q)
            )
            normalizado = normalizar_cuit(q)
            if normalizado != q:
                filtro |= Q(cuit=normalizado)
            qs = qs.filter(filtro)
        data = list(qs.values('id', 'razon_social', 'cuit', 'contacto', 'telefono', 'email')[:20])
        return JsonResponse(data, safe=False)
