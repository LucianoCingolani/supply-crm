import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views import View

from accounts.mixins import VentasRequeridasMixin
from clientes.models import Cliente, normalizar_cuit
from productos.models import ARS, MONEDAS, Producto
from . import membrete
from .forms import ConsultaClienteForm, FiltroConsultaForm, SeguimientoForm
from .models import Consulta, LineaCotizacion

MONEDAS_VALIDAS = dict(MONEDAS)


def moneda_valida(valor, por_defecto=ARS):
    return valor if valor in MONEDAS_VALIDAS else por_defecto


def leer_tipo_cambio(request):
    """(valor, ok). El vacío es válido: significa 'todavía no lo sé'."""
    crudo = request.POST.get('tipo_cambio', '').strip().replace(',', '.')
    if not crudo:
        return None, True
    try:
        valor = Decimal(crudo)
    except InvalidOperation:
        return None, False
    return (valor, True) if valor > 0 else (None, False)


def categorias_de(productos):
    """Los nombres de las categorías en uso, ordenados y sin repetir."""
    return sorted({p.categoria.nombre for p in productos if p.categoria_id},
                  key=str.lower)


def productos_para_selector(productos):
    """Los datos que el selector necesita del lado del navegador.

    Se entrega como lista y el template la serializa con json_script, que se
    encarga del escapado.
    """
    return [
        {
            'id': p.pk,
            'codigo': p.codigo,
            'nombre': p.nombre,
            'categoria': p.categoria.nombre if p.categoria_id else '',
            'precio': float(p.precio) if p.precio else 0,
            'moneda': p.moneda,
        }
        for p in productos
    ]


class ConsultaAccesoMixin(VentasRequeridasMixin):
    """Da acceso solo a las consultas visibles para el usuario."""

    def get_consultas(self):
        return Consulta.objects.visibles_para(self.request.user)

    def get_consulta(self, pk, *prefetch):
        qs = self.get_consultas()
        if prefetch:
            qs = qs.prefetch_related(*prefetch)
        return get_object_or_404(qs, pk=pk)


class ConsultaListView(ConsultaAccesoMixin, View):
    def get(self, request):
        qs = self.get_consultas()
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

        # Filtro por vendedor (solo quien ve todas las consultas puede filtrar por otros)
        vendedor_id = request.GET.get('vendedor', '')
        vendedores = None
        if request.user.puede_ver_todas_las_consultas:
            vendedores = get_user_model().objects.filter(
                is_active=True, consultas__isnull=False,
            ).distinct().order_by('last_name', 'first_name')
            if vendedor_id.isdigit():
                qs = qs.filter(vendedor_id=vendedor_id)

        consultas = list(qs.select_related('vendedor', 'cliente'))
        return render(request, 'consultas/list.html', {
            'consultas': consultas,
            'filtro': filtro,
            'total': len(consultas),
            'vendedores': vendedores,
            'vendedor_activo': vendedor_id,
        })


class ConsultaDetailView(ConsultaAccesoMixin, View):
    def get(self, request, pk):
        consulta = self.get_consulta(pk, 'logs__user')
        return render(request, 'consultas/detail.html', {
            'consulta': consulta,
            'seg_form': SeguimientoForm(),
        })

    def post(self, request, pk):
        consulta = self.get_consulta(pk)
        form = SeguimientoForm(request.POST)
        if form.is_valid():
            log = form.save(commit=False)
            log.consulta = consulta
            log.cliente = consulta.cliente   # también entra en la línea de tiempo del cliente
            log.user = request.user
            log.save()
            messages.success(request, 'Seguimiento registrado.')
        return redirect('consultas:detail', pk=pk)


