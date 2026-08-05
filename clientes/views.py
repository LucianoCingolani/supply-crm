from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

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

    def get(self, request):
        q = request.GET.get('q', '').strip()
        qs = self.get_clientes().con_total_consultas_para(request.user)
        if q:
            qs = qs.filter(self._filtro_busqueda(q))
        # Orden explícito: el annotate agrega un GROUP BY y con eso Django deja
        # de considerar aplicable el ordering del Meta, así que paginar sin esto
        # puede repetir o saltear filas entre páginas.
        qs = qs.order_by('razon_social', 'pk')

        pagina = Paginator(qs, self.POR_PAGINA).get_page(request.GET.get('pagina'))
        clientes = list(pagina)
        self._adjuntar_ultima_consulta(clientes, request.user)

        return render(request, 'clientes/list.html', {
            'clientes': clientes,
            'pagina': pagina,
            'q': q,
            'total': pagina.paginator.count,
        })

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
    def get(self, request, pk):
        cliente = self.get_cliente(pk)
        consultas = (
            Consulta.objects.visibles_para(request.user)
            .filter(cliente=cliente)
            .select_related('vendedor')
            .order_by('-fecha', '-created_at')
        )
        return render(request, 'clientes/detail.html', {
            'cliente': cliente,
            'consultas': consultas,
        })


class ClienteEditView(ClienteAccesoMixin, View):
    def get(self, request, pk):
        cliente = self.get_cliente(pk)
        return render(request, 'clientes/form.html', {
            'form': ClienteForm(instance=cliente),
            'cliente': cliente,
        })

    def post(self, request, pk):
        cliente = self.get_cliente(pk)
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            return redirect('clientes:detail', pk=pk)
        return render(request, 'clientes/form.html', {
            'form': form,
            'cliente': cliente,
        })


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
