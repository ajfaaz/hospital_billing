# messaging/signals.py
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Message

@receiver(post_save, sender=Message)
def notify_new_message(sender, instance, created, **kwargs):
    if not created:
        return
    layer = get_channel_layer()
    group = f"user_{instance.recipient_id}"
    async_to_sync(layer.group_send)(
        group,
        {
            "type": "new_message",   # <— matches JS check
            "count": Message.objects.filter(
                recipient=instance.recipient, is_read=False
            ).count(),
        },
    )
