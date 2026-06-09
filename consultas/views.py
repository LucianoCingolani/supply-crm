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

_MESES_ES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
}


def _extraer_datos_cotizacion(pdf_file):
    import pdfplumber

    with pdfplumber.open(pdf_file) as pdf:
        text = pdf.pages[0].extract_text() or '' if pdf.pages else ''

    data = {'estado': 'cotizado', 'via_entrada': 'mail'}

    # "Cotización 8366 — BERTINO MARIA PAULA— 27-27143554-7"
    m = re.search(
        r'Cotizaci[oó]n\s+(\d+)\s*[—–]+\s*(.+?)\s*[—–]+\s*(\d{2}-\d{8}-\d)',
        text,
    )
    if m:
        data['numero_cotizacion'] = m.group(1)
        razon = m.group(2).strip()
        data['razon_social'] = razon
        data['contacto'] = razon
        data['cuit'] = m.group(3).strip()

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


class ConsultaImportPDFView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'consultas/import_pdf.html')

    def post(self, request):
        pdf_file = request.FILES.get('pdf_file')
        if not pdf_file:
            messages.error(request, 'Seleccioná un archivo PDF.')
            return render(request, 'consultas/import_pdf.html')

        try:
            data = _extraer_datos_cotizacion(pdf_file)
        except Exception:
            messages.error(request, 'No se pudo leer el PDF. Verificá que sea un archivo válido.')
            return render(request, 'consultas/import_pdf.html')

        form = ConsultaForm(initial=data)
        return render(request, 'consultas/form.html', {
            'form': form,
            'title': 'Importar cotización desde PDF',
            'form_action': reverse('consultas:create'),
        })
