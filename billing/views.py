from io import BytesIO
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, Max
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import get_template
from .models import MedicineCategory
from billing.utils.vitals import evaluate_vitals
import json
from xhtml2pdf import pisa
from datetime import timedelta

from .forms import (
    BillItemForm,
    PaymentForm,
    AppointmentForm,
    CustomUserCreationForm,
    MedicalRecordForm,
    LabReportForm,
    RadiologyReportForm,
    PatientRegistrationForm,
)
from .models import (
    Appointment,
    Patient,
    Service,
    Bill,
    BillItem,
    Payment,
    AuditLog,
    PatientVisit,
    CustomUser,
    Hospital,
    MedicalRecord,
    LabReport,
    RadiologyReport,
    VitalSign,
    VitalAlert,
    VitalAlertLog,
    SLAPolicy,
    PatientCoverage,
    ThirdPartyPayer,
    Payer,
)
from billing.utils.sla import sla_remaining_time, sla_timer_state
from billing.utils.audit import log_action
from billing.utils.billing import calculate_bill_split

from messaging.forms import MessageForm
from messaging.models import Message

User = get_user_model()

# =======================================================
# DASHBOARD
# =======================================================
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def dashboard(request):
    user = request.user

    # Handle hospital-bound data (some roles may not have hospital field)
    hospital_filter = {}
    if hasattr(user, 'hospital') and user.hospital:
        hospital_filter = {"hospital": user.hospital}

    # Income trend (monthly totals)
    income_by_month = (
        Payment.objects.annotate(month=TruncMonth("paid_on"))
        .values("month")
        .annotate(total=Sum("amount_paid"))
        .order_by("month")
    )

    labels = [entry["month"].strftime("%b %Y") for entry in income_by_month]
    data = [entry["total"] for entry in income_by_month]

    # Unread messages
    unread_count = Message.objects.filter(recipient=user, is_read=False).count()

    # Dashboard stats
    context = {
        "chart_labels": labels,
        "chart_data": data,
        "patient_count": Patient.objects.filter(**hospital_filter).count(),
        "appointment_count": Appointment.objects.filter(**hospital_filter).count(),
        "bill_count": Bill.objects.filter(**hospital_filter).count(),
        "total_income": Payment.objects.aggregate(total=Sum("amount_paid"))["total"] or 0,
        "unread_count": unread_count,
    }

    # Map user roles to their dashboards
    template_map = {
        "admin": "billing/dashboard_admin.html",
        "doctor": "billing/dashboard_doctor.html",
        "receptionist": "billing/dashboard_receptionist.html",
        "accountant": "billing/dashboard_accountant.html",
        "radiologist": "billing/dashboard_radiologist.html",
        "lab_technician": "billing/dashboard_lab.html",
        "pharmacist": "billing/pharmacist_dashboard.html",
    }

    # Default to a simple dashboard if role is missing
    template = template_map.get(user.role, "billing/dashboard.html")
    return render(request, template, context)

# =======================================================
# HOME & ROLE REDIRECT
# =======================================================

def home(request):
    return render(request, "home.html")


@login_required
def redirect_by_role(request):
    role_redirects = {
        "admin": "admin_dashboard",
        "doctor": "doctor_dashboard",
        "receptionist": "receptionist_dashboard",
        "accountant": "accountant_dashboard",
        "radiologist": "radiologist_dashboard",
        "lab_technician": "lab_dashboard",
        "pharmacist": "pharmacist_dashboard",
    }
    return redirect(role_redirects.get(request.user.role, "dashboard"))


# =======================================================
# PATIENT MANAGEMENT
# =======================================================

@login_required
def patient_list(request):
    query = request.GET.get("q", "")
    patients = Patient.objects.filter(hospital=request.user.hospital)
    if query:
        patients = patients.filter(full_name__icontains=query)
    return render(request, "billing/patient_list.html", {"patients": patients, "query": query})


@login_required
def patient_detail(request, patient_id):
    """Simple patient detail endpoint — redirect to the EMR page.

    Kept lightweight to avoid adding a new template; callers expecting
    a patient detail page will be forwarded to the EMR view.
    """
    patient = get_object_or_404(Patient, id=patient_id)
    return redirect("patient_emr", patient_id=patient.id)


@login_required
def create_patient(request):
    if request.method == "POST":
        name = request.POST.get("name")
        dob = request.POST.get("dob")
        phone = request.POST.get("phone")

        hospital = request.user.hospital
        if not hospital:
            messages.error(request, "No hospital found.")
            return redirect("receptionist_dashboard")

        patient = Patient.objects.create(
            full_name=name,
            date_of_birth=dob,
            phone_number=phone,
            hospital=hospital,
        )
        messages.success(request, "Patient created successfully.")
        return redirect(f"/appointments/create/?patient={patient.id}")
    return render(request, "billing/create_patient.html")


@login_required
def register_patient(request):
    payers = Payer.objects.filter(active=True)

    if request.method == "POST":
        # ensure patient is linked to the user's hospital
        if not getattr(request.user, 'hospital', None):
            messages.error(request, "You are not linked to a hospital.")
            return redirect("receptionist_dashboard")

        # Patient info
        patient = Patient.objects.create(
            full_name=request.POST.get("full_name"),
            date_of_birth=request.POST.get("date_of_birth") or None,
            phone_number=request.POST.get("phone"),
            hospital=request.user.hospital,
        )

        payer = Payer.objects.get(id=request.POST.get("payer"))

        # Default coverage logic
        patient_percentage = 100
        government_percentage = 0

        if payer.code in ["NHIS", "KSCHMA"]:
            patient_percentage = 10
            government_percentage = 90

        if payer.code == "HOSPITAL_FREE":
            patient_percentage = 0
            government_percentage = 100

        PatientCoverage.objects.create(
            patient=patient,
            payer=payer,
            patient_percentage=patient_percentage,
            government_percentage=government_percentage,
            approved_by=request.user,
            notes=request.POST.get("coverage_notes", "")
        )

        return redirect("receptionist_dashboard")

    return render(request, "billing/register_patient.html", {"payers": payers})


# =======================================================
# APPOINTMENTS
# =======================================================

@login_required
def appointment_list(request):
    hospital = getattr(request.user, "hospital", None)
    if not hospital:
        messages.error(request, "You are not linked to any hospital.")
        return redirect("dashboard")

    query = request.GET.get("q", "")
    appointments = Appointment.objects.filter(hospital=hospital)
    if query:
        appointments = appointments.filter(
            Q(patient__full_name__icontains=query) | Q(reason__icontains=query)
        )
    appointments = appointments.select_related("patient", "doctor").order_by("-date", "-time")
    return render(request, "billing/appointment_list.html", {"appointments": appointments, "query": query})


