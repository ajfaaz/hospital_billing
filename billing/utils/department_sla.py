from django.db.models import Avg, Count, Q, F, DurationField, ExpressionWrapper
from datetime import timedelta
from billing.models import VitalAlert, CustomUser


def department_sla_metrics(hospital):
    data = []

    doctors = CustomUser.objects.filter(
        hospital=hospital,
        role="doctor"
    )

    departments = doctors.values_list(
        "specialty", flat=True
    ).distinct()

    for dept in departments:
        dept_doctors = doctors.filter(specialty=dept)

        alerts = VitalAlert.objects.filter(
            assigned_doctor__in=dept_doctors,
            patient__hospital=hospital
        )

        total = alerts.count()
        acknowledged = alerts.filter(acknowledged_at__isnull=False)

        avg_ack = acknowledged.annotate(
            ack_duration=ExpressionWrapper(
                F("acknowledged_at") - F("created_at"),
                output_field=DurationField()
            )
        ).aggregate(avg=Avg("ack_duration"))["avg"]

        sla_minutes = hospital.sla_doctor_ack_minutes
        within_sla = acknowledged.filter(
            acknowledged_at__lte=F("created_at") + timedelta(minutes=sla_minutes)
        ).count()

        escalations = alerts.filter(escalation_level__gt=0).count()

        compliance = (
            (within_sla / acknowledged.count()) * 100
            if acknowledged.exists() else 0
        )

        # Risk indicator
        if compliance >= 85:
            risk = "green"
        elif compliance >= 60:
            risk = "amber"
        else:
            risk = "red"

        data.append({
            "department": dept or "Unassigned",
            "total_alerts": total,
            "avg_ack_time": avg_ack,
            "sla_compliance": round(compliance, 1),
            "escalations": escalations,
            "risk": risk,
            "doctor_count": dept_doctors.count(),
        })

    return data
