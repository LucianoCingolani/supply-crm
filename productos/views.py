from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import Length
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from accounts.mixins import CapacidadRequeridaMixin
from .forms import ProductoForm
from .models import MONEDAS, Categoria, Producto


def categorias_existentes():
    """Todas las categorías, incluidas las que todavía no tienen artículos."""
    return Categoria.objects.all()


class CatalogoView(LoginRequiredMixin, View):
    """El catálogo, con el buscador global y las categorías al costado.

    Antes entrabas y caías en la primera categoría, y el buscador se limitaba a
    la que tuvieras abierta: para encontrar un artículo había que acertar la
    categoría primero. Ahora arranca en «Todos» y se busca sobre los 740; la
    categoría pasó a ser un filtro que se aplica sobre lo buscado.
    """

    POR_PAGINA = 60

    def get(self, request):
        q = request.GET.get('q', '').strip()
        categoria = request.GET.get('categoria', '').strip()

        encontrados = self.buscar(q)
        qs = encontrados.filter(categoria__nombre=categoria) if categoria else encontrados
        pagina = self.paginar(request, qs)
        total = pagina.paginator.count

        return render(request, 'productos/catalogo.html', {
            'pagina': pagina,
            # Las categorías se cuentan sobre lo buscado, así el costado dice en
            # qué secciones cayeron los resultados y sirve para acotarlos.
            'categorias': self.categorias(encontrados),
            'q': q,
            'categoria_activa': categoria,
            'total': total,
            # Sin categoría abierta es el mismo COUNT que ya hizo el paginador.
            'total_general': encontrados.count() if categoria else total,
        })

    def buscar(self, q):
        qs = Producto.objects.filter(activo=True)
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q) |
                Q(codigo__icontains=q) |
                Q(especificaciones__icontains=q)
            )
        return qs

    def categorias(self, encontrados):
        """Las categorías presentes en el resultado, con cuántos cayó en cada una.

        Se arma sobre el resultado y no sobre la tabla de categorías: sin
        búsqueda son todas las que tienen artículos, y con búsqueda quedan solo
        las que tienen algo que mostrar.
        """
        filas = (encontrados
                 .exclude(categoria=None)
                 .values('categoria__nombre')
                 .annotate(total=Count('id'))
                 .order_by('categoria__nombre'))
        return [{'nombre': f['categoria__nombre'], 'total': f['total']}
                for f in filas]

    def paginar(self, request, qs):
        """Una página de tarjetas, sin traerse las fotos.

        Las fotos pesan medio mega cada una y las sirve `consultas:producto_foto`
        a pedido del browser, así que acá alcanza con saber si el artículo tiene
        una: traer los binarios de sesenta artículos para decidir si mostrar un
        ícono son cuarenta megas al horno.
        """
        qs = (qs.only('codigo', 'nombre', 'precio', 'moneda', 'updated_at')
                .annotate(bytes_de_foto=Length('foto'))
                .order_by('nombre'))
        return Paginator(qs, self.POR_PAGINA).get_page(request.GET.get('pagina'))


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


class ProductoFotoBorrarView(CapacidadRequeridaMixin, View):
    """Borra la imagen de un artículo, sin tocar el resto de la ficha.

    Antes era un tilde dentro del formulario que además había que guardar, y el
    botón de guardar está al pie de la otra columna: se tildaba, no pasaba nada
    visible y parecía que no funcionaba. Ahora borra al apretarlo. Solo POST,
    así ningún prefetch ni un link mal pegado se lleva una foto puesta.
    """

    capacidad = 'puede_editar_catalogo'

    def post(self, request, pk):
        producto = get_object_or_404(Producto, pk=pk, activo=True)
        if producto.foto:
            producto.foto = None
            producto.foto_tipo = ''
            # updated_at entra a mano: versiona la URL de la foto, que es lo
            # que saca del caché del browser a la que acabamos de borrar.
            producto.save(update_fields=['foto', 'foto_tipo', 'updated_at'])
            messages.success(request, 'Imagen borrada.')
        else:
            messages.info(request, 'Ese artículo no tenía imagen.')
        return redirect('productos:detail', pk=pk)


