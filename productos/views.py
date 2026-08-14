from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from accounts.mixins import CapacidadRequeridaMixin
from .forms import ProductoForm
from .models import MONEDAS, Producto


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


class PreciosView(CapacidadRequeridaMixin, View):
    """Mantenimiento de la lista de precios, sin tocar el resto de la ficha.

    Es la pantalla de Tesorería: una tabla filtrable con el precio y la moneda
    de cada artículo editables, y un solo guardado para toda la página.
    """

    capacidad = 'puede_editar_precios'
    POR_PAGINA = 100

    def get(self, request):
        return render(request, 'productos/precios.html', self.contexto(request))

    def post(self, request):
        pagina = self.pagina(request)
        productos = list(pagina)
        cambios, errores = self.leer_cambios(request, productos)

        # Todo o nada: con cien filas en pantalla, guardar la mitad y dejar la
        # otra sin avisar es peor que no guardar nada.
        if errores:
            messages.error(
                request,
                'No se guardó nada. Revisá el precio de: ' + ', '.join(errores) + '.')
            return render(request, 'productos/precios.html',
                          self.contexto(request, pagina, productos, errores))

        if cambios:
            Producto.objects.bulk_update(
                cambios, ['precio', 'moneda', 'updated_at'], batch_size=200)
            messages.success(
                request,
                f'{len(cambios)} precio{"s" if len(cambios) != 1 else ""} actualizado'
                f'{"s" if len(cambios) != 1 else ""}.')
        else:
            messages.info(request, 'No había ningún cambio para guardar.')
        return redirect(f'{reverse("productos:precios")}?{request.GET.urlencode()}')

    # ── Lectura del formulario ─────────────────────────────────────

    def leer_cambios(self, request, productos):
        """(a_guardar, códigos_con_error). Solo entra lo que efectivamente cambió.

        De paso deja en cada artículo lo que se tipeó, para poder devolver la
        pantalla tal como quedó: si una fila está mal y las otras ediciones se
        pierden, hay que rehacer el trabajo.
        """
        cambios, errores = [], []
        ahora = timezone.now()

        for producto in productos:
            crudo = request.POST.get(f'precio_{producto.pk}')
            if crudo is None:
                continue  # la fila no vino en el POST
            producto.precio_crudo = crudo

            moneda = request.POST.get(f'moneda_{producto.pk}', producto.moneda)
            if moneda not in dict(MONEDAS):
                moneda = producto.moneda

            precio, ok = self.leer_precio(crudo)
            if not ok:
                errores.append(producto.codigo)
                producto.moneda = moneda   # que el select vuelva como lo dejó
                continue
            if precio == producto.precio and moneda == producto.moneda:
                continue
            producto.precio = precio
            producto.moneda = moneda
            # bulk_update no dispara auto_now.
            producto.updated_at = ahora
            cambios.append(producto)
        return cambios, errores

    def leer_precio(self, crudo):
        """(valor, ok). Vacío es válido: significa artículo sin precio."""
        texto = (crudo or '').strip().replace(',', '.')
        if not texto:
            return None, True
        try:
            valor = Decimal(texto)
        except InvalidOperation:
            return None, False
        if valor < 0:
            return None, False
        return valor.quantize(Decimal('0.01')), True

    # ── Armado de la pantalla ──────────────────────────────────────

    def pagina(self, request):
        qs = Producto.objects.filter(activo=True)
        categoria = request.GET.get('categoria', '')
        if categoria:
            qs = qs.filter(categoria=categoria)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(codigo__icontains=q))
        # only() para no arrastrar la foto binaria de cada artículo.
        qs = qs.only('codigo', 'nombre', 'categoria', 'precio', 'moneda',
                     'unidad_medida', 'updated_at').order_by('categoria', 'nombre')
        return Paginator(qs, self.POR_PAGINA).get_page(request.GET.get('pagina'))

    def contexto(self, request, pagina=None, productos=None, errores=None):
        if pagina is None:
            pagina = self.pagina(request)
        if productos is None:
            productos = list(pagina)
        # En un GET todavía no hay nada tipeado: el campo arranca con lo guardado.
        for producto in productos:
            if not hasattr(producto, 'precio_crudo'):
                producto.precio_crudo = ('' if producto.precio is None
                                         else f'{producto.precio:.2f}')
        return {
            'pagina': pagina,
            'productos': productos,
            'errores': errores or [],
            'categorias': categorias_existentes(),
            'categoria_activa': request.GET.get('categoria', ''),
            'q': request.GET.get('q', '').strip(),
            'monedas': MONEDAS,
            'querystring': request.GET.urlencode(),
        }


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


