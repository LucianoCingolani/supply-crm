from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from accounts.mixins import GerenteRequiredMixin
from .forms import ConsultaForm, FiltroConsultaForm, SeguimientoForm
from .models import Consulta


class ConsultaListView(LoginRequiredMixin, View):
    def get(self, request):
        qs = self._get_queryset(request)
        filtro = FiltroConsultaForm(request.GET)

        if filtro.is_valid():
            if filtro.cleaned_data['estado']:
                qs = qs.filter(estado=filtro.cleaned_data['estado'])
            if filtro.cleaned_data['via_entrada']:
                qs = qs.filter(via_entrada=filtro.cleaned_data['via_entrada'])
            if filtro.cleaned_data['buscar']:
                q = filtro.cleaned_data['buscar']
                qs = qs.filter(
                    Q(razon_social__icontains=q) |
                    Q(contacto__icontains=q) |
                    Q(productos__icontains=q) |
                    Q(numero_cotizacion__icontains=q)
                )

        # Filtro por vendedor (solo gerente puede filtrar por otros)
        vendedor_id = request.GET.get('vendedor')
        if request.user.is_gerente and vendedor_id:
            qs = qs.filter(vendedor_id=vendedor_id)

        return render(request, 'consultas/list.html', {
            'consultas': qs.select_related('vendedor'),
            'filtro': filtro,
            'total': qs.count(),
        })

    def _get_queryset(self, request):
        if request.user.is_gerente:
            return Consulta.objects.all()
        return Consulta.objects.filter(vendedor=request.user)


class ConsultaCreateView(LoginRequiredMixin, View):
    def get(self, request):
        form = ConsultaForm(initial={'fecha': __import__('datetime').date.today()})
        return render(request, 'consultas/form.html', {'form': form, 'title': 'Nueva consulta'})

    def post(self, request):
        form = ConsultaForm(request.POST)
        if form.is_valid():
            consulta = form.save(commit=False)
            consulta.vendedor = request.user
            consulta.save()
            messages.success(request, 'Consulta registrada.')
            return redirect('consultas:detail', pk=consulta.pk)
        return render(request, 'consultas/form.html', {'form': form, 'title': 'Nueva consulta'})


class ConsultaDetailView(LoginRequiredMixin, View):
    def get_consulta(self, request, pk):
        qs = Consulta.objects.all() if request.user.is_gerente else Consulta.objects.filter(vendedor=request.user)
        return get_object_or_404(qs.prefetch_related('logs__user'), pk=pk)

    def get(self, request, pk):
        consulta = self.get_consulta(request, pk)
        return render(request, 'consultas/detail.html', {
            'consulta': consulta,
            'seg_form': SeguimientoForm(),
        })

    def post(self, request, pk):
        consulta = self.get_consulta(request, pk)
        form = SeguimientoForm(request.POST)
        if form.is_valid():
            log = form.save(commit=False)
            log.consulta = consulta
            log.user = request.user
            log.save()
            messages.success(request, 'Seguimiento registrado.')
        return redirect('consultas:detail', pk=pk)


class ConsultaEditView(LoginRequiredMixin, View):
    def get_consulta(self, request, pk):
        qs = Consulta.objects.all() if request.user.is_gerente else Consulta.objects.filter(vendedor=request.user)
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        consulta = self.get_consulta(request, pk)
        return render(request, 'consultas/form.html', {
            'form': ConsultaForm(instance=consulta),
            'title': f'Editar consulta',
            'consulta': consulta,
        })

    def post(self, request, pk):
        consulta = self.get_consulta(request, pk)
        form = ConsultaForm(request.POST, instance=consulta)
        if form.is_valid():
            form.save()
            messages.success(request, 'Consulta actualizada.')
            return redirect('consultas:detail', pk=pk)
        return render(request, 'consultas/form.html', {
            'form': form,
            'title': 'Editar consulta',
            'consulta': consulta,
        })
