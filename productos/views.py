from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.views import View

from .models import Producto


class CatalogoView(LoginRequiredMixin, View):
    def get(self, request):
        qs = Producto.objects.filter(activo=True).order_by('categoria', 'nombre')

        q = request.GET.get('q', '').strip()
        categoria = request.GET.get('categoria', '').strip()

        if q:
            qs = qs.filter(
                Q(nombre__icontains=q) |
                Q(codigo__icontains=q) |
                Q(especificaciones__icontains=q)
            )
        if categoria:
            qs = qs.filter(categoria=categoria)

        # categorías con cantidad para el sidebar
        from django.db.models import Count
        categorias = (
            Producto.objects.filter(activo=True)
            .values('categoria')
            .annotate(total=Count('id'))
            .order_by('categoria')
        )

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
