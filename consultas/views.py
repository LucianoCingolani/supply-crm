import json
import re
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views import View

from accounts.mixins import GerenteRequiredMixin
from productos.models import Producto
from .forms import ConsultaForm, FiltroConsultaForm, SeguimientoForm
from .models import Consulta, LineaCotizacion

def _get_or_create_cliente(cliente_id=None, razon_social='', cuit='', contacto='', telefono='', email=''):
    from clientes.models import Cliente
    razon_social = (razon_social or '').strip()
    cuit = (cuit or '').strip()

    if cliente_id:
        cliente = Cliente.objects.filter(pk=cliente_id).first()
        if cliente:
            return cliente

    if not razon_social and not cuit:
        return None

    if cuit:
        cliente = Cliente.objects.filter(cuit=cuit).first()
        if cliente:
            return cliente

    if razon_social:
        cliente = Cliente.objects.filter(razon_social__iexact=razon_social).first()
        if cliente:
            return cliente

    return Cliente.objects.create(
        razon_social=razon_social or contacto or cuit,
        contacto=(contacto or '').strip(),
        cuit=cuit,
        telefono=(telefono or '').strip(),
        email=(email or '').strip(),
    )


_MESES_ES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
}


def _es_cuit(s):
    return bool(re.match(r'^\d{2}-\d{8}-\d$', s) or re.match(r'^\d{11}$', s))


def _extraer_datos_cotizacion(pdf_file):
    import pdfplumber

    with pdfplumber.open(pdf_file) as pdf:
        text = pdf.pages[0].extract_text() or '' if pdf.pages else ''

    data = {'estado': 'cotizado', 'via_entrada': 'mail'}

    # Caso 1: dos separadores → "Cotización N — CUIT— NOMBRE" o "Cotización N — NOMBRE — CUIT"
    m = re.search(
        r'Cotizaci[oó]n\s+(\d+)\s*[—–]+\s*(.+?)\s*[—–]+\s*(.+)',
        text,
    )
    if m:
        data['numero_cotizacion'] = m.group(1)
        part_a = m.group(2).strip()
        part_b = m.group(3).strip()
        if _es_cuit(part_a):
            data['cuit'] = part_a
            data['razon_social'] = part_b
            data['contacto'] = part_b
        else:
            data['razon_social'] = part_a
            data['contacto'] = part_a
            cuit_m = re.search(r'\d{2}-\d{8}-\d|\d{11}', part_b)
            if cuit_m:
                data['cuit'] = cuit_m.group(0)
    else:
        # Caso 2: un solo separador → "Cotización N — NOMBRE" (sin CUIT)
        m = re.search(r'Cotizaci[oó]n\s+(\d+)\s*[—–]+\s*(.+)', text)
        if m:
            data['numero_cotizacion'] = m.group(1)
            razon = m.group(2).strip()
            data['razon_social'] = razon
            data['contacto'] = razon

    # "02 de junio 2026"
    m = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+(\d{4})', text, re.IGNORECASE)
    if m:
        mes = _MESES_ES.get(m.group(2).lower())
        if mes:
            data['fecha'] = f"{m.group(3)}-{mes:02d}-{int(m.group(1)):02d}"

    # Product: line immediately after the "Cotización N —..." line
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, line in enumerate(lines):
        if re.search(r'Cotizaci[oó]n\s+\d+', line) and i + 1 < len(lines):
            data['productos'] = lines[i + 1].rstrip(':')
            break

    return data


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
            consulta.cliente = _get_or_create_cliente(
                cliente_id=request.POST.get('cliente_id'),
                razon_social=form.cleaned_data.get('razon_social', ''),
                cuit=form.cleaned_data.get('cuit', ''),
                contacto=form.cleaned_data.get('contacto', ''),
                telefono=form.cleaned_data.get('telefono', ''),
                email=form.cleaned_data.get('email', ''),
            )
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
            consulta = form.save(commit=False)
            consulta.cliente = _get_or_create_cliente(
                cliente_id=request.POST.get('cliente_id'),
                razon_social=form.cleaned_data.get('razon_social', ''),
                cuit=form.cleaned_data.get('cuit', ''),
                contacto=form.cleaned_data.get('contacto', ''),
                telefono=form.cleaned_data.get('telefono', ''),
                email=form.cleaned_data.get('email', ''),
            )
            consulta.save()
            messages.success(request, 'Consulta actualizada.')
            return redirect('consultas:detail', pk=pk)
        return render(request, 'consultas/form.html', {
            'form': form,
            'title': 'Editar consulta',
            'consulta': consulta,
        })