class ConsultaEditView(ConsultaAccesoMixin, View):
    """Edita los datos de la consulta. El cliente no se toca acá: se edita en su ficha."""

    exige_carga = True

    def get(self, request, pk):
        consulta = self.get_consulta(pk)
        return render(request, 'consultas/form.html', {
            'form': ConsultaClienteForm(instance=consulta),
            'title': 'Editar consulta',
            'consulta': consulta,
            'cliente': consulta.cliente,
        })

    def post(self, request, pk):
        consulta = self.get_consulta(pk)
        form = ConsultaClienteForm(request.POST, instance=consulta)
        if form.is_valid():
            form.save()
            messages.success(request, 'Consulta actualizada.')
            return redirect('consultas:detail', pk=pk)
        return render(request, 'consultas/form.html', {
            'form': form,
            'title': 'Editar consulta',
            'consulta': consulta,
            'cliente': consulta.cliente,
        })


class CotizacionView(ConsultaAccesoMixin, View):
    def get(self, request, pk):
        consulta = self.get_consulta(pk, 'lineas__producto')
        productos = (Producto.objects.filter(activo=True)
                     .select_related('categoria')
                     .order_by('categoria__nombre', 'nombre'))
        # Esta pantalla arma el selector en el template, con las opciones
        # agrupadas por categoría; no necesita los productos en JSON.
        return render(request, 'consultas/cotizacion.html', {
            'consulta': consulta,
            'productos': productos,
            'monedas': MONEDAS,
            'totales': consulta.totales(),
        })

    def post(self, request, pk):
        consulta = self.get_consulta(pk)
        action = request.POST.get('action')

        if action == 'add':
            descripcion = request.POST.get('descripcion', '').strip()
            try:
                cantidad = Decimal(request.POST.get('cantidad', '1'))
                precio = Decimal(request.POST.get('precio_unitario', '0'))
            except InvalidOperation:
                messages.error(request, 'Cantidad o precio inválido.')
                return redirect('consultas:cotizacion', pk=pk)
            if not descripcion or precio <= 0:
                messages.error(request, 'Completá descripción y precio.')
                return redirect('consultas:cotizacion', pk=pk)
            linea = LineaCotizacion(
                consulta=consulta, descripcion=descripcion,
                cantidad=cantidad, precio_unitario=precio,
                moneda=moneda_valida(request.POST.get('moneda'), consulta.moneda),
            )
            prod_id = request.POST.get('producto_id')
            if prod_id:
                linea.producto = Producto.objects.filter(pk=prod_id).first()
            linea.save()

        elif action == 'delete':
            LineaCotizacion.objects.filter(consulta=consulta, pk=request.POST.get('linea_id')).delete()

        elif action == 'moneda':
            tipo_cambio, ok = leer_tipo_cambio(request)
            if not ok:
                messages.error(request, 'Tipo de cambio inválido.')
                return redirect('consultas:cotizacion', pk=pk)
            consulta.moneda = moneda_valida(request.POST.get('moneda'), consulta.moneda)
            consulta.tipo_cambio = tipo_cambio
            consulta.save(update_fields=['moneda', 'tipo_cambio', 'updated_at'])

        return redirect('consultas:cotizacion', pk=pk)


class CotizacionPDFView(ConsultaAccesoMixin, View):
    def get(self, request, pk):
        consulta = self.get_consulta(pk, 'lineas__producto')

        # El PDF ya no imprime totales, pero sí el precio de cada línea llevado
        # a la moneda de la cotización. Sin tipo de cambio esa conversión no se
        # puede hacer, y un precio en blanco o mal convertido va al cliente.
        if consulta.totales() is None:
            messages.error(
                request,
                'La cotización mezcla pesos y dólares. Cargá el tipo de cambio '
                'para poder generar el PDF.',
            )
            return redirect('consultas:cotizacion', pk=pk)

        html = render_to_string('consultas/cotizacion_pdf.html', {
            'consulta': consulta,
            'request': request,
            **membrete.contexto(),
        })
        import weasyprint
        pdf_bytes = weasyprint.HTML(string=html).write_pdf()

        nombre = f"Cotizacion_{consulta.numero_cotizacion or consulta.pk}.pdf"
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return response


class ClienteScopeMixin(VentasRequeridasMixin):
    """Vistas que arrancan de un cliente de la cartera del usuario."""

    def get_cliente(self, pk):
        return get_object_or_404(Cliente.objects.visibles_para(self.request.user), pk=pk)


