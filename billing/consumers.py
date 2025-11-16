# billing/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Each connected user joins a notification group
        self.group_name = f"user_{self.scope['user'].id}_notifications"

        if self.scope["user"].is_anonymous:
            await self.close()
        else:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        # Optional: for debugging — echo messages back
        await self.send(text_data=json.dumps({
            "type": "debug",
            "message": "Notification socket active"
        }))

    async def send_notification(self, event):
        """
        This method will be called whenever a notification is sent
        through the channel layer to this user's group.
        """
        await self.send(text_data=json.dumps({
            "type": "notification",
            "message": event["message"],
            "count": event.get("count", 0)
        }))
