from django.db import models
from django.db.models import Count, Q


class ClienteQuerySet(models.QuerySet):
    def visibles_para(self, user):
        """Acota a los clientes que `user` tiene permitido ver.

        Un empleado ve únicamente los clientes con los que trabajó, es decir
        aquellos que tienen al menos una consulta suya.
        """
        if user.puede_ver_todos_los_clientes:
            return self
        return self.filter(consultas__vendedor=user).distinct()

    def con_total_consultas_para(self, user):
        """Anota `total_consultas` contando solo las consultas visibles para `user`."""
        filtro = Q() if user.puede_ver_todas_las_consultas else Q(consultas__vendedor=user)
        return self.annotate(total_consultas=Count('consultas', filter=filtro, distinct=True))


class Cliente(models.Model):
    razon_social = models.CharField(max_length=200, verbose_name='Razón social')
    contacto = models.CharField(max_length=150, blank=True, verbose_name='Contacto')
    cuit = models.CharField(max_length=30, blank=True, db_index=True, verbose_name='CUIT / CUIL')
    telefono = models.CharField(max_length=30, blank=True, verbose_name='Teléfono')
    email = models.EmailField(blank=True)
    notas = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ClienteQuerySet.as_manager()

    class Meta:
        ordering = ['razon_social']
        verbose_name = 'cliente'
        verbose_name_plural = 'clientes'

    def __str__(self):
        return self.razon_social
