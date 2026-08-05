from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('El email es obligatorio')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', self.model.ADMIN)
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    ADMIN = 'admin'
    GERENTE = 'gerente'
    EMPLEADO = 'empleado'

    ROLE_CHOICES = [
        (ADMIN, 'Admin'),
        (GERENTE, 'Gerente'),
        (EMPLEADO, 'Empleado'),
    ]

    # Roles que ven los datos de toda la empresa, no solo los propios
    ROLES_VISION_TOTAL = [ADMIN, GERENTE]

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=EMPLEADO, verbose_name='rol')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    must_change_password = models.BooleanField(
        default=False,
        verbose_name='debe cambiar la contraseña',
        help_text='Al ingresar, se le va a exigir que elija una contraseña nueva.',
    )
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        # El acceso al admin de Django lo determina el rol, no un flag editable aparte
        self.is_staff = self.is_admin or self.is_superuser
        super().save(*args, **kwargs)

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    # ── Identidad de rol ───────────────────────────────────────────
    # Responden "qué rol tiene". No las uses para decidir permisos:
    # para eso están las capacidades de abajo.

    @property
    def is_admin(self):
        return self.role == self.ADMIN

    @property
    def is_gerente(self):
        return self.role == self.GERENTE

    @property
    def is_empleado(self):
        return self.role == self.EMPLEADO

    # ── Capacidades ────────────────────────────────────────────────
    # Lo que consultan views, mixins y templates. Para cambiar qué puede
    # hacer un rol se toca únicamente acá.

    @property
    def puede_ver_todas_las_consultas(self):
        return self.role in self.ROLES_VISION_TOTAL

    @property
    def puede_ver_todos_los_clientes(self):
        return self.role in self.ROLES_VISION_TOTAL

    @property
    def puede_gestionar_usuarios(self):
        return self.role in self.ROLES_VISION_TOTAL

    @property
    def puede_asignar_clientes(self):
        """Repartir la cartera es del Gerente: define qué cliente trabaja cada uno."""
        return self.role in self.ROLES_VISION_TOTAL

    @property
    def puede_editar_catalogo(self):
        return self.role in self.ROLES_VISION_TOTAL

    @property
    def puede_ver_reportes(self):
        return self.role in self.ROLES_VISION_TOTAL

    @property
    def puede_administrar_admins(self):
        """Solo un Admin puede ver, crear o modificar a otros Admins."""
        return self.is_admin
