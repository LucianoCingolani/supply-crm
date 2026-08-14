from django import forms
from django.contrib.auth import get_user_model

from .models import Cliente

User = get_user_model()

INPUT_CLASS = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'
TEXTAREA_CLASS = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'


SELECT_CLASS = INPUT_CLASS + ' bg-white'


class ClienteForm(forms.ModelForm):
    """El campo `vendedor` solo aparece para quien puede repartir la cartera."""

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        if editor is not None and not editor.puede_asignar_clientes:
            del self.fields['vendedor']
            return
        # Solo roles que llevan cartera: el Coach y Tesorería no atienden clientes.
        candidatos = User.objects.filter(
            is_active=True, role__in=User.ROLES_QUE_CARGAN_VENTAS)
        if editor is not None and not editor.puede_administrar_admins:
            candidatos = candidatos.exclude(role=User.ADMIN)
        self.fields['vendedor'].queryset = candidatos.order_by('last_name', 'first_name')
        self.fields['vendedor'].empty_label = '— Sin asignar —'

    class Meta:
        model = Cliente
        fields = [
            'razon_social', 'contacto', 'cuit', 'dni',
            'telefono', 'whatsapp', 'email',
            'domicilio', 'localidad', 'provincia', 'codigo_postal',
            'condicion_fiscal', 'tipo_factura',
            'vendedor',
            'notas',
        ]
        widgets = {
            'razon_social': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Nombre de la empresa o persona'}),
            'contacto': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Nombre del contacto'}),
            'cuit': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: 30-12345678-9'}),
            'dni': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: 27143554'}),
            'telefono': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: 11 1234-5678'}),
            'whatsapp': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: 11 1234-5678'}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS, 'placeholder': 'contacto@empresa.com'}),
            'domicilio': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Calle y número'}),
            'localidad': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: San Justo'}),
            'provincia': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: Buenos Aires'}),
            'codigo_postal': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: 1754'}),
            'condicion_fiscal': forms.Select(attrs={'class': SELECT_CLASS}),
            'tipo_factura': forms.Select(attrs={'class': SELECT_CLASS}),
            'vendedor': forms.Select(attrs={'class': SELECT_CLASS}),
            'notas': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3, 'placeholder': 'Notas internas sobre este cliente...'}),
        }
        labels = {
            'razon_social': 'Razón Social',
            'cuit': 'CUIT / CUIL',
        }
