from django import forms
from .models import Consulta, SeguimientoLog

SELECT_CLASS = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white'
INPUT_CLASS = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'
TEXTAREA_CLASS = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'


class ConsultaForm(forms.ModelForm):
    class Meta:
        model = Consulta
        fields = [
            'fecha', 'productos', 'cantidad', 'via_entrada', 'numero_cotizacion',
            'razon_social', 'contacto', 'cuit', 'telefono', 'email',
            'estado', 'notas', 'fecha_seguimiento',
        ]
        widgets = {
            'fecha': forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'}),
            'productos': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: B32 Bines Plásticos, C11 Contenedor'}),
            'cantidad': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: 10'}),
            'via_entrada': forms.Select(attrs={'class': SELECT_CLASS}),
            'numero_cotizacion': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: 8013'}),
            'razon_social': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Nombre de la empresa'}),
            'contacto': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Nombre del contacto'}),
            'cuit': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: 30-12345678-9'}),
            'telefono': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: 11 1234-5678'}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS, 'placeholder': 'contacto@empresa.com'}),
            'estado': forms.Select(attrs={'class': SELECT_CLASS}),
            'notas': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3, 'placeholder': 'Notas del seguimiento...'}),
            'fecha_seguimiento': forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'}),
        }
        labels = {
            'productos': 'Productos / Descripción',
            'via_entrada': 'Canal de entrada',
            'numero_cotizacion': 'Nº Cotización',
            'razon_social': 'Razón Social',
            'fecha_seguimiento': 'Próximo seguimiento',
        }


class SeguimientoForm(forms.ModelForm):
    class Meta:
        model = SeguimientoLog
        fields = ['nota']
        widgets = {
            'nota': forms.Textarea(attrs={
                'class': TEXTAREA_CLASS,
                'rows': 2,
                'placeholder': 'Registrá una acción: llamé, mandé wsp, confirmó compra...',
            })
        }
        labels = {'nota': ''}


class FiltroConsultaForm(forms.Form):
    estado = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos los estados')] + Consulta.ESTADO_CHOICES,
        widget=forms.Select(attrs={'class': SELECT_CLASS})
    )
    via_entrada = forms.ChoiceField(
        required=False,
        choices=[('', 'Todas las vías')] + Consulta.VIA_CHOICES,
        widget=forms.Select(attrs={'class': SELECT_CLASS})
    )
    buscar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Empresa, contacto, producto...'})
    )
