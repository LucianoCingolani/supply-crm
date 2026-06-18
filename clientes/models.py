from django.db import models


class Cliente(models.Model):
    razon_social = models.CharField(max_length=200, verbose_name='Razón social')
    contacto = models.CharField(max_length=150, blank=True, verbose_name='Contacto')
    cuit = models.CharField(max_length=30, blank=True, db_index=True, verbose_name='CUIT / CUIL')
    telefono = models.CharField(max_length=30, blank=True, verbose_name='Teléfono')
    email = models.EmailField(blank=True)
    notas = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['razon_social']
        verbose_name = 'cliente'
        verbose_name_plural = 'clientes'

    def __str__(self):
        return self.razon_social

    @property
    def ultima_consulta(self):
        return self.consultas.order_by('-fecha', '-created_at').first()