class ProductoBorrarView(CapacidadRequeridaMixin, View):
    """Saca un artículo del catálogo, de los mismos roles que lo editan.

    Es una baja, no un DELETE. Las cotizaciones ya emitidas siguen citando el
    artículo —la línea guarda su propia descripción y precio, pero la foto y la
    ficha las saca de acá— y volver a cargar una foto de medio mega con sus
    especificaciones cuesta bastante más que un click de más. Así que el
    artículo deja de aparecer en todas las pantallas y se puede reactivar.
    """

    capacidad = 'puede_editar_catalogo'

    def get(self, request, pk):
        producto = self.get_producto(pk)
        return render(request, 'productos/confirmar_borrado.html', {
            'producto': producto,
            'cotizaciones': self.cotizaciones(producto),
        })

    def post(self, request, pk):
        producto = self.get_producto(pk)
        producto.activo = False
        # auto_now no corre si updated_at no entra en update_fields.
        producto.save(update_fields=['activo', 'updated_at'])
        messages.success(
            request,
            f'"{producto.nombre}" salió del catálogo. Si hace falta, se '
            f'reactiva desde Dados de baja.')
        return redirect('productos:catalogo')

    def get_producto(self, pk):
        return get_object_or_404(Producto, pk=pk, activo=True)

    def cotizaciones(self, producto):
        """En cuántas cotizaciones figura, para decirlo antes de dar de baja."""
        # Local: `productos` es la capa de abajo y no importa `consultas`.
        from consultas.models import Consulta
        return (Consulta.objects
                .filter(lineas__producto=producto)
                .distinct()
                .count())


class BajasView(CapacidadRequeridaMixin, View):
    """Los artículos dados de baja, para poder devolverlos al catálogo.

    Sin esta pantalla la baja sería irreversible desde la web —el artículo
    inactivo no entra ni a su propia ficha— y quedaría solo el admin de Django.
    """

    capacidad = 'puede_editar_catalogo'

    def get(self, request):
        return render(request, 'productos/bajas.html', {'productos': self.dados_de_baja()})

    def post(self, request):
        producto = get_object_or_404(
            Producto, pk=request.POST.get('producto'), activo=False)
        producto.activo = True
        producto.save(update_fields=['activo', 'updated_at'])
        messages.success(request, f'"{producto.nombre}" volvió al catálogo.')
        return redirect('productos:bajas')

    def dados_de_baja(self):
        return (Producto.objects
                .filter(activo=False)
                .select_related('categoria')
                .only('codigo', 'nombre', 'precio', 'moneda', 'updated_at',
                      'categoria__nombre')
                .order_by('nombre'))

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
            qs = qs.filter(categoria__nombre=categoria)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(codigo__icontains=q))
        # only() para no arrastrar la foto binaria de cada artículo.
        # select_related porque la tabla muestra el nombre de la categoría en
        # cada una de las cien filas; sin él es una consulta por fila.
        qs = qs.select_related('categoria').only(
            'codigo', 'nombre', 'categoria__nombre', 'precio', 'moneda',
            'unidad_medida', 'updated_at').order_by('categoria__nombre', 'nombre')
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