@login_required
def create_appointment(request):
    hospital = request.user.hospital
    patients = Patient.objects.filter(hospital=hospital)
    doctors = CustomUser.objects.filter(role="doctor", hospital=hospital)
    preselected_patient_id = request.GET.get("patient")

    if request.method == "POST":
        patient_id = request.POST.get("patient")
        doctor_id = request.POST.get("doctor")
        date = request.POST.get("date")
        time = request.POST.get("time")
        reason = request.POST.get("reason")

        patient = get_object_or_404(Patient, id=patient_id, hospital=hospital)
        doctor = get_object_or_404(CustomUser, id=doctor_id, hospital=hospital)

        Appointment.objects.create(
            hospital=hospital,
            patient=patient,
            doctor=doctor,
            date=date,
            time=time,
            reason=reason,
            status="scheduled",
        )
        messages.success(request, "Appointment created successfully.")
        return redirect("appointment_list")

    return render(
        request,
        "billing/create_appointment.html",
        {"patients": patients, "doctors": doctors, "preselected_patient_id": preselected_patient_id},
    )


# =======================================================
# BILLING & PAYMENTS
# =======================================================

@login_required
def bill_list(request):
    hospital = request.user.hospital
    bills = Bill.objects.filter(hospital=hospital).select_related('patient').order_by('-created_at')
    return render(request, "billing/bill_list.html", {"bills": bills})

@login_required
def create_bill_index(request):
    messages.info(request, "Please select a patient to create a bill.")
    return redirect("patient_list")

