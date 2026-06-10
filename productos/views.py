from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from .models import Producto


class CatalogoView(LoginRequiredMixin, View):
    def get(self, request):
        q = request.GET.get('q', '').strip()
        categoria = request.GET.get('categoria', '').strip()

        categorias = (
            Producto.objects.filter(activo=True)
            .values('categoria')
            .annotate(total=Count('id'))
            .order_by('categoria')
        )

        # Sin filtro activo: redirigir a la primera categoría
        if not categoria and not q:
            primera = categorias.first()
            if primera:
                return redirect(f"{reverse('productos:catalogo')}?categoria={primera['categoria']}")

        qs = Producto.objects.filter(activo=True).order_by('nombre')
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q) |
                Q(codigo__icontains=q) |
                Q(especificaciones__icontains=q)
            )
        if categoria:
            qs = qs.filter(categoria=categoria)

        return render(request, 'productos/catalogo.html', {
            'productos': qs,
            'categorias': categorias,
            'q': q,
            'categoria_activa': categoria,
            'total': qs.count(),
        })


class ProductoDetailView(LoginRequiredMixin, View):
    def get(self, request, pk):
        producto = get_object_or_404(Producto, pk=pk, activo=True)
        return render(request, 'productos/detail.html', {'producto': producto})