class CategoriasView(CapacidadRequeridaMixin, View):
    """Administración de las secciones del catálogo.

    Existe para que el gerente no dependa de nadie para agregar una categoría
    nueva, y para poder arreglar las que quedaron mal escritas sin entrar
    artículo por artículo.
    """

    capacidad = 'puede_editar_catalogo'

    ACCIONES = ('crear', 'renombrar', 'borrar', 'mover')

    def get(self, request):
        return render(request, 'productos/categorias.html', self.contexto(request))

    def post(self, request):
        accion = request.POST.get('accion')
        if accion not in self.ACCIONES:
            messages.error(request, 'Acción desconocida.')
        else:
            getattr(self, f'_{accion}')(request)
        return redirect(f'{reverse("productos:categorias")}?{request.GET.urlencode()}')

    # ── Acciones ───────────────────────────────────────────────────

    def _crear(self, request):
        nombre = request.POST.get('nombre', '').strip()
        if not nombre:
            messages.error(request, 'Escribí un nombre para la categoría.')
            return
        if Categoria.objects.filter(nombre__iexact=nombre).exists():
            messages.error(request, f'Ya existe una categoría "{nombre}".')
            return
        Categoria.objects.create(nombre=nombre)
        messages.success(
            request,
            f'Categoría "{nombre}" creada. Todavía no tiene artículos, así que no '
            f'aparece en el catálogo hasta que le asignes alguno.')

    def _renombrar(self, request):
        categoria = self._categoria(request)
        nombre = request.POST.get('nombre', '').strip()
        if categoria is None or not nombre:
            messages.error(request, 'Elegí una categoría y escribí el nombre nuevo.')
            return
        if (Categoria.objects.filter(nombre__iexact=nombre)
                .exclude(pk=categoria.pk).exists()):
            messages.error(
                request,
                f'Ya existe otra categoría "{nombre}". Para juntarlas, mové sus '
                f'artículos y después borrá la que quede vacía.')
            return
        anterior = categoria.nombre
        categoria.nombre = nombre
        categoria.save(update_fields=['nombre'])
        messages.success(request, f'"{anterior}" ahora se llama "{nombre}".')

    def _borrar(self, request):
        categoria = self._categoria(request)
        if categoria is None:
            return
        # SET_NULL: los artículos no se van con ella, quedan sin clasificar.
        cuantos = categoria.productos.count()
        nombre = categoria.nombre
        categoria.delete()
        messages.success(
            request,
            f'Categoría "{nombre}" borrada.'
            + (f' Sus {cuantos} artículo(s) quedaron sin clasificar.' if cuantos else ''))

    def _mover(self, request):
        """Mueve los artículos tildados a la categoría elegida."""
        categoria = self._categoria(request)
        if categoria is None:
            return
        ids = request.POST.getlist('producto')
        if not ids:
            messages.error(request, 'No tildaste ningún artículo.')
            return
        movidos = Producto.objects.filter(pk__in=ids).update(
            categoria=categoria, updated_at=timezone.now())
        messages.success(
            request,
            f'{movidos} artículo(s) movidos a "{categoria.nombre}".')

    def _categoria(self, request):
        categoria = Categoria.objects.filter(pk=request.POST.get('categoria')).first()
        if categoria is None:
            messages.error(request, 'No encontré esa categoría.')
        return categoria

    # ── Armado de la pantalla ──────────────────────────────────────

    def contexto(self, request):
        categorias = (
            Categoria.objects
            .annotate(total=Count('productos'))
            .order_by('nombre')
        )
        # La categoría abierta: se ven sus artículos y los de al lado, para poder
        # traer los que le faltan sin salir de la pantalla.
        abierta = Categoria.objects.filter(pk=request.GET.get('abierta')).first()
        return {
            'categorias': categorias,
            'abierta': abierta,
            'miembros': self._miembros(abierta),
            'articulos': self._articulos(request, abierta),
            'q': request.GET.get('q', '').strip(),
            'sin_clasificar': Producto.objects.filter(
                activo=True, categoria=None).count(),
        }

    def _miembros(self, abierta):
        """Lo que la categoría abierta ya tiene adentro, para poder revisarlo."""
        if abierta is None:
            return None
        return abierta.productos.order_by('nombre')

    def _articulos(self, request, abierta):
        """Los artículos que se ofrecen para mover a la categoría abierta.

        Sin filtro son los que no la tienen todavía —moverle uno que ya está no
        hace nada— y el buscador acota, porque el catálogo tiene 740.
        """
        if abierta is None:
            return None
        qs = (Producto.objects.filter(activo=True)
              .exclude(categoria=abierta)
              .select_related('categoria'))
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(codigo__icontains=q))
        else:
            # Sin búsqueda, lo primero que se quiere ver son los sin clasificar.
            qs = qs.filter(categoria=None)
        return qs.order_by('categoria__nombre', 'nombre')[:200]


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


