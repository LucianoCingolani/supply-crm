from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model

User = get_user_model()

INPUT_CLASS = 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'


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


class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS})
    )
    password2 = forms.CharField(
        label='Confirmar contraseña',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS})
    )

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'role')
        widgets = {
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS}),
            'first_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'last_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'role': forms.Select(attrs={'class': INPUT_CLASS}),
        }

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Las contraseñas no coinciden.')
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'role', 'is_active')
        widgets = {
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS}),
            'first_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'last_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'role': forms.Select(attrs={'class': INPUT_CLASS}),
        }


class PasswordChangeForm(forms.Form):
    password1 = forms.CharField(
        label='Nueva contraseña',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS})
    )
    password2 = forms.CharField(
        label='Confirmar nueva contraseña',
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS})
    )

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Las contraseñas no coinciden.')
        return p2