class CotizacionView(LoginRequiredMixin, View):
    def _get_consulta(self, request, pk):
        qs = Consulta.objects.all() if request.user.is_gerente else Consulta.objects.filter(vendedor=request.user)
        return get_object_or_404(qs.prefetch_related('lineas__producto'), pk=pk)

    def get(self, request, pk):
        consulta = self._get_consulta(request, pk)
        productos = Producto.objects.filter(activo=True).order_by('categoria', 'nombre')
        productos_json = json.dumps([
            {'id': p.pk, 'nombre': p.nombre, 'precio': float(p.precio) if p.precio else 0}
            for p in productos
        ])
        total_neto = sum(l.subtotal for l in consulta.lineas.all())
        return render(request, 'consultas/cotizacion.html', {
            'consulta': consulta,
            'productos': productos,
            'productos_json': productos_json,
            'total_neto': total_neto,
            'iva': total_neto * Decimal('0.21'),
            'total_con_iva': total_neto * Decimal('1.21'),
        })

    def post(self, request, pk):
        consulta = self._get_consulta(request, pk)
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
            linea = LineaCotizacion(consulta=consulta, descripcion=descripcion,
                                    cantidad=cantidad, precio_unitario=precio)
            prod_id = request.POST.get('producto_id')
            if prod_id:
                linea.producto = Producto.objects.filter(pk=prod_id).first()
            linea.save()

        elif action == 'delete':
            LineaCotizacion.objects.filter(consulta=consulta, pk=request.POST.get('linea_id')).delete()

        return redirect('consultas:cotizacion', pk=pk)


class CotizacionPDFView(LoginRequiredMixin, View):
    def get(self, request, pk):
        qs = Consulta.objects.all() if request.user.is_gerente else Consulta.objects.filter(vendedor=request.user)
        consulta = get_object_or_404(qs.prefetch_related('lineas__producto'), pk=pk)

        total_neto = sum(l.subtotal for l in consulta.lineas.all())
        html = render_to_string('consultas/cotizacion_pdf.html', {
            'consulta': consulta,
            'total_neto': total_neto,
            'iva': total_neto * Decimal('0.21'),
            'total_con_iva': total_neto * Decimal('1.21'),
            'request': request,
        })
        import weasyprint
        pdf_bytes = weasyprint.HTML(string=html).write_pdf()

        nombre = f"Cotizacion_{consulta.numero_cotizacion or consulta.pk}.pdf"
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return response


class NuevaCotizacionView(LoginRequiredMixin, View):
    """Crea una cotización standalone: arma la Consulta en el fondo automáticamente."""

    def _productos_ctx(self):
        productos = Producto.objects.filter(activo=True).order_by('categoria', 'nombre')
        productos_json = json.dumps([
            {'id': p.pk, 'nombre': p.nombre, 'precio': float(p.precio) if p.precio else 0}
            for p in productos
        ])
        return productos, productos_json

    def get(self, request):
        import datetime
        productos, productos_json = self._productos_ctx()
        return render(request, 'consultas/nueva_cotizacion.html', {
            'productos': productos,
            'productos_json': productos_json,
            'hoy': datetime.date.today().isoformat(),
        })

    def post(self, request):
        import datetime

        # ── datos del cliente ──
        razon_social = request.POST.get('razon_social', '').strip()
        cuit         = request.POST.get('cuit', '').strip()
        contacto     = request.POST.get('contacto', '').strip()
        telefono     = request.POST.get('telefono', '').strip()
        email        = request.POST.get('email', '').strip()
        nro_cot      = request.POST.get('numero_cotizacion', '').strip()
        fecha_str    = request.POST.get('fecha', '')
        via          = request.POST.get('via_entrada', 'mail')

        try:
            fecha = datetime.date.fromisoformat(fecha_str)
        except (ValueError, TypeError):
            fecha = datetime.date.today()

        # ── líneas enviadas como campos indexados ──
        lineas = []
        i = 0
        while True:
            desc   = request.POST.get(f'linea_desc_{i}', '').strip()
            cant   = request.POST.get(f'linea_cant_{i}', '')
            precio = request.POST.get(f'linea_precio_{i}', '')
            prod_id = request.POST.get(f'linea_prod_{i}', '')
            if not desc and not cant:
                break
            try:
                cant_d   = Decimal(cant)
                precio_d = Decimal(precio)
            except InvalidOperation:
                i += 1
                continue
            if desc and cant_d > 0 and precio_d > 0:
                lineas.append({
                    'descripcion': desc,
                    'cantidad': cant_d,
                    'precio_unitario': precio_d,
                    'producto_id': prod_id or None,
                })
            i += 1

        if not lineas:
            productos, productos_json = self._productos_ctx()
            messages.error(request, 'Agregá al menos un producto a la cotización.')
            return render(request, 'consultas/nueva_cotizacion.html', {
                'productos': productos,
                'productos_json': productos_json,
                'hoy': fecha_str,
                'post': request.POST,
            })

        # ── primer producto como descripción de la Consulta ──
        desc_consulta = lineas[0]['descripcion'][:300]

        cliente = _get_or_create_cliente(
            cliente_id=request.POST.get('cliente_id'),
            razon_social=razon_social,
            cuit=cuit,
            contacto=contacto,
            telefono=telefono,
            email=email,
        )
        consulta = Consulta.objects.create(
            fecha=fecha,
            productos=desc_consulta,
            numero_cotizacion=nro_cot,
            via_entrada=via,
            razon_social=razon_social,
            contacto=contacto or razon_social,
            cuit=cuit,
            telefono=telefono,
            email=email,
            estado=Consulta.COTIZADO,
            vendedor=request.user,
            cliente=cliente,
        )

        for idx, l in enumerate(lineas):
            lc = LineaCotizacion(
                consulta=consulta,
                descripcion=l['descripcion'],
                cantidad=l['cantidad'],
                precio_unitario=l['precio_unitario'],
                orden=idx,
            )
            if l['producto_id']:
                lc.producto = Producto.objects.filter(pk=l['producto_id']).first()
            lc.save()

        return redirect('consultas:cotizacion', pk=consulta.pk)


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


