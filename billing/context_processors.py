from messaging.models import Message


def unread_messages(request):
    if request.user.is_authenticated:
        return {
            "unread_count": Message.objects.filter(recipient=request.user, is_read=False).count()
        }
    return {"unread_count": 0}
