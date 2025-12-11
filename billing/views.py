from io import BytesIO
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, Max
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import get_template
from .models import MedicineCategory


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
    VitalSign,
)
from .utils import log_action
import json

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

        MedicalRecord.objects.create(
            patient=patient,
            visit=visit,
            title=title,
            notes=notes,
            created_by=request.user,
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
            visit=visit,
            doctor=request.user,
            notes=notes,
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

    # Fetch related data
    medical_records = MedicalRecord.objects.filter(patient=patient).order_by("-created_at")

    vital_signs = VitalSign.objects.filter(
        visit__patient=patient
    ).order_by("created_at")

    lab_reports = LabReport.objects.filter(patient=patient).order_by("-date")
    radiology_reports = RadiologyReport.objects.filter(patient=patient).order_by("-created_at")
    prescriptions = Prescription.objects.filter(visit__patient=patient).select_related("doctor", "visit").order_by("-issued_at")

    return render(
        request,
        "billing/patient_emr.html",
        {
            "patient": patient,
            "medical_records": medical_records,
            "lab_reports": lab_reports,
            "radiology_reports": radiology_reports,
            "prescriptions": prescriptions,
            "active_visit": active_visit,
            "visits": visits,
            "vital_signs": vital_signs,
        },
    )

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
    prescriptions = Prescription.objects.filter(status='issued').order_by('-issued_at')

    print("Pharmacist Dashboard → Found prescriptions:", prescriptions.count())  # debug log
    for p in prescriptions:
        print(f"→ {p.id}: {p.medicines} ({p.status})")

    context = {
        "prescriptions": prescriptions,
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
            doctor=request.user,
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
def edit_medicine(request, med_id):
    if not request.user.is_pharmacist() and not request.user.is_admin():
        return redirect("dashboard")

    hospital = request.user.hospital

    medicine = get_object_or_404(Medicine, id=med_id, hospital=hospital)
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
            return redirect("edit_medicine", med_id=medicine.id)

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
        bp = (request.POST.get("bp") or "").strip()
        systolic = None
        diastolic = None
        if "/" in bp:
            parts = bp.split("/")
            try:
                systolic = int(parts[0].strip())
            except Exception:
                systolic = None
            try:
                diastolic = int(parts[1].strip())
            except Exception:
                diastolic = None

        # try to attach an active visit if available
        visit = PatientVisit.objects.filter(patient=patient, status="active").first()

        VitalSign.objects.create(
            patient=patient,
            visit=visit,
            systolic=systolic,
            diastolic=diastolic,
            pulse=request.POST.get("pulse") or None,
            temperature=request.POST.get("temp") or None,
            respiratory_rate=request.POST.get("resp") or None,
            spo2=request.POST.get("spo2") or None,
            recorded_by=request.user,
        )
        messages.success(request, "Vital signs recorded successfully!")
        return redirect("patient_emr", patient_id=patient.id)

    return render(request, "billing/add_vitals.html", {
        "patient": patient,
    })


# ------------------------------------------------------------------
# Doctor note templates (global constant)
# ------------------------------------------------------------------
DOCTOR_NOTE_TEMPLATES = {
    "soap":
    """**S: Subjective**
- Chief Complaint: 
- History of Present Illness: 
- Review of Systems: 

**O: Objective**
- Vital Signs: 
- Physical Examination: 

**A: Assessment**
- Working Diagnosis: 

**P: Plan**
- Labs/Imaging Requested:
- Medications:
- Follow-up:""",

    "hpi":
    """**History of Present Illness**
- Onset:
- Duration:
- Severity:
- Quality:
- Aggravating/Relieving Factors:
- Associated Symptoms:
- Previous Episodes:""",

    "assessment":
    """**Assessment**
- Primary Diagnosis:
- Differential Diagnosis #1: 
- Differential Diagnosis #2:
- Summary:""",

    "plan":
    """**Management Plan**
- Medications:
- Investigations:
- Procedures:
- Advice/Education:
- Follow-up:""",

    "quick":
    """**Quick Note**
- Summary:
- Action Taken:
- Next Steps:""",
}
