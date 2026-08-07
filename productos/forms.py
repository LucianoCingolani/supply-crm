from django import forms

from .models import Producto

INPUT_CLASS = ('w-full px-3 py-2 border border-gray-300 rounded-lg text-sm '
               'focus:outline-none focus:ring-2 focus:ring-blue-500')
SELECT_CLASS = INPUT_CLASS + ' bg-white'
FILE_CLASS = ('w-full text-sm text-gray-600 file:mr-3 file:py-2 file:px-4 file:rounded-lg '
              'file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 '
              'hover:file:bg-blue-100 cursor-pointer')

# La imagen se guarda como bytes en la fila del producto, así que conviene un
# tope: una foto de cámara sin redimensionar infla cada consulta al catálogo.
MAX_IMAGEN_BYTES = 5 * 1024 * 1024


class PrecioField(forms.DecimalField):
    """Acepta la coma como separador decimal, que es como se escribe acá."""

    def to_python(self, value):
        if isinstance(value, str):
            value = value.replace(',', '.')
        return super().to_python(value)


class ProductoForm(forms.ModelForm):
    """Alta manual de un artículo del catálogo."""

    precio = PrecioField(
        max_digits=14, decimal_places=2, min_value=0, required=False,
        label='Precio de venta',
        help_text='Sin IVA. Se puede dejar vacío y cargarlo después.',
        widget=forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: 150000.00'}),
    )
    imagen = forms.FileField(
        required=False,
        label='Imagen',
        help_text='JPG, PNG o WEBP, hasta 5 MB.',
        widget=forms.ClearableFileInput(attrs={
            'class': FILE_CLASS, 'accept': 'image/*', 'id': 'foto-input',
        }),
    )

    class Meta:
        model = Producto
        fields = ['codigo', 'nombre', 'unidad_medida', 'precio', 'moneda', 'categoria']
        widgets = {
            'codigo': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: SA-01234'}),
            'nombre': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ej: Guante de nitrilo azul talle L'}),
            'unidad_medida': forms.Select(attrs={'class': SELECT_CLASS}),
            'moneda': forms.Select(attrs={'class': SELECT_CLASS}),
            'categoria': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': 'Ej: Protección de manos',
                'list': 'categorias-existentes',
            }),
        }
        labels = {
            'nombre': 'Descripción',
            'categoria': 'Categoría',
        }
        help_texts = {
            'codigo': 'Identifica al artículo, no se puede repetir ni cambiar después.',
            'moneda': 'En qué moneda está el precio de arriba. La cotización convierte si hace falta.',
            # El catálogo se navega por categoría: sin ella el artículo existe
            # pero solo aparece buscándolo por nombre o código.
            'categoria': 'Define en qué sección del catálogo aparece. Elegí una de la lista o escribí una nueva.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # En un alta manual siempre se sabe cómo se vende el artículo; el vacío
        # del modelo es solo para lo que vino importado.
        self.fields['unidad_medida'].required = True
        self.fields['unidad_medida'].initial = 'UN'

    def clean_imagen(self):
        imagen = self.cleaned_data.get('imagen')
        if not imagen:
            return imagen
        if not (imagen.content_type or '').lower().startswith('image/'):
            raise forms.ValidationError('El archivo tiene que ser una imagen.')
        if imagen.size > MAX_IMAGEN_BYTES:
            raise forms.ValidationError('La imagen no puede superar los 5 MB.')
        return imagen

    def save(self, commit=True):
        producto = super().save(commit=False)
        imagen = self.cleaned_data.get('imagen')
        if imagen:
            producto.foto = imagen.read()
            producto.foto_tipo = imagen.content_type or 'image/jpeg'
        if commit:
            producto.save()
        return producto
