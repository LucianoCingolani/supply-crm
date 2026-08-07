from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from accounts.mixins import CapacidadRequeridaMixin
from .forms import ProductoForm
from .models import Producto


def categorias_existentes():
    """Categorías ya en uso, para sugerirlas en el alta."""
    return (
        Producto.objects.exclude(categoria='')
        .values_list('categoria', flat=True)
        .distinct()
        .order_by('categoria')
    )


class CatalogoView(LoginRequiredMixin, View):
    def get(self, request):
        q = request.GET.get('q', '').strip()
        categoria = request.GET.get('categoria', '').strip()

        # Se excluyen las categorías vacías: no son navegables y, si quedaran
        # primeras, el redirect de abajo entraría en loop.
        categorias = (
            Producto.objects.filter(activo=True)
            .exclude(categoria='')
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
    """La ficha del artículo. Para quien puede editar el catálogo, es además el
    formulario: corregir un precio o una categoría no debería costar dos
    pantallas, y con 740 artículos importados sin clasificar, menos todavía.
    """

    def get(self, request, pk):
        return self.render_ficha(request, self.get_producto(pk))

    def post(self, request, pk):
        producto = self.get_producto(pk)
        if not request.user.puede_editar_catalogo:
            messages.error(request, 'No tenés permisos para editar el catálogo.')
            return redirect('productos:detail', pk=pk)

        form = ProductoForm(request.POST, request.FILES, instance=producto, edicion=True)
        if not form.is_valid():
            return self.render_ficha(request, producto, form)
        form.save()
        messages.success(request, 'Artículo actualizado.')
        return redirect('productos:detail', pk=pk)

    def get_producto(self, pk):
        return get_object_or_404(Producto, pk=pk, activo=True)

    def render_ficha(self, request, producto, form=None):
        puede_editar = request.user.puede_editar_catalogo
        if puede_editar and form is None:
            form = ProductoForm(instance=producto, edicion=True)
        return render(request, 'productos/detail.html', {
            'producto': producto,
            'puede_editar': puede_editar,
            'form': form if puede_editar else None,
            'categorias': categorias_existentes() if puede_editar else None,
        })


class ProductoCreateView(CapacidadRequeridaMixin, View):
    """Alta manual de un artículo, para lo que no viene en el Excel de Enexpro."""

    capacidad = 'puede_editar_catalogo'

    def get(self, request):
        return self.render_form(request, ProductoForm())

    def post(self, request):
        form = ProductoForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.render_form(request, form)
        producto = form.save()
        messages.success(request, f'Artículo "{producto.nombre}" creado.')
        return redirect('productos:detail', pk=producto.pk)

    def render_form(self, request, form):
        return render(request, 'productos/form.html', {
            'form': form,
            'categorias': categorias_existentes(),
        })


