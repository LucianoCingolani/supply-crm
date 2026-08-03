from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User = get_user_model()

INPUT_CLASS = 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'
CHECKBOX_CLASS = 'h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500'


class DosPasswordsMixin:
    """Valida que las dos contraseñas coincidan y que pasen los validadores de Django.

    `usuario_objetivo` se usa para las reglas que comparan la contraseña con los
    datos de la persona (UserAttributeSimilarityValidator).
    """

    usuario_objetivo = None

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise ValidationError('Las contraseñas no coinciden.')
        if p2:
            validate_password(p2, self.usuario_objetivo)
        return p2


class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'tu@email.com',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': '••••••••',
        })
    )


class RolesPermitidosMixin:
    """Deja elegir el rol Admin solo si quien edita es Admin."""

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        if editor is not None and not editor.puede_administrar_admins:
            self.fields['role'].choices = [
                (valor, etiqueta) for valor, etiqueta in User.ROLE_CHOICES
                if valor != User.ADMIN
            ]


class UserCreateForm(DosPasswordsMixin, RolesPermitidosMixin, forms.ModelForm):
    password1 = forms.CharField(
        label='Contraseña provisoria',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS}),
        help_text='Se la pasás a la persona por el medio que uses; ella elige la definitiva al ingresar.',
    )
    password2 = forms.CharField(
        label='Confirmar contraseña',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS})
    )

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'role', 'must_change_password')
        widgets = {
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS}),
            'first_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'last_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'role': forms.Select(attrs={'class': INPUT_CLASS}),
            'must_change_password': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
        }
        labels = {
            'must_change_password': 'Pedirle que elija su contraseña al ingresar',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Al crear un usuario lo esperable es que elija su propia contraseña.
        self.fields['must_change_password'].initial = True

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class UserEditForm(RolesPermitidosMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'role', 'is_active', 'must_change_password')
        widgets = {
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS}),
            'first_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'last_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'role': forms.Select(attrs={'class': INPUT_CLASS}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
            'must_change_password': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
        }
        labels = {
            'is_active': 'Usuario activo',
            'must_change_password': 'Pedirle que elija su contraseña al ingresar',
        }


class AdminSetPasswordForm(DosPasswordsMixin, forms.Form):
    """Un Admin o Gerente le fija una contraseña a otra persona."""

    password1 = forms.CharField(
        label='Nueva contraseña',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS})
    )
    password2 = forms.CharField(
        label='Confirmar nueva contraseña',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS})
    )
    must_change_password = forms.BooleanField(
        label='Pedirle que elija su contraseña al ingresar',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
    )

    def __init__(self, *args, usuario_objetivo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario_objetivo = usuario_objetivo


class CambiarPasswordPropiaForm(DosPasswordsMixin, forms.Form):
    """La persona cambia su propia contraseña.

    Pide la contraseña actual salvo que esté en un cambio obligatorio: en ese
    caso acaba de autenticarse con una provisoria que no eligió, y volver a
    pedírsela es fricción sin ganancia.
    """

    password_actual = forms.CharField(
        label='Contraseña actual',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS})
    )
    password1 = forms.CharField(
        label='Nueva contraseña',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS})
    )
    password2 = forms.CharField(
        label='Confirmar nueva contraseña',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS})
    )

    def __init__(self, *args, usuario_objetivo=None, exigir_actual=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario_objetivo = usuario_objetivo
        self.exigir_actual = exigir_actual
        if not exigir_actual:
            del self.fields['password_actual']

    def clean_password_actual(self):
        actual = self.cleaned_data.get('password_actual')
        if self.usuario_objetivo and not self.usuario_objetivo.check_password(actual):
            raise ValidationError('La contraseña actual no es correcta.')
        return actual

    def clean_password2(self):
        p2 = super().clean_password2()
        # Vale también para el cambio obligatorio: si no, alcanzaría con repetir
        # la contraseña provisoria para que el flag se limpie sin haber elegido nada.
        if p2 and self.usuario_objetivo and self.usuario_objetivo.check_password(p2):
            raise ValidationError('La contraseña nueva tiene que ser distinta de la actual.')
        return p2
