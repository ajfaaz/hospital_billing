from django.db import models

class Medicine(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    stock = models.PositiveIntegerField()
    expiry_date = models.DateField()

    def __str__(self):
        return self.name
