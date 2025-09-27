from django.db import models
from django.conf import settings

class Message(models.Model):
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_messages"
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_messages"
    )
    subject = models.CharField(max_length=255)
    body = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"From {self.sender.username} to {self.recipient.username}: {self.subject}"


from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Message

@receiver(post_save, sender=Message)
def notify_recipient(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        group = f"user_{instance.recipient.id}"
        unread_count = Message.objects.filter(
            recipient=instance.recipient, is_read=False
        ).count()
        async_to_sync(channel_layer.group_send)(
            group,
            {"type": "new_message", "count": unread_count},
        )