class ConsultaImportPDFView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'consultas/import_pdf.html')

    def post(self, request):
        import datetime
        import pdfplumber

        # Modo debug: muestra el texto crudo del primer PDF
        if 'debug' in request.POST:
            pdf_file = request.FILES.get('pdf_file')
            if pdf_file:
                try:
                    with pdfplumber.open(pdf_file) as pdf:
                        texto = '\n--- PÁGINA {} ---\n'.join(
                            p.extract_text() or '(sin texto)' for p in pdf.pages[:3]
                        )
                except Exception as e:
                    texto = f'Error al leer: {e}'
                return render(request, 'consultas/import_pdf.html', {'debug_texto': texto})

        pdf_files = request.FILES.getlist('pdf_file')
        if not pdf_files:
            messages.error(request, 'Seleccioná al menos un archivo PDF.')
            return render(request, 'consultas/import_pdf.html')

        # Un solo archivo: flujo original con review manual
        if len(pdf_files) == 1:
            try:
                data = _extraer_datos_cotizacion(pdf_files[0])
            except Exception:
                messages.error(request, 'No se pudo leer el PDF. Verificá que sea un archivo válido.')
                return render(request, 'consultas/import_pdf.html')
            form = ConsultaForm(initial=data)
            return render(request, 'consultas/form.html', {
                'form': form,
                'title': 'Importar cotización desde PDF',
                'form_action': reverse('consultas:create'),
            })

        # Múltiples archivos: auto-crear sin review
        resultados = []
        for pdf_file in pdf_files:
            resultado = {'nombre': pdf_file.name, 'ok': False, 'consulta': None, 'error': ''}
            try:
                data = _extraer_datos_cotizacion(pdf_file)
                cliente = _get_or_create_cliente(
                    razon_social=data.get('razon_social', ''),
                    cuit=data.get('cuit', ''),
                    contacto=data.get('razon_social', ''),
                )
                fecha = data.get('fecha')
                if fecha:
                    try:
                        fecha = datetime.date.fromisoformat(fecha)
                    except ValueError:
                        fecha = datetime.date.today()
                else:
                    fecha = datetime.date.today()
                consulta = Consulta.objects.create(
                    fecha=fecha,
                    productos=data.get('productos', ''),
                    numero_cotizacion=data.get('numero_cotizacion', ''),
                    via_entrada=data.get('via_entrada', 'mail'),
                    razon_social=data.get('razon_social', ''),
                    contacto=data.get('razon_social', ''),
                    cuit=data.get('cuit', ''),
                    estado=Consulta.COTIZADO,
                    vendedor=request.user,
                    cliente=cliente,
                )
                resultado['ok'] = True
                resultado['consulta'] = consulta
            except Exception as e:
                resultado['error'] = str(e) or 'Error inesperado'
            resultados.append(resultado)

        creadas = sum(1 for r in resultados if r['ok'])
        fallidas = len(resultados) - creadas
        return render(request, 'consultas/import_pdf.html', {
            'resultados': resultados,
            'creadas': creadas,
            'fallidas': fallidas,
        })