@login_required
def create_bill(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    services = Service.objects.filter(hospital=patient.hospital)
    # include patient coverage info in template context
    coverage = getattr(patient, "patientcoverage", None)

    if request.method == "POST":
        items_data, total = [], 0
        service_ids = request.POST.getlist("service")
        quantities = request.POST.getlist("quantity")

        for i in range(len(service_ids)):
            service = get_object_or_404(Service, id=service_ids[i])
            qty = int(quantities[i])
            subtotal = service.price * qty
            total += subtotal
            items_data.append({"service": service, "quantity": qty, "subtotal": subtotal})

        patient_payable, third_party_payable, third_party = calculate_bill_split(patient, total)

        bill = Bill.objects.create(
            patient=patient,
            total_amount=total,
            created_by=request.user,
            hospital=patient.hospital,
            patient_payable=patient_payable,
            third_party_payable=third_party_payable,
            third_party=third_party,
        )
        log_action(request.user, "create", "Bill", bill.id, f"Created bill of ${total} for {patient}")

        for item in items_data:
            BillItem.objects.create(bill=bill, service=item["service"], quantity=item["quantity"], subtotal=item["subtotal"])

        return redirect("view_invoice", bill_id=bill.id)

    return render(
        request,
        "billing/create_bill.html",
        {
            "patient": patient,
            "services": services,
            "coverage": coverage,
        },
    )


@login_required
def view_invoice(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    items = bill.items.all()
    payments = bill.payment_set.all()
    paid = sum(p.amount_paid for p in payments)
    due = bill.total_amount - paid
    return render(
        request,
        "billing/invoice.html",
        {"bill": bill, "items": items, "payments": payments, "paid": paid, "due": due},
    )


@login_required
def download_invoice_pdf(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    items = bill.items.all()
    payments = bill.payment_set.all()
    paid = sum(p.amount_paid for p in payments)
    due = bill.total_amount - paid

    html = get_template("billing/invoice.html").render(
        {"bill": bill, "items": items, "payments": payments, "paid": paid, "due": due}
    )
    buffer = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=buffer, encoding="UTF-8")
    buffer.seek(0)

    if pisa_status.err:
        return HttpResponse("PDF generation error", status=500)

    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="invoice_{bill.invoice_no}.pdf"'
    return response


@login_required
def record_payment(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    if request.method == "POST":
        amount = request.POST.get("amount")
        payment_method = request.POST.get("payment_method")
        Payment.objects.create(
            bill=bill,
            amount_paid=amount,
            payment_mode=payment_method,
            hospital=bill.hospital,
        )

        # Update bill status — only consider the patient's portion
        total_paid = bill.payment_set.aggregate(total=Sum('amount_paid'))['total'] or 0
        if total_paid >= bill.patient_payable:
            bill.is_fully_paid = True
            bill.save()

        messages.success(request, "Payment recorded successfully.")
        return redirect("view_invoice", bill_id=bill.id)
    return render(request, "billing/record_payment.html", {"bill": bill})


# =======================================================
# REPORTS & AUDIT LOGS
# =======================================================

@login_required
def income_report(request):
    payments = Payment.objects.all().order_by("-paid_on")
    total_income = payments.aggregate(total=Sum("amount_paid"))["total"] or 0

    monthly_data = (
        payments.annotate(month=TruncMonth("paid_on"))
        .values("month")
        .annotate(total=Sum("amount_paid"))
        .order_by("month")
    )
    labels = [item["month"].strftime("%B %Y") for item in monthly_data]
    data = [float(item["total"]) for item in monthly_data]

    return render(
        request,
        "billing/income_report.html",
        {"payments": payments, "total_income": total_income, "labels": labels, "data": data},
    )


@login_required
def audit_logs(request):
    if request.user.role not in ["admin", "accountant"]:
        return HttpResponseForbidden("You are not authorized to view this page.")
    logs = AuditLog.objects.all().order_by("-timestamp")
    return render(request, "billing/audit_logs.html", {"logs": logs})


# =======================================================
# MESSAGING
# =======================================================

# billing/views.py  (or move to messaging/views.py if preferred)

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, Max
from django.contrib.auth import get_user_model
from messaging.models import Message
from messaging.forms import MessageForm

User = get_user_model()

@login_required
def compose_message(request):
    to_user_id = request.GET.get("to")
    reply_subject = request.GET.get("subject")
    initial_data = {}

    if to_user_id:
        recipient = User.objects.filter(id=to_user_id).first()
        if recipient:
            initial_data["recipient"] = recipient
    if reply_subject and not reply_subject.lower().startswith("re:"):
        initial_data["subject"] = f"Re: {reply_subject}"

    if request.method == "POST":
        form = MessageForm(request.POST)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.sender = request.user
            msg.save()
            return redirect("inbox")
    else:
        form = MessageForm(initial=initial_data)

    return render(request, "billing/messages/compose.html", {"form": form})


@login_required
def inbox(request):
    # latest message per sender
    subquery = (
        Message.objects.filter(recipient=request.user)
        .values("sender")
        .annotate(latest_id=Max("id"))
        .values_list("latest_id", flat=True)
    )
    messages = (
        Message.objects.filter(id__in=subquery)
        .select_related("sender")
        .order_by("-timestamp")
    )
    return render(request, "billing/messages/inbox.html", {"messages": messages})


@login_required
def conversation(request, sender_id):
    sender = get_object_or_404(User, id=sender_id)

    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        if body:
            Message.objects.create(
                sender=request.user,
                recipient=sender,
                subject="Reply",
                body=body,
            )
            return redirect("conversation", sender_id=sender.id)

    msgs = Message.objects.filter(
        Q(sender=request.user, recipient=sender) |
        Q(sender=sender, recipient=request.user)
    ).order_by("timestamp")

    Message.objects.filter(
        sender=sender, recipient=request.user, is_read=False
    ).update(is_read=True)

    return render(
        request,
        "billing/messages/conversation.html",
        {"sender": sender, "messages": msgs},
    )


@login_required
def sent_messages(request):
    messages_sent = Message.objects.filter(sender=request.user).order_by("-timestamp")
    return render(
        request,
        "billing/messages/sent_messages.html",
        {"messages_sent": messages_sent},
    )


@login_required
def message_detail(request, pk):
    message = get_object_or_404(
        Message.objects.filter(
            Q(id=pk) & (Q(recipient=request.user) | Q(sender=request.user))
        )
    )
    if message.recipient == request.user and not message.is_read:
        message.is_read = True
        message.save()
    return render(request, "billing/messages/message_detail.html", {"message": message})


# =======================================================
# MEDICAL RECORDS / REPORTS
# =======================================================

@login_required
def add_medical_record(request, patient_id):
    if request.user.role != "doctor":
        messages.error(request, "Only doctors can add medical notes.")
        return redirect("patient_emr", patient_id=patient_id)

    patient = get_object_or_404(Patient, id=patient_id)
    visit_id = request.POST.get("visit_id")
    visit = None

    if visit_id:
        visit = PatientVisit.objects.filter(id=visit_id, patient=patient).first()

    if request.method == "POST":
        title = request.POST.get("title").strip()
        notes = request.POST.get("notes").strip()

        alert_id = request.POST.get("alert_id")
        alert = None
        if alert_id:
            alert = VitalAlert.objects.filter(id=alert_id, patient=patient).first()

        MedicalRecord.objects.create(
            patient=patient,
            diagnosis=title,
            treatment="See notes",
            notes=notes,
            doctor=request.user,
            alert=alert
        )

        if alert:
            alert.status = "resolved"
            alert.save()

            VitalAlertLog.objects.create(
                alert=alert,
                action="resolved",
                performed_by=request.user,
                notes="Resolved via consultation note"
            )

        messages.success(request, "Medical note added successfully.")
        return redirect("patient_emr", patient_id=patient.id)

@login_required
def add_doctor_note(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    hospital = request.user.hospital

    visits = PatientVisit.objects.filter(patient=patient, status="active")

    if request.method == "POST":
        visit_id = request.POST.get("visit_id")
        notes = request.POST.get("notes")

        visit = get_object_or_404(PatientVisit, id=visit_id)

        MedicalRecord.objects.create(
            patient=patient,
            doctor=request.user,
            notes=notes,
            diagnosis="Doctor Note",
            treatment="See notes",
        )

        messages.success(request, "Doctor note added successfully.")
        return redirect("patient_emr", patient_id=patient.id)

    return render(request, "billing/doctor_note_add.html", {
        "patient": patient,
        "visits": visits,
    })


@login_required
def patient_history(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    history = patient.medical_history.all().order_by("-created_at")
    return render(request, "billing/patient_history.html", {"patient": patient, "history": history})


@login_required
def patient_emr(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)

    # Get visits correctly ordered
    visits = PatientVisit.objects.filter(patient=patient).order_by("-created_at", "-id")

    # Determine which visit is active or selected
    visit_id = request.GET.get("visit")
    if visit_id:
        active_visit = get_object_or_404(PatientVisit, id=visit_id, patient=patient)
    else:
        active_visit = visits.first()

    alert = None
    alert_id = request.GET.get("alert")

    if alert_id:
        alert = VitalAlert.objects.filter(
            id=alert_id,
            patient=patient
        ).first()

    # Fetch related data
    medical_records = MedicalRecord.objects.filter(patient=patient).order_by("-created_at")

    latest_vitals = (
        VitalSign.objects
        .filter(patient=patient)
        .select_related("recorded_by")
        .first()
    )

    vitals_status = {}
    if latest_vitals:
        vitals_status = evaluate_vitals(latest_vitals)

    vital_signs = VitalSign.objects.filter(
        visit__patient=patient
    ).order_by("created_at")

    vitals = VitalSign.objects.filter(patient=patient).order_by("created_at")[:30]
    vital_data = []
    for v in vitals:
        status_map = evaluate_vitals(v)

        vital_data.append({
            "date": v.created_at.strftime("%Y-%m-%d %H:%M"),
            "systolic": v.blood_pressure_systolic,
            "diastolic": v.blood_pressure_diastolic,
            "temperature": float(v.temperature) if v.temperature else None,
            "pulse": v.heart_rate,
            "bp_status": status_map.get("blood_pressure", "normal"),
            "temp_status": status_map.get("temperature", "normal"),
            "pulse_status": status_map.get("pulse", "normal"),
        })

    lab_reports = LabReport.objects.filter(patient=patient).order_by("-date")
    radiology_reports = RadiologyReport.objects.filter(patient=patient).order_by("-created_at")
    prescriptions = Prescription.objects.filter(visit__patient=patient).select_related("doctor", "visit").order_by("-issued_at")

    # Active (non-resolved) vital alerts for this patient
    vital_alerts = VitalAlert.objects.filter(patient=patient).exclude(status="resolved")

    context = {
        "patient": patient,
        "medical_records": medical_records,
        "lab_reports": lab_reports,
        "radiology_reports": radiology_reports,
        "prescriptions": prescriptions,
        "active_visit": active_visit,
        "visits": visits,
        "vital_signs": vital_signs,
        "vital_alerts": vital_alerts,
        "vital_data_json": json.dumps(vital_data),
        "latest_vitals": latest_vitals,
        "vitals_status": vitals_status,
        "linked_alert": alert,
    }

    return render(request, "billing/patient_emr.html", context)


@login_required
def acknowledge_vital_alert(request, alert_id):
    alert = get_object_or_404(VitalAlert, id=alert_id)

    if request.user.is_doctor():
        alert.status = "acknowledged"
        alert.doctor = request.user
        alert.acknowledged_at = timezone.now()
        alert.escalation_deadline = None
        alert.save()

        VitalAlertLog.objects.create(
            alert=alert,
            action="acknowledged",
            performed_by=request.user,
            notes="Doctor acknowledged alert"
        )

    return redirect("patient_emr", patient_id=alert.patient.id)


@login_required
def resolve_vital_alert(request, alert_id):
    alert = get_object_or_404(VitalAlert, id=alert_id)

    if not request.user.is_doctor():
        messages.error(request, "Unauthorized action")
        return redirect("patient_emr", patient_id=alert.patient.id)

    if request.method == "POST":
        notes = request.POST.get("notes", "").strip()

        if not notes:
            messages.error(request, "Resolution notes are required")
            return redirect("resolve_vital_alert", alert_id=alert.id)

        alert.status = "resolved"
        alert.resolved_at = timezone.now()
        alert.save()

        VitalAlertLog.objects.create(
            alert=alert,
            action="resolved",
            performed_by=request.user,
            notes=notes
        )

        messages.success(request, "Alert resolved with clinical notes")
        return redirect("patient_emr", patient_id=alert.patient.id)

    return render(request, "billing/resolve_alert.html", {
        "alert": alert
    })


@login_required
def doctor_alert_dashboard(request):
    if not request.user.is_doctor():
        messages.error(request, "Unauthorized access")
        return redirect("dashboard")

    alerts = VitalAlert.objects.filter(
        status__in=["open", "acknowledged", "escalated"]
    ).select_related("patient").order_by("-created_at")

    for alert in alerts:
        alert.sla_remaining = sla_remaining_time(alert)
        alert.sla_state = sla_timer_state(alert)

    return render(request, "billing/doctor_alert_dashboard.html", {
        "alerts": alerts,
        "now": timezone.now(),
    })


@login_required
def doctor_scorecard(request, doctor_id):
    if not request.user.is_admin():
        return redirect("dashboard")

    doctor = get_object_or_404(CustomUser, id=doctor_id, role="doctor")
    hospital = request.user.hospital

    from billing.utils.sla_metrics import doctor_sla_metrics
    from billing.utils.scorecard import performance_grade

    metrics = doctor_sla_metrics(doctor, hospital)
    grade = performance_grade(
        metrics["sla_compliance"],
        metrics["escalations"]
    )

    return render(request, "billing/admin/doctor_scorecard.html", {
        "doctor": doctor,
        "metrics": metrics,
        "grade": grade,
    })


@login_required
def doctor_sla_dashboard(request):
    if not request.user.is_admin():
        return redirect("dashboard")

    hospital = request.user.hospital

    from billing.utils.sla_metrics import doctor_sla_metrics

    doctors = doctor_sla_metrics(hospital)

    return render(request, "billing/admin/doctor_sla_dashboard.html", {
        "doctors": doctors
    })

@login_required
def admin_alert_dashboard(request):
    user = request.user

    if not user.is_admin():
        return redirect("dashboard")

    alerts = VitalAlert.objects.filter(
        status__in=["open", "escalated"]
    ).select_related(
        "patient", "vital", "doctor"
    ).order_by("-created_at")

    return render(request, "billing/alerts/admin_dashboard.html", {
        "alerts": alerts,
        "now": timezone.now(),
    })


from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

@staff_member_required
def sla_settings(request):
    """Per-hospital SLA policy settings (Admin only)"""

    hospital = request.user.hospital

    return render(request, "billing/admin/sla_settings.html", {
        "hospital": hospital
    })


@login_required
def hospital_sla_settings(request):
    if not request.user.is_admin():
        return redirect("dashboard")

    hospital = request.user.hospital
    form = HospitalSLAForm(request.POST or None, instance=hospital)

    if form.is_valid():
        form.save()
        messages.success(request, "SLA policies updated successfully")

    return render(request, "billing/admin/hospital_sla.html", {
        "form": form
    })

from django.db.models import Avg, Count, F, DurationField, ExpressionWrapper

@login_required
def doctor_sla_leaderboard(request):
    if request.user.role not in ["admin", "doctor"]:
        return redirect("dashboard")

    doctors = (
        VitalAlert.objects
        .values("doctor__id", "doctor__full_name")
        .annotate(
            total=Count("id"),
            sla_met=Count(
                "id",
                filter=F("acknowledged_at__lte=F('acknowledge_deadline')")
            ),
            breached=Count(
                "id",
                filter=F("acknowledged_at__gt=F('acknowledge_deadline')")
            ),
            avg_response=Avg(
                ExpressionWrapper(
                    F("acknowledged_at") - F("created_at"),
                    output_field=DurationField()
                )
            )
        )
    )

    leaderboard = []
    for d in doctors:
        total = d["total"]
        sla_rate = round((d["sla_met"] / total) * 100, 1) if total else 0

        leaderboard.append({
            "name": d["doctor__full_name"],
            "total": total,
            "sla_rate": sla_rate,
            "breached": d["breached"],
            "avg_response": d["avg_response"],
        })

    # Sort by SLA rate (DESC), then avg response (ASC)
    leaderboard.sort(
        key=lambda x: (-x["sla_rate"], x["avg_response"] or 999999)
    )

    return render(
        request,
        "billing/doctor_sla_leaderboard.html",
        {"leaderboard": leaderboard}
    )

@login_required
def doctor_sla_self_view(request):
    user = request.user

    if user.role != "doctor":
        return redirect("dashboard")

    alerts = VitalAlert.objects.filter(doctor=user)

    total = alerts.count()

    acknowledged = alerts.filter(
        acknowledged_at__isnull=False,
        acknowledged_at__lte=F("acknowledge_deadline")
    ).count()

    breached = alerts.filter(
        acknowledged_at__gt=F("acknowledge_deadline")
    ).count()

    open_alerts = alerts.filter(status="open").count()

    avg_response = alerts.filter(
        acknowledged_at__isnull=False
    ).annotate(
        response_time=ExpressionWrapper(
            F("acknowledged_at") - F("created_at"),
            output_field=DurationField()
        )
    ).aggregate(avg=Avg("response_time"))["avg"]

    sla_rate = round((acknowledged / total) * 100, 1) if total else 0

    context = {
        "total": total,
        "acknowledged": acknowledged,
        "breached": breached,
        "open_alerts": open_alerts,
        "sla_rate": sla_rate,
        "avg_response": avg_response,
    }

    return render(request, "billing/doctor_sla_self.html", context)


@login_required
def department_sla_dashboard(request):
    if not request.user.is_admin():
        return redirect("dashboard")

    hospital = request.user.hospital

    from billing.utils.department_sla import department_sla_metrics

    departments = department_sla_metrics(hospital)

    return render(request, "billing/admin/department_sla_dashboard.html", {
        "departments": departments
    })



@login_required
def load_note_template(request, key):
    from .doctor_templates import DOCTOR_NOTE_TEMPLATES  # If stored separately

    template = DOCTOR_NOTE_TEMPLATES.get(key)

    if not template:
        return JsonResponse({"template": ""})

    return JsonResponse({"template": template})

@login_required
def add_emr_note(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)

    if request.method == "POST":
        notes = request.POST.get("notes")
        MedicalRecord.objects.create(
            patient=patient,
            doctor=request.user,
            notes=notes,
            note_type="doctor_note",
        )

        messages.success(request, "Doctor note added.")
        return redirect("patient_emr", patient_id=patient.id)


@login_required
def add_lab_report(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if request.method == "POST":
        form = LabReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.patient = patient
            report.lab_technician = request.user
            report.save()
            return redirect("patient_emr", patient_id=patient.id)
    else:
        form = LabReportForm()
    return render(request, "billing/add_lab_report.html", {"form": form, "patient": patient})


@login_required
def add_radiology_report(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if request.method == "POST":
        form = RadiologyReportForm(request.POST, patient=patient)
        if form.is_valid():
            report = form.save(commit=False)
            report.patient = patient
            report.radiologist = request.user
            report.save()
            messages.success(request, "Radiology report added successfully.")
            return redirect("add_radiology_report", patient_id=patient.id)
        messages.error(request, f"Form is invalid: {form.errors}")
    else:
        form = RadiologyReportForm(patient=patient)

    past_reports = RadiologyReport.objects.filter(patient=patient).order_by("-created_at")
    return render(
        request,
        "billing/add_radiology_report.html",
        {"form": form, "patient": patient, "past_reports": past_reports},
    )

from django.db.models.functions import TruncMonth
from django.db.models import Count, Avg, F
from datetime import timedelta
from django.utils.timezone import now

@login_required
def doctor_sla_trend(request, doctor_id=None):
    if request.user.role != "admin":
        return redirect("dashboard")

    alerts = VitalAlert.objects.all()

    if doctor_id:
        alerts = alerts.filter(doctor_id=doctor_id)

    data = (
        alerts
        .annotate(month=TruncMonth("created_at"))
        .values("doctor__full_name", "month")
        .annotate(
            total=Count("id"),
            sla_met=Count(
                "id",
                filter=F("acknowledged_at__lte=F('acknowledge_deadline')")
            )
        )
        .order_by("month")
    )

    trends = {}
    for row in data:
        name = row["doctor__full_name"]
        sla_rate = round((row["sla_met"] / row["total"]) * 100, 1) if row["total"] else 0

        trends.setdefault(name, []).append({
            "month": row["month"],
            "sla_rate": sla_rate,
        })

    # Detect trend direction
    for doctor, months in trends.items():
        for i in range(1, len(months)):
            prev = months[i - 1]["sla_rate"]
            curr = months[i]["sla_rate"]

            if curr > prev:
                months[i]["trend"] = "up"
            elif curr < prev:
                months[i]["trend"] = "down"
            else:
                months[i]["trend"] = "flat"

        if months:
            months[0]["trend"] = "flat"

    return render(
        request,
        "billing/doctor_sla_trend.html",
        {"trends": trends}
    )


@login_required
def create_prescription(request, visit_id):
    visit = get_object_or_404(PatientVisit, id=visit_id)

    if request.method == "POST":
        form = PrescriptionForm(request.POST)
        if form.is_valid():
            prescription = form.save(commit=False)
            prescription.hospital = visit.hospital
            prescription.doctor = request.user
            prescription.visit = visit
            prescription.save()
            messages.success(request, "Prescription created successfully.")
            return redirect("patient_emr", patient_id=visit.patient.id)
    else:
        form = PrescriptionForm(initial={"visit": visit, "doctor": request.user})

    return render(request, "billing/prescriptions/create_prescription.html", {"form": form, "visit": visit})


@login_required
def print_visit_prescriptions(request, visit_id):
    """Render a simple printable page showing prescriptions for a visit."""
    visit = get_object_or_404(PatientVisit, id=visit_id)
    prescriptions = Prescription.objects.filter(visit=visit).select_related("doctor")

    return render(
        request,
        "billing/print_visit_prescriptions.html",
        {
            "visit": visit,
            "prescriptions": prescriptions,
        },
    )

@login_required
def pending_prescriptions(request):
    prescriptions = Prescription.objects.filter(status="issued").select_related("doctor", "visit__patient")
    prescriptions = Prescription.objects.filter(
        status="issued"
    ).select_related("visit__patient", "doctor")
    return render(request, "billing/prescriptions/pending_prescriptions.html", {"prescriptions": prescriptions})


@login_required
def dispense_prescription(request, prescription_id):
    prescription = get_object_or_404(Prescription, id=prescription_id)

    if prescription.status == "issued":
        prescription.status = "dispensed"
        prescription.dispensed_at = timezone.now()
        prescription.save()
        messages.success(request, "Prescription marked as dispensed.")
    else:
        messages.warning(request, "This prescription was already dispensed.")

    return redirect("pending_prescriptions")

from django.template.loader import render_to_string
from django.http import HttpResponse
import tempfile

@login_required
def export_emr_pdf(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)

    medical_records = MedicalRecord.objects.filter(patient=patient)
    lab_reports = LabReport.objects.filter(patient=patient)
    radiology_reports = RadiologyReport.objects.filter(patient=patient)
    prescriptions = Prescription.objects.filter(visit__patient=patient)
    vital_signs = VitalSign.objects.filter(patient=patient)

    html_string = render_to_string("billing/print_emr.html", {
        "patient": patient,
        "medical_records": medical_records,
        "lab_reports": lab_reports,
        "radiology_reports": radiology_reports,
        "prescriptions": prescriptions,
        "vital_signs": vital_signs,
    })

    pdf_data = None
    # Try WeasyPrint first (may fail on systems without GTK/Pango libs)
    try:
        from weasyprint import HTML

        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=True) as temp_pdf:
            HTML(string=html_string).write_pdf(temp_pdf.name)

            temp_pdf.seek(0)
            pdf_data = temp_pdf.read()
    except Exception:
        # Fallback to xhtml2pdf (pisa) which is pure-Python
        try:
            from xhtml2pdf import pisa
            buffer = BytesIO()
            pisa_status = pisa.CreatePDF(html_string, dest=buffer, encoding="UTF-8")
            if pisa_status.err:
                return HttpResponse("PDF generation error", status=500)
            buffer.seek(0)
            pdf_data = buffer.getvalue()
        except Exception:
            return HttpResponse("PDF generation error: no PDF backend available", status=500)

    response = HttpResponse(pdf_data, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="EMR_{patient.full_name}.pdf"'
    return response


# =======================================================
# Autocomplete API Endpoint
# =======================================================

from django.http import JsonResponse

@login_required
def medicine_autocomplete(request):
    q = request.GET.get('q', '').strip()
    qs = Medicine.objects.filter(name__icontains=q)
    if hasattr(request.user, "hospital") and request.user.hospital:
        qs = qs.filter(hospital=request.user.hospital)
    results = [{"id": m.id, "name": m.name, "price": float(m.price), "qty": m.quantity} for m in qs[:10]]
    return JsonResponse(results, safe=False)



# =======================================================
# USER REGISTRATION
# =======================================================

def register(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            hospital, _ = Hospital.objects.get_or_create(name="Main Hospital")
            user.hospital = hospital
            user.save()
            messages.success(request, "Account created successfully.")
            return redirect("login")
    else:
        form = CustomUserCreationForm()
    return render(request, "registration/register.html", {"form": form})


# =======================================================
# ROLE-BASED DASHBOARDS (simple render)
# =======================================================

@login_required
def admin_dashboard(request):
    return render(request, "billing/dashboard_admin.html")

@login_required
def doctor_dashboard(request):
    patients = Patient.objects.filter(hospital=request.user.hospital)
    return render(request, "billing/dashboard_doctor.html", {"patients": patients})

@login_required
def receptionist_dashboard(request):
    return render(request, "billing/dashboard_receptionist.html")

@login_required
def accountant_dashboard(request):
    return render(request, "billing/dashboard_accountant.html")

@login_required
def radiologist_dashboard(request):
    return render(request, "billing/dashboard_radiologist.html")

@login_required
def lab_dashboard(request):
    return render(request, "billing/dashboard_lab.html")

@login_required
def pharmacist_dashboard(request):
    hospital = request.user.hospital
    prescriptions = Prescription.objects.filter(status='issued', hospital=hospital).order_by('-issued_at')

    # Daily Dispense Count
    today = timezone.now().date()
    daily_dispensed_count = Prescription.objects.filter(
        status='dispensed',
        hospital=hospital,
        dispensed_at__date=today
    ).count()

    print("Pharmacist Dashboard → Found prescriptions:", prescriptions.count())  # debug log
    for p in prescriptions:
        print(f"→ {p.id}: {p.medicines} ({p.status})")

    context = {
        "prescriptions": prescriptions,
        "daily_dispensed_count": daily_dispensed_count,
    }
    return render(request, "billing/pharmacist_dashboard.html", context)


# =======================================================
# Prescription and Dispenses
# =======================================================

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import Patient, Prescription, Medicine
from .forms import PrescriptionForm

# Doctor adds a prescription
@login_required
def add_prescription(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)

    # Get current active visit
    visit = PatientVisit.objects.filter(
        patient=patient,
        status="active"
    ).first()

    # Automatically create an active visit if none exists
    if not visit:
        visit = PatientVisit.objects.create(
            patient=patient,
            hospital=request.user.hospital,
            status="active"
        )

    if request.method == "POST":
        medicines = request.POST.get("medicines")
        dosage = request.POST.get("dosage") or "N/A"
        duration = request.POST.get("duration") or "N/A"
        instructions = request.POST.get("instructions") or "No special instructions"

        prescription = Prescription.objects.create(
            hospital=request.user.hospital,
            visit=visit,
            doctor=request.user,             # this is fine if Prescription model has doctor field
            medicines=medicines,
            dosage=dosage,
            duration=duration,
            instructions=instructions,
        )

        messages.success(request, "Prescription added successfully.")
        return redirect("patient_emr", patient_id=patient.id)

    return render(request, "billing/prescription_form.html", {"patient": patient})

# Pharmacist sees pending prescriptions
@login_required
def pending_prescriptions(request):
    prescriptions = Prescription.objects.filter(status="issued").select_related(
        "visit__patient", "doctor", "medicine"
    )
    prescriptions = Prescription.objects.filter(
        status="issued"
    ).select_related("visit__patient", "doctor")
    return render(request, "billing/prescriptions/pending_prescriptions.html", {"prescriptions": prescriptions})


# Pharmacist marks as dispensed (reduces stock)
from django.utils import timezone
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from .models import Prescription

@login_required
def dispense_prescription(request, prescription_id):
    prescription = get_object_or_404(Prescription, id=prescription_id)

    # Only pharmacist can dispense
    if request.user.role != "pharmacist":
        return HttpResponse("Unauthorized", status=403)

    prescription.status = "dispensed"
    prescription.pharmacist = request.user
    prescription.dispensed_at = timezone.now()
    prescription.save()

    messages.success(request, "Prescription dispensed successfully.")
    return redirect("pharmacist_dashboard")


@login_required
def medicine_list(request):
    if request.user.role != "pharmacist":
        messages.error(request, "Only pharmacists can view this page.")
        return redirect("dashboard")

    medicines = Medicine.objects.all()
    return render(request, "billing/medicine_list.html", {"medicines": medicines})


# =======================================================
# PHARMACIST PRESCRIPTION MANAGEMENT
# =======================================================

@login_required
def pharmacist_prescriptions(request):
    # Only pharmacists should access this page
    if request.user.role != "pharmacist":
        messages.error(request, "Access denied.")
        return redirect("dashboard")

    prescriptions = Prescription.objects.filter(status="issued").select_related("visit__patient", "doctor")
    return render(request, "billing/pharmacist_prescriptions.html", {"prescriptions": prescriptions})

@login_required
def pharmacist_dispense_prescription(request, prescription_id):
    prescription = get_object_or_404(Prescription, pk=prescription_id)

    # Security check
    if request.user.role != "pharmacist":
        messages.error(request, "Unauthorized access.")
        return redirect("dashboard")

    # POST: Pharmacist submits dispense form
    if request.method == "POST":
        notes = request.POST.get("dispensed_notes", "").strip()

        # -------------------------------
        # 1️⃣ Deduct medicine from inventory
        # -------------------------------
        lines = prescription.medicines.split("\n")  # medicine1 x 2
        errors = []

        for line in lines:
            if "x" not in line:
                continue

            med_name = line.split("x")[0].strip()
            qty_needed = int(line.split("x")[1].strip())

            try:
                med = Medicine.objects.get(
                    hospital=request.user.hospital,
                    name__iexact=med_name
                )
            except Medicine.DoesNotExist:
                errors.append(f"{med_name} is not found in inventory.")
                continue

            if med.quantity < qty_needed:
                errors.append(f"Not enough stock for: {med_name} (needed {qty_needed}, available {med.quantity})")
            else:
                # deduct from stock
                med.quantity -= qty_needed
                med.save()

        # If any errors, stop dispensing
        if errors:
            messages.error(request, "Unable to dispense prescription:")
            for e in errors:
                messages.error(request, e)
            return redirect("pharmacist_dispense_view", prescription_id=prescription.id)

        # -------------------------------
        # 2️⃣ Update prescription record
        # -------------------------------
        prescription.status = "dispensed"
        prescription.pharmacist = request.user
        prescription.dispensed_at = timezone.now()
        prescription.dispensed_notes = notes
        prescription.save()

        messages.success(request, "Prescription dispensed successfully.")
        return redirect("pharmacist_history")

    # GET request: show confirmation page
    return render(request, "billing/pharmacist_dispense_confirm.html", {
        "prescription": prescription
    })


from django.db import IntegrityError
from django.contrib import messages

@login_required
def add_medicine(request):
    if request.method == "POST":
        name = request.POST.get("name")
        price = request.POST.get("price")
        quantity = request.POST.get("quantity")

        if not name or not price or not quantity:
            messages.error(request, "All fields are required.")
            return redirect("add_medicine")

        try:
            price = float(price)
            quantity = int(quantity)
        except ValueError:
            messages.error(request, "Price and quantity must be valid numbers.")
            return redirect("add_medicine")

        try:
            Medicine.objects.create(
                hospital=request.user.hospital,
                name=name,
                price=price,
                quantity=quantity,
            )
            messages.success(request, f"{name} added successfully.")
            return redirect("medicine_list")

        except IntegrityError:
            messages.error(request, f"'{name}' already exists in your inventory.")
            return redirect("add_medicine")

    return render(request, "billing/add_medicine.html")


@login_required
def dispense_history(request):
    if request.user.role != "pharmacist":
        return HttpResponseForbidden("Not allowed.")

    history = Prescription.objects.filter(
        status="dispensed",
        pharmacist=request.user
    ).order_by("-dispensed_at")

    return render(request, "billing/dispense_history.html", {
        "history": history
    })

@login_required
def medicine_inventory(request):
    if request.user.role != "pharmacist":
        messages.error(request, "Unauthorized access.")
        return redirect("dashboard")

    medicines = Medicine.objects.filter(hospital=request.user.hospital)

    return render(request, "medicine_inventory.html", {
        "medicines": medicines
    })

@login_required
def doctor_prescriptions(request):
    if request.user.role != "doctor":
        messages.error(request, "Unauthorized access.")
        return redirect("dashboard")

    prescriptions = Prescription.objects.filter(
        doctor=request.user
    ).order_by('-issued_at')

    
    return render(request, "billing/doctor_prescriptions.html", {
        "prescriptions": prescriptions
    })

# =======================================================
# MEDICINE MANAGEMENT VIEWS
# =======================================================

from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib import messages
from .models import Medicine, StockLog
import csv
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator

@login_required
def medicine_list(request):
    hospital = request.user.hospital

    categories = MedicineCategory.objects.filter(hospital=hospital)

    q = request.GET.get("q", "")
    status = request.GET.get("status", "")
    selected_category = request.GET.get("category", "all")

    medicines = Medicine.objects.filter(hospital=hospital)

    # Search
    if q:
        medicines = medicines.filter(name__icontains=q)

    # Category
    if selected_category != "all":
        medicines = medicines.filter(category_id=selected_category)

    # Status filter
    low_stock_threshold = 10
    if status == "ok":
        medicines = medicines.filter(quantity__gt=low_stock_threshold)
    elif status == "low":
        medicines = medicines.filter(quantity__gt=0, quantity__lte=low_stock_threshold)
    elif status == "out":
        medicines = medicines.filter(quantity=0)

    paginator = Paginator(medicines.order_by("name"), 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "billing/medicine/medicine_list.html", {
        "categories": categories,
        "page_obj": page_obj,
        "selected_category": selected_category,
        "low_stock_threshold": low_stock_threshold,
    })


@login_required
def add_medicine(request):
    if not request.user.is_pharmacist() and not request.user.is_admin():
        return redirect("dashboard")

    hospital = request.user.hospital
    categories = MedicineCategory.objects.filter(hospital=hospital)

    if request.method == "POST":
        name = request.POST.get("name").strip()
        price = request.POST.get("price")
        quantity = request.POST.get("quantity")
        category_id = request.POST.get("category")
        
        category = MedicineCategory.objects.filter(id=category_id, hospital=hospital).first()

        # prevent duplicates
        if Medicine.objects.filter(hospital=hospital, name__iexact=name).exists():
            messages.error(request, "Medicine already exists.")
            return redirect("add_medicine")

        Medicine.objects.create(
            hospital=hospital,
            name=name,
            quantity=quantity,
            price=price,
            category=category,
        )

        messages.success(request, "Medicine added successfully.")
        return redirect("medicine_list")

    return render(request, "billing/medicine/add_medicine.html", {
        "categories": categories
   })



@login_required
def edit_medicine(request, pk):
    if not request.user.is_pharmacist() and not request.user.is_admin():
        return redirect("dashboard")

    hospital = request.user.hospital

    medicine = get_object_or_404(Medicine, id=pk, hospital=hospital)
    categories = MedicineCategory.objects.filter(hospital=hospital)

    if request.method == "POST":
        name = request.POST.get("name").strip()
        price = request.POST.get("price")
        quantity = request.POST.get("quantity")
        category_id = request.POST.get("category")

        # Validate category
        category = MedicineCategory.objects.filter(
            id=category_id, hospital=hospital
        ).first()

        # Prevent duplicate names on same hospital (except itself)
        if Medicine.objects.filter(
            hospital=hospital,
            name__iexact=name
        ).exclude(id=medicine.id).exists():
            messages.error(request, "A medicine with this name already exists.")
            return redirect("edit_medicine", pk=medicine.id)

        # Update safely
        medicine.name = name
        medicine.price = price
        medicine.quantity = quantity
        medicine.category = category
        medicine.save()

        messages.success(request, "Medicine updated successfully.")
        return redirect("medicine_list")

    return render(request, "billing/medicine/edit_medicine.html", {
        "medicine": medicine,
        "categories": categories,
    })


@login_required
def delete_medicine(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk, hospital=request.user.hospital)

    if request.method == "POST":
        medicine.delete()
        messages.success(request, "Medicine deleted.")
        return redirect("medicine_list")

    return render(request, "billing/medicine/delete_medicine_confirmation.html", {
        "medicine": medicine
    })


@login_required
def medicine_detail(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk, hospital=request.user.hospital)

    logs = StockLog.objects.filter(medicine=medicine).order_by("-timestamp")

    return render(request, "billing/medicine/medicine_details.html", {
        "medicine": medicine,
        "logs": logs
    })


@login_required
def stock_in(request, pk):
    med = get_object_or_404(Medicine, pk=pk, hospital=request.user.hospital)

    if request.method == "POST":
        qty = int(request.POST.get("quantity"))
        med.quantity += qty
        med.save()

        StockLog.objects.create(
            medicine=med,
            action="IN",
            quantity=qty,
            user=request.user
        )

        messages.success(request, f"Added {qty} units to stock.")
        return redirect("medicine_detail", pk=pk)

    return render(request, "billing/medicine/stock_form.html", {
        "medicine": med,
        "mode": "in"
    })

@login_required
def stock_out(request, pk):
    med = get_object_or_404(Medicine, pk=pk, hospital=request.user.hospital)

    if request.method == "POST":
        qty = int(request.POST.get("quantity"))

        if qty > med.quantity:
            messages.error(request, "Cannot remove more than available stock.")
            return redirect("medicine_detail", pk=pk)

        med.quantity -= qty
        med.save()

        StockLog.objects.create(
            medicine=med,
            action="OUT",
            quantity=qty,
            user=request.user
        )

        messages.success(request, f"Removed {qty} units from stock.")
        return redirect("medicine_detail", pk=pk)

    return render(request, "billing/medicine/stock_form.html", {
        "medicine": med,
        "mode": "out"
    })

#@login_required
def stock_logs_view(request):
    logs = StockLog.objects.filter(medicine__hospital=request.user.hospital)

    # Filters
    q = request.GET.get("q", "")
    med = request.GET.get("med", "")
    action = request.GET.get("action", "")

    if q:
        logs = logs.filter(
            Q(medicine__name__icontains=q) |
            Q(user__username__icontains=q)
        )

    if med:
        logs = logs.filter(medicine__id=med)

    if action in ["IN", "OUT"]:
        logs = logs.filter(action=action)

    logs = logs.order_by("-timestamp")

    medicines = Medicine.objects.filter(hospital=request.user.hospital)

    return render(request, "billing/medicine/stock_logs.html", {
        "logs": logs,
        "medicines": medicines
    })

@login_required
def inventory_dashboard(request):
    meds = Medicine.objects.filter(hospital=request.user.hospital)

    total_medicines = meds.count()
    low_stock_threshold = 10

    low_stock = meds.filter(quantity__gt=0, quantity__lte=low_stock_threshold).count()
    out_of_stock = meds.filter(quantity=0).count()
    total_quantity = meds.aggregate(total=Sum("quantity"))["total"] or 0

    recent_logs = StockLog.objects.filter(
        medicine__hospital=request.user.hospital
    ).order_by("-timestamp")[:10]

    return render(request, "billing/pharmacy/inventory_dashboard.html", {
        "total_medicines": total_medicines,
        "low_stock": low_stock,
        "out_of_stock": out_of_stock,
        "total_quantity": total_quantity,
        "recent_logs": recent_logs,
    })


# =======================================================
# EXPORT MEDICINES CSV
# =======================================================

@login_required
def export_medicines_csv(request):
    medicines = Medicine.objects.filter(hospital=request.user.hospital)

    # Apply search / filter
    q = request.GET.get("q", "")
    status = request.GET.get("status", "")
    low_threshold = 10

    if q:
        medicines = medicines.filter(name__icontains=q)

    if status == "low":
        medicines = medicines.filter(quantity__gt=0, quantity__lte=low_threshold)
    elif status == "out":
        medicines = medicines.filter(quantity=0)
    elif status == "ok":
        medicines = medicines.filter(quantity__gt=low_threshold)

    # CSV Output
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="medicine_inventory.csv"'

    writer = csv.writer(response)
    writer.writerow(["Medicine", "Price", "Quantity"])

    for med in medicines:
        writer.writerow([med.name, med.price, med.quantity])

    return response


# ------------------------------
# MEDICINE CATEGORY – ADD
# ------------------------------
@login_required
def add_category(request):

    # ---- ROLE CHECK FIX ----
    if request.user.role not in ["pharmacist", "admin"]:
        return redirect("dashboard")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()

        if not name:
            messages.error(request, "Category name cannot be empty.")
            return redirect("category_list")

        # Prevent duplicate categories for the same hospital
        if MedicineCategory.objects.filter(
            hospital=request.user.hospital,
            name__iexact=name
        ).exists():
            messages.error(request, "Category already exists.")
            return redirect("category_list")

        # Create category
        MedicineCategory.objects.create(
            hospital=request.user.hospital,
            name=name
        )

        messages.success(request, "Category added successfully.")
        return redirect("category_list")   # FIXED

    return render(request, "billing/medicine/category_add.html")  # FIXED PATH


@login_required
def category_list(request):
    categories = MedicineCategory.objects.filter(hospital=request.user.hospital)
    return render(request, "billing/medicine/category_list.html", {
        "categories": categories
    })


@login_required
def edit_category(request, category_id):
    category = get_object_or_404(
        MedicineCategory,
        id=category_id,
        hospital=request.user.hospital
    )

    # Access control: only admin & pharmacist
    if request.user.role not in ["pharmacist", "admin"]:
        return redirect("dashboard")

    if request.method == "POST":
        name = request.POST.get("name").strip()

        # Avoid duplicates
        if MedicineCategory.objects.filter(
            hospital=request.user.hospital,
            name__iexact=name
        ).exclude(id=category.id).exists():
            messages.error(request, "A category with this name already exists.")
            return redirect("category_list")

        category.name = name
        category.save()

        messages.success(request, "Category updated successfully.")
        return redirect("category_list")

    return render(request, "billing/medicine/edit_category.html", {
        "category": category
    })



@login_required
def delete_category(request, cat_id):
    category = get_object_or_404(MedicineCategory, id=cat_id, hospital=request.user.hospital)

    if request.method == "POST":
        category.delete()
        messages.success(request, "Category deleted.")
        return redirect("category_list")

    return render(request, "billing/medicine/delete_category.html", {
        "category": category
    })

# ==============================
# VITAL SIGNS
# ==============================

@login_required
def add_vital_sign(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if request.method == "POST":
        visit = PatientVisit.objects.filter(patient=patient, status="active").first()

        def parse_int(val):
            return int(val) if val is not None and str(val).strip() else None

        def parse_float(val):
            return float(val) if val is not None and str(val).strip() else None

        systolic = parse_int(request.POST.get("systolic"))
        diastolic = parse_int(request.POST.get("diastolic"))
        heart_rate = parse_int(request.POST.get("pulse"))
        temperature = parse_float(request.POST.get("temperature"))
        respiratory_rate = parse_int(request.POST.get("respiratory_rate"))
        spo2 = parse_int(request.POST.get("spo2"))

        vital = VitalSign.objects.create(
            patient=patient,
            visit=visit,
            blood_pressure_systolic=systolic,
            blood_pressure_diastolic=diastolic,
            heart_rate=heart_rate,
            temperature=temperature,
            respiratory_rate=respiratory_rate,
            spo2=spo2,
            recorded_by=request.user,
        )

        # Evaluate the recorded vitals
        alerts_dict = evaluate_vitals(vital)
        request.session["vital_alerts"] = list(alerts_dict.items())

        # Create an alert record if any metric is critical
        if "critical" in alerts_dict.values():
            critical_items = "; ".join(f"{k}: {v}" for k, v in alerts_dict.items() if v == "critical")
            
            sla = SLAPolicy.objects.filter(
                hospital=patient.hospital,
                severity="critical",
                active=True
            ).first()

            now = timezone.now()
            if sla:
                acknowledge_deadline = now + timedelta(minutes=sla.response_time_minutes)
                escalation_deadline = now + timedelta(minutes=sla.escalation_time_minutes)
            else:
                acknowledge_deadline = None
                escalation_deadline = None

            alert = VitalAlert.objects.create(
                patient=patient,
                vital=vital,
                doctor=visit.assigned_doctor if visit else None,
                message=("Critical vital signs detected: " + critical_items) if critical_items else "Critical vital signs detected",
                sla_policy=sla,
                acknowledge_deadline=acknowledge_deadline,
                escalation_deadline=escalation_deadline,
            )

            VitalAlertLog.objects.create(
                alert=alert,
                action="created",
                performed_by=request.user,
                notes="System detected critical vitals"
            )

        # Determine overall status
        status_priority = {"critical": 2, "high": 1, "normal": 0}
        overall_status = "normal"
        alert_messages = []

        for metric, severity in alerts_dict.items():
            if status_priority.get(severity, 0) > status_priority.get(overall_status, 0):
                overall_status = severity
            if severity != "normal":
                alert_messages.append(f"{metric.replace('_', ' ').title()}: {severity}")

        vital.status = overall_status
        vital.alert_message = "; ".join(alert_messages)
        vital.save()

        if overall_status == "critical":
            messages.error(request, "⚠️ CRITICAL vitals recorded!")
        elif overall_status == "high":
            messages.warning(request, "⚠️ Abnormal vitals detected.")
        else:
            messages.success(request, "Vitals recorded successfully.")

        return redirect("patient_emr", patient_id=patient.id)

    return render(request, "billing/add_vitals.html", {"patient": patient})



@login_required
def patient_vitals_graphs(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)

    vitals = VitalSign.objects.filter(patient=patient).order_by("created_at")

    data = {
        "labels": [v.created_at.strftime("%d %b %H:%M") for v in vitals],
        "pulse": [v.heart_rate for v in vitals],
        "temperature": [float(v.temperature) if v.temperature else None for v in vitals],
        "systolic": [v.blood_pressure_systolic for v in vitals],
        "diastolic": [v.blood_pressure_diastolic for v in vitals],
    }

    return render(request, "billing/patient_vitals_graphs.html", {
        "patient": patient,
        "data": data,
    })



# ------------------------------------------------------------------
# NHIS CLAIMS DASHBOARD
# ------------------------------------------------------------------

@login_required
def nhis_claims_dashboard(request):
    nhis = Payer.objects.filter(code="NHIS").first()
    kschma = Payer.objects.filter(code="KSCHMA").first()

    # Bills where the linked ThirdPartyPayer is a government scheme
    government_bills = Bill.objects.filter(third_party__payer_type__in=["federal", "state"]) 

    nhis_bills = government_bills.filter(patient__patientcoverage__payer=nhis)
    kschma_bills = government_bills.filter(patient__patientcoverage__payer=kschma)

    def bill_totals(qs):
        return {
            "total": qs.aggregate(t=Sum("third_party_payable"))["t"] or 0,
            "paid": qs.filter(is_fully_paid=True).aggregate(p=Sum("third_party_payable"))["p"] or 0,
            "unpaid": qs.filter(is_fully_paid=False).aggregate(u=Sum("third_party_payable"))["u"] or 0,
        }

    context = {
        "nhis": bill_totals(nhis_bills),
        "kschma": bill_totals(kschma_bills),
        "nhis_bills": nhis_bills.order_by("-created_at"),
        "kschma_bills": kschma_bills.order_by("-created_at"),
    }

    return render(request, "billing/accountant/nhis_claims_dashboard.html", context)
