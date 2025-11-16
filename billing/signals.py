from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from billing.models import Hospital

User = get_user_model()

@receiver(post_save, sender=User)
def assign_default_hospital(sender, instance, created, **kwargs):
    """
    Automatically assign the default hospital to any new user created.
    """
    if created and not instance.hospital:
        # ✅ get or create a default hospital
        default_hospital, _ = Hospital.objects.get_or_create(
            name="Default Hospital",
            defaults={"address": "Main Branch", "phone": "0000000000"},
        )
        instance.hospital = default_hospital
        instance.save()
