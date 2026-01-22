from django.utils import timezone
from billing.models import VitalAlert, CustomUser

def escalate_alert(alert):
    now = timezone.now()

    if not alert.sla_policy:
        return

    if alert.escalation_level >= alert.sla_policy.max_escalation_level:
        return

    alert.escalation_level += 1
    alert.last_escalated_at = now
    alert.escalated = True
    alert.escalated_at = now

    # Escalation chain
    if alert.escalation_level == 1:
        # Head doctor
        alert.escalated_to = CustomUser.objects.filter(
            role="head_doctor"
        ).first()

    elif alert.escalation_level == 2:
        # Admin
        alert.escalated_to = CustomUser.objects.filter(
            role="admin"
        ).first()

    alert.save()
