from django.utils import timezone

def sla_status(alert):
    if alert.status != "open":
        return "resolved"

    now = timezone.now()

    if alert.acknowledge_deadline and now > alert.acknowledge_deadline:
        return "breached"

    return "within_sla"

def sla_remaining_time(alert):
    if not alert.acknowledge_deadline:
        return None

    now = timezone.now()
    delta = alert.acknowledge_deadline - now

    seconds = int(delta.total_seconds())
    return seconds


def sla_timer_state(alert):
    if alert.status != "open":
        return "resolved"

    remaining = sla_remaining_time(alert)
    if remaining is None:
        return "none"

    if remaining <= 0:
        return "breached"
    elif remaining <= 300:  # last 5 minutes
        return "warning"
    else:
        return "safe"
