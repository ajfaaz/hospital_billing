from django.core.management.base import BaseCommand
from billing.utils.alert_escalation import escalate_unacknowledged_alerts

class Command(BaseCommand):
    help = "Escalate unacknowledged critical vital alerts"

    def handle(self, *args, **kwargs):
        escalate_unacknowledged_alerts()
        self.stdout.write(self.style.SUCCESS("Alert escalation check completed"))