def copiar_datos_del_cliente(consulta, cliente):
    """La Consulta guarda una copia de los datos del cliente al momento de cargarla.

    Arrancando desde el cliente no hace falta tipearlos: se copian de la ficha.
    """
    consulta.cliente = cliente
    consulta.razon_social = cliente.razon_social
    consulta.contacto = cliente.contacto
    consulta.cuit = cliente.cuit
    consulta.telefono = cliente.telefono
    consulta.email = cliente.email
    return consulta


class ConsultaCreateParaClienteView(ClienteScopeMixin, View):
    """Registra una consulta sobre un cliente ya elegido."""

    exige_carga = True

    def get(self, request, cliente_pk):
        import datetime
        cliente = self.get_cliente(cliente_pk)
        return render(request, 'consultas/form.html', {
            'form': ConsultaClienteForm(initial={'fecha': datetime.date.today()}),
            'title': 'Nueva consulta',
            'cliente': cliente,
        })

    def post(self, request, cliente_pk):
        cliente = self.get_cliente(cliente_pk)
        form = ConsultaClienteForm(request.POST)
        if form.is_valid():
            consulta = copiar_datos_del_cliente(form.save(commit=False), cliente)
            consulta.vendedor = request.user
            consulta.save()
            messages.success(request, 'Consulta registrada.')
            return redirect('consultas:detail', pk=consulta.pk)
        return render(request, 'consultas/form.html', {
            'form': form,
            'title': 'Nueva consulta',
            'cliente': cliente,
        })


class ClienteRapidoView(VentasRequeridasMixin, View):
    """Alta mínima de cliente desde el modal de "Nueva consulta".

    Solo lo necesario para arrancar la consulta; el resto de la ficha se
    completa después. Termina en la pantalla de productos de ese cliente, que
    es a dónde iba el que apretó el botón.
    """

    exige_carga = True

    CAMPOS = ['cuit', 'razon_social', 'contacto', 'telefono', 'whatsapp', 'email']

    def post(self, request):
        datos = {campo: request.POST.get(campo, '').strip() for campo in self.CAMPOS}
        if not datos['razon_social']:
            messages.error(request, 'La razón social es obligatoria para cargar el cliente.')
            return redirect('consultas:list')

        cuit = normalizar_cuit(datos['cuit'])
        if cuit:
            # Si ya está cargado no se duplica: se sigue con la ficha que existe.
            # Cargar dos veces al mismo cliente es el error que más se comete acá.
            existente = Cliente.objects.filter(cuit=cuit).first()
            if existente:
                return self._seguir_con_el_existente(request, existente)

        cliente = Cliente(**{**datos, 'cuit': cuit})
        # El que lo trae se lo queda, salvo que reparta cartera: si no, lo carga
        # y lo pierde de vista en el mismo movimiento.
        if not request.user.puede_asignar_clientes:
            cliente.vendedor = request.user
        cliente.save()
        messages.success(request, f'Cliente "{cliente.razon_social}" creado.')
        return redirect('consultas:nueva_cotizacion', cliente_pk=cliente.pk)

    def _seguir_con_el_existente(self, request, cliente):
        visible = Cliente.objects.visibles_para(request.user).filter(pk=cliente.pk).exists()
        if not visible:
            messages.error(
                request,
                f'"{cliente.razon_social}" ya está cargado con ese CUIT, pero en la '
                f'cartera de otro vendedor. Pedile al gerente que te lo asigne.',
            )
            return redirect('consultas:list')
        messages.info(
            request,
            f'"{cliente.razon_social}" ya estaba cargado con ese CUIT. '
            f'Seguimos con su ficha.',
        )
        return redirect('consultas:nueva_cotizacion', cliente_pk=cliente.pk)


