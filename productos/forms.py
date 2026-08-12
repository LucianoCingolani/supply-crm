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
    """Alta y edición de un artículo del catálogo.

    `edicion=True` bloquea el código, que es la clave con la que el importador
    reconoce al artículo: cambiarlo crearía un duplicado en la próxima corrida.
    """

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
    borrar_foto = forms.BooleanField(
        required=False,
        label='Borrar la imagen actual',
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 rounded border-gray-300 text-red-500 focus:ring-red-400',
        }),
    )

    class Meta:
        model = Producto
        fields = ['codigo', 'nombre', 'unidad_medida', 'precio', 'moneda',
                  'categoria', 'colores', 'especificaciones']
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
            'colores': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': 'Ej: A elección',
            }),
            'especificaciones': forms.Textarea(attrs={
                'class': INPUT_CLASS + ' font-mono', 'rows': 5,
                'placeholder': 'Una característica por línea',
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
            'especificaciones': 'Una por línea. Salen como bullets en la ficha.',
        }

    def __init__(self, *args, edicion=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.edicion = edicion
        if edicion:
            # disabled ignora lo que venga en el POST y conserva el valor guardado.
            self.fields['codigo'].disabled = True
            self.fields['codigo'].help_text = 'No se puede modificar: es la clave del artículo.'
            self.fields['codigo'].widget.attrs['class'] = (
                INPUT_CLASS + ' bg-gray-50 text-gray-400 cursor-not-allowed'
            )
        else:
            # En un alta siempre se sabe cómo se vende; editando puede tocar
            # arreglar solo el precio de una fila importada que no trae unidad,
            # y exigirla ahí sería un obstáculo sin motivo.
            self.fields['unidad_medida'].required = True
            self.fields['unidad_medida'].initial = 'UN'
            del self.fields['borrar_foto']

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
        elif self.cleaned_data.get('borrar_foto'):
            producto.foto = None
            producto.foto_tipo = ''
        if commit:
            producto.save()
        return producto
