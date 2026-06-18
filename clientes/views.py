from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .forms import ClienteForm
from .models import Cliente


class ClienteListView(LoginRequiredMixin, View):
    def get(self, request):
        q = request.GET.get('q', '').strip()
        qs = Cliente.objects.annotate(total_consultas=Count('consultas'))
        if q:
            qs = qs.filter(
                Q(razon_social__icontains=q) |
                Q(cuit__icontains=q) |
                Q(contacto__icontains=q) |
                Q(email__icontains=q)
            )
        return render(request, 'clientes/list.html', {
            'clientes': qs,
            'q': q,
            'total': qs.count(),
        })


class ClienteDetailView(LoginRequiredMixin, View):
    def get(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk)
        consultas = cliente.consultas.select_related('vendedor').order_by('-fecha', '-created_at')
        return render(request, 'clientes/detail.html', {
            'cliente': cliente,
            'consultas': consultas,
        })


class ClienteEditView(LoginRequiredMixin, View):
    def get(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk)
        return render(request, 'clientes/form.html', {
            'form': ClienteForm(instance=cliente),
            'cliente': cliente,
        })

    def post(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk)
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            return redirect('clientes:detail', pk=pk)
        return render(request, 'clientes/form.html', {
            'form': form,
            'cliente': cliente,
        })


class ClienteSearchView(LoginRequiredMixin, View):
    """Endpoint JSON para el autocomplete en formularios de consulta."""
    def get(self, request):
        q = request.GET.get('q', '').strip()
        qs = Cliente.objects.all()
        if q:
            qs = qs.filter(
                Q(razon_social__icontains=q) |
                Q(cuit__icontains=q) |
                Q(contacto__icontains=q)
            )
        data = list(qs.values('id', 'razon_social', 'cuit', 'contacto', 'telefono', 'email')[:20])
        return JsonResponse(data, safe=False)
