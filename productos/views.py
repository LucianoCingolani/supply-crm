from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from accounts.mixins import GerenteRequiredMixin
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


class ProductoEditView(GerenteRequiredMixin, View):
    def get(self, request, pk):
        producto = get_object_or_404(Producto, pk=pk)
        return render(request, 'productos/edit.html', {'producto': producto})

    def post(self, request, pk):
        producto = get_object_or_404(Producto, pk=pk)

        # Precio
        precio_raw = request.POST.get('precio', '').strip()
        try:
            producto.precio = Decimal(precio_raw.replace(',', '.')) if precio_raw else None
        except InvalidOperation:
            messages.error(request, 'Precio inválido.')
            return render(request, 'productos/edit.html', {'producto': producto})

        # Nombre y especificaciones
        nombre = request.POST.get('nombre', '').strip()
        if nombre:
            producto.nombre = nombre
        producto.especificaciones = request.POST.get('especificaciones', '').strip()

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
