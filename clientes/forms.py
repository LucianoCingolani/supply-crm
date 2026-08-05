from django import forms
from .models import Cliente

INPUT_CLASS = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'
TEXTAREA_CLASS = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'


SELECT_CLASS = INPUT_CLASS + ' bg-white'


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            'razon_social', 'contacto', 'cuit', 'dni',
            'telefono', 'email',
            'domicilio', 'localidad', 'provincia', 'codigo_postal',
            'condicion_fiscal', 'tipo_factura',
            'notas',
        ]
        widgets = {
            'razon_social': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Nombre de la empresa o persona'}),
            'contacto': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Nombre del contacto'}),
            'cuit': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: 30-12345678-9'}),
            'dni': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: 27143554'}),
            'telefono': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: 11 1234-5678'}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS, 'placeholder': 'contacto@empresa.com'}),
            'domicilio': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Calle y número'}),
            'localidad': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: San Justo'}),
            'provincia': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: Buenos Aires'}),
            'codigo_postal': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: 1754'}),
            'condicion_fiscal': forms.Select(attrs={'class': SELECT_CLASS}),
            'tipo_factura': forms.Select(attrs={'class': SELECT_CLASS}),
            'notas': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3, 'placeholder': 'Notas internas sobre este cliente...'}),
        }
        labels = {
            'razon_social': 'Razón Social',
            'cuit': 'CUIT / CUIL',
        }
