from django.db.models import Avg, F, DurationField, ExpressionWrapper
from datetime import timedelta
from billing.models import VitalAlert, CustomUser, Hospital

def doctor_sla_metrics(target, hospital=None):
    """
    Calculates SLA metrics.
    If target is a Hospital, returns a list of metrics for all doctors in that hospital.
    If target is a Doctor (User), returns a dict of metrics for that specific doctor.
    """
    # Case 1: Target is Hospital -> Return list for all doctors
    if isinstance(target, Hospital):
        doctors = CustomUser.objects.filter(hospital=target, role="doctor")
        results = []
        for doc in doctors:
            metrics = calculate_metrics(doc)
            metrics['doctor'] = doc
            results.append(metrics)
        return results
    
    # Case 2: Target is Doctor -> Return single dict
    elif isinstance(target, CustomUser):
        return calculate_metrics(target)
    
    return {}

def calculate_metrics(doctor):
    alerts = VitalAlert.objects.filter(assigned_doctor=doctor)
    total = alerts.count()
    
    # Acknowledged alerts
    acked = alerts.filter(acknowledged_at__isnull=False)
    
    # Avg Ack Time
    avg_ack = acked.annotate(
        duration=ExpressionWrapper(F('acknowledged_at') - F('created_at'), output_field=DurationField())
    ).aggregate(avg=Avg('duration'))['avg']
    
    # Format avg_ack
    avg_ack_str = "0m"
    if avg_ack:
        total_seconds = int(avg_ack.total_seconds())
        minutes = total_seconds // 60
        avg_ack_str = f"{minutes}m"

    # SLA Compliance Calculation
    sla_minutes = 15 # Default fallback
    if doctor.hospital and hasattr(doctor.hospital, 'sla_doctor_ack_minutes'):
        sla_minutes = doctor.hospital.sla_doctor_ack_minutes
        
    within_sla = 0
    for a in acked:
        limit = a.created_at + timedelta(minutes=sla_minutes)
        if a.acknowledged_at <= limit:
            within_sla += 1
            
    compliance = 0
    if acked.exists():
        compliance = int((within_sla / acked.count()) * 100)
        
    # Escalations (assuming escalation_level > 0 means escalated)
    escalations = alerts.filter(escalation_level__gt=0).count()
    
    # Risk Assessment
    risk = "green"
    if compliance < 85: risk = "amber"
    if compliance < 60: risk = "red"
        
    return {
        "total_alerts": total,
        "avg_ack_time": avg_ack_str,
        "sla_compliance": compliance,
        "escalations": escalations,
        "risk": risk
    }