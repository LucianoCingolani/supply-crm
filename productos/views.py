from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from accounts.mixins import CapacidadRequeridaMixin
from .forms import ProductoForm
from .models import MONEDAS, UNIDADES_MEDIDA, Producto


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
    def get(self, request, pk):
        producto = get_object_or_404(Producto, pk=pk, activo=True)
        return render(request, 'productos/detail.html', {'producto': producto})


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


class ProductoEditView(CapacidadRequeridaMixin, View):
    capacidad = 'puede_editar_catalogo'

    def get(self, request, pk):
        producto = get_object_or_404(Producto, pk=pk)
        return render(request, 'productos/edit.html', {
            'producto': producto,
            'unidades': UNIDADES_MEDIDA,
            'monedas': MONEDAS,
        })

    def post(self, request, pk):
        producto = get_object_or_404(Producto, pk=pk)

        # Precio
        precio_raw = request.POST.get('precio', '').strip()
        try:
            producto.precio = Decimal(precio_raw.replace(',', '.')) if precio_raw else None
        except InvalidOperation:
            messages.error(request, 'Precio inválido.')
            return render(request, 'productos/edit.html',
                          {'producto': producto, 'unidades': UNIDADES_MEDIDA})

        # Nombre y especificaciones
        nombre = request.POST.get('nombre', '').strip()
        if nombre:
            producto.nombre = nombre
        producto.especificaciones = request.POST.get('especificaciones', '').strip()

        unidad = request.POST.get('unidad_medida', '').strip()
        if unidad in dict(UNIDADES_MEDIDA) or unidad == '':
            producto.unidad_medida = unidad

        moneda = request.POST.get('moneda', '').strip()
        if moneda in dict(MONEDAS):
            producto.moneda = moneda

        # Foto: solo reemplazar si se subió un archivo nuevo
        foto_file = request.FILES.get('foto')
        if foto_file:
            producto.foto = foto_file.read()
            producto.foto_tipo = foto_file.content_type or 'image/jpeg'

        # Opción para borrar la foto actual
        elif request.POST.get('borrar_foto'):
            producto.foto = None
            producto.foto_tipo = ''

        producto.save()
        messages.success(request, f'Producto "{producto.nombre}" actualizado.')
        return redirect('productos:detail', pk=pk)
