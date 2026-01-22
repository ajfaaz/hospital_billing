from django.utils import timezone
from billing.models import VitalAlert
from .sla_engine import escalate_alert

def run_sla_monitor():
    now = timezone.now()

    alerts = VitalAlert.objects.filter(
        status="open",
        escalation_deadline__isnull=False,
        escalation_deadline__lte=now
    )

    for alert in alerts:
        escalate_alert(alert)