class NuevaCotizacionView(ClienteScopeMixin, View):
    """Cotiza a un cliente de la cartera: arma la Consulta en el fondo."""

    exige_carga = True

    def _render(self, request, cliente, fecha_str=None, post=None):
        import datetime
        productos = list(Producto.objects.filter(activo=True)
                         .select_related('categoria')
                         .order_by('categoria__nombre', 'nombre'))
        return render(request, 'consultas/nueva_cotizacion.html', {
            'cliente': cliente,
            'productos': productos,
            'productos_data': productos_para_selector(productos),
            'categorias': categorias_de(productos),
            'hoy': fecha_str or datetime.date.today().isoformat(),
            'monedas': MONEDAS,
            'post': post,
        })

    def get(self, request, cliente_pk):
        return self._render(request, self.get_cliente(cliente_pk))

    def post(self, request, cliente_pk):
        import datetime
        cliente = self.get_cliente(cliente_pk)

        nro_cot = request.POST.get('numero_cotizacion', '').strip()
        fecha_str = request.POST.get('fecha', '')
        via = request.POST.get('via_entrada', 'mail')
        try:
            fecha = datetime.date.fromisoformat(fecha_str)
        except (ValueError, TypeError):
            fecha = datetime.date.today()

        moneda = moneda_valida(request.POST.get('moneda'))
        tipo_cambio, tc_ok = leer_tipo_cambio(request)
        if not tc_ok:
            messages.error(request, 'Tipo de cambio inválido.')
            return self._render(request, cliente, fecha_str, request.POST)

        lineas = self._leer_lineas(request, moneda)
        if not lineas:
            messages.error(request, 'Agregá al menos un producto a la cotización.')
            return self._render(request, cliente, fecha_str, request.POST)

        if any(l['moneda'] != moneda for l in lineas) and not tipo_cambio:
            messages.error(
                request,
                'Hay productos en otra moneda que la de la cotización: cargá el tipo de cambio.',
            )
            return self._render(request, cliente, fecha_str, request.POST)

        consulta = copiar_datos_del_cliente(
            Consulta(
                fecha=fecha,
                # El primer producto describe la consulta.
                productos=lineas[0]['descripcion'][:300],
                numero_cotizacion=nro_cot,
                via_entrada=via,
                estado=Consulta.COTIZADO,
                moneda=moneda,
                tipo_cambio=tipo_cambio,
                vendedor=request.user,
            ),
            cliente,
        )
        consulta.save()

        for orden, l in enumerate(lineas):
            LineaCotizacion.objects.create(
                consulta=consulta,
                descripcion=l['descripcion'],
                cantidad=l['cantidad'],
                precio_unitario=l['precio_unitario'],
                moneda=l['moneda'],
                orden=orden,
                producto=Producto.objects.filter(pk=l['producto_id']).first()
                if l['producto_id'] else None,
            )

        return redirect('consultas:cotizacion', pk=consulta.pk)

    def _leer_lineas(self, request, moneda_cotizacion):
        """Las líneas llegan como campos indexados: linea_desc_0, linea_cant_0, ..."""
        lineas, i = [], 0
        while True:
            desc = request.POST.get(f'linea_desc_{i}', '').strip()
            cant = request.POST.get(f'linea_cant_{i}', '')
            precio = request.POST.get(f'linea_precio_{i}', '')
            if not desc and not cant:
                break
            try:
                cant_d, precio_d = Decimal(cant), Decimal(precio)
            except InvalidOperation:
                i += 1
                continue
            if desc and cant_d > 0 and precio_d > 0:
                lineas.append({
                    'descripcion': desc,
                    'cantidad': cant_d,
                    'precio_unitario': precio_d,
                    'moneda': moneda_valida(request.POST.get(f'linea_moneda_{i}'), moneda_cotizacion),
                    'producto_id': request.POST.get(f'linea_prod_{i}', ''),
                })
            i += 1
        return lineas


class ProductoFotoView(LoginRequiredMixin, View):
    """Sirve la foto binaria de un producto con caché de 7 días en el browser."""
    def get(self, request, pk):
        producto = get_object_or_404(Producto, pk=pk)
        if not producto.foto:
            from django.http import Http404
            raise Http404
        response = HttpResponse(bytes(producto.foto), content_type=producto.foto_tipo or 'image/jpeg')
        response['Cache-Control'] = 'private, max-age=604800'  # 7 días
        response['Vary'] = 'Cookie'
        return response
