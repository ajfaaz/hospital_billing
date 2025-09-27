from io import BytesIO
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, Max
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import get_template

from xhtml2pdf import pisa

from .forms import (
    BillItemForm,
    PaymentForm,
    AppointmentForm,
    CustomUserCreationForm,
    MedicalRecordForm,
    LabReportForm,
    RadiologyReportForm,
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
)
from .utils import log_action

from messaging.forms import MessageForm
from messaging.models import Message

User = get_user_model()

# =======================================================
# DASHBOARD
# =======================================================

@login_required
def dashboard(request):
    user = request.user
    income_by_month = (
        Payment.objects.annotate(month=TruncMonth("paid_on"))
        .values("month")
        .annotate(total=Sum("amount_paid"))
        .order_by("month")
    )
    labels = [entry["month"].strftime("%b %Y") for entry in income_by_month]
    data = [entry["total"] for entry in income_by_month]

    unread_count = Message.objects.filter(recipient=user, is_read=False).count()

    context = {
        "chart_labels": labels,
        "chart_data": data,
        "patient_count": Patient.objects.filter(hospital=user.hospital).count(),
        "appointment_count": Appointment.objects.filter(hospital=user.hospital).count(),
        "bill_count": Bill.objects.filter(hospital=user.hospital).count(),
        "total_income": Payment.objects.aggregate(total=Sum("amount_paid"))["total"] or 0,
        "unread_count": unread_count,
    }

    template_map = {
        "admin": "billing/dashboard_admin.html",
        "doctor": "billing/dashboard_doctor.html",
        "receptionist": "billing/dashboard_receptionist.html",
        "accountant": "billing/dashboard_accountant.html",
        "radiologist": "billing/dashboard_radiologist.html",
        "lab_technician": "billing/dashboard_lab.html",
        "pharmacist": "billing/dashboard_pharmacist.html",
    }
    template = template_map.get(user.role, "billing/dashboard.html")
    return render(request, template, context)


# =======================================================
# HOME & ROLE REDIRECT
# =======================================================

def home(request):
    if request.user.is_authenticated:
        role_dashboard_map = {
            "admin": "admin_dashboard",
            "doctor": "doctor_dashboard",
            "receptionist": "receptionist_dashboard",
            "accountant": "accountant_dashboard",
            "radiologist": "radiologist_dashboard",
            "lab_technician": "lab_dashboard",
            "pharmacist": "pharmacist_dashboard",
        }
        return redirect(role_dashboard_map.get(request.user.role, "dashboard"))
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
def create_bill(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    services = Service.objects.filter(hospital=patient.hospital)

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

        bill = Bill.objects.create(
            patient=patient,
            total_amount=total,
            created_by=request.user,
            hospital=patient.hospital,
        )
        log_action(request.user, "create", "Bill", bill.id, f"Created bill of ${total} for {patient}")

        for item in items_data:
            BillItem.objects.create(bill=bill, service=item["service"], quantity=item["quantity"], subtotal=item["subtotal"])

        return redirect("view_invoice", bill_id=bill.id)

    return render(request, "billing/create_bill.html", {"patient": patient, "services": services})


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
    patient = get_object_or_404(Patient, id=patient_id)
    if request.method == "POST":
        form = MedicalRecordForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.patient = patient
            record.doctor = request.user
            record.save()
            return redirect("patient_history", patient_id=patient.id)
    else:
        form = MedicalRecordForm()
    return render(request, "billing/add_medical_record.html", {"form": form, "patient": patient})


@login_required
def patient_history(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    history = patient.medical_history.all().order_by("-created_at")
    return render(request, "billing/patient_history.html", {"patient": patient, "history": history})


@login_required
def patient_emr(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    medical_records = MedicalRecord.objects.filter(patient=patient).order_by("-created_at")
    lab_reports = LabReport.objects.filter(patient=patient).order_by("-date")
    radiology_reports = RadiologyReport.objects.filter(patient=patient).order_by("-created_at")
    return render(
        request,
        "billing/patient_emr.html",
        {
            "patient": patient,
            "medical_records": medical_records,
            "lab_reports": lab_reports,
            "radiology_reports": radiology_reports,
        },
    )


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
    return render(request, "billing/dashboard_pharmacist.html")
