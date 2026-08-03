from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('email', 'first_name', 'last_name', 'role', 'is_active', 'must_change_password')
    list_filter = ('role', 'is_active', 'must_change_password')
    ordering = ('email',)
    search_fields = ('email', 'first_name', 'last_name')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Información personal', {'fields': ('first_name', 'last_name')}),
        ('Permisos', {
            'fields': ('role', 'is_active', 'must_change_password', 'is_superuser',
                       'groups', 'user_permissions'),
            # is_staff no se edita acá: lo deriva CustomUser.save() a partir del rol
            'description': 'El acceso a este admin lo da el rol Admin.',
        }),
        ('Fechas', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'role', 'password1', 'password2', 'is_active'),
        }),
    )
    readonly_fields = ('date_joined', 'last_login', 'is_staff')
