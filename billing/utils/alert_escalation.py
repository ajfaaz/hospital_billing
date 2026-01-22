from django.utils import timezone
from django.conf import settings
from datetime import timedelta

from billing.models import VitalAlert
from messaging.models import Message
from django.contrib.auth import get_user_model

User = get_user_model()


def get_escalation_target(alert, role):
    return (
        User.objects.filter(
            role=role,
            hospital=alert.patient.hospital,
            is_active=True,
        ).first()
    )


def escalate_unacknowledged_alerts():
    now = timezone.now()

    for level, rule in settings.VITAL_ALERT_ESCALATION_RULES.items():
        threshold = now - timedelta(minutes=rule["minutes"])

        alerts = VitalAlert.objects.filter(
            status__in=["open", "escalated"],
            escalation_level__lt=level,
            created_at__lte=threshold,
        ).select_related("patient")

        for alert in alerts:
            target = get_escalation_target(alert, rule["role"])
            if not target:
                continue

            Message.objects.create(
                sender=None,
                recipient=target,
                subject="🚨 ESCALATED CRITICAL VITAL ALERT",
                body=(
                    f"Patient: {alert.patient.full_name}\n"
                    f"Severity: CRITICAL\n"
                    f"Escalation Level: {level}\n\n"
                    f"{alert.message}"
                ),
            )

            alert.escalation_level = level
            alert.escalated_to = rule["role"]
            alert.escalated_at = now
            alert.status = "escalated"
            alert.save()
