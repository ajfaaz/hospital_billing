# billing/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib import messages
from django.db.models import Sum, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone

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
    Message,
)
from .forms import (
    BillItemForm,
    PaymentForm,
    AppointmentForm,
    CustomUserCreationForm,
    MessageForm,
)
from .utils import log_action
from io import BytesIO
from django.template.loader import get_template
from xhtml2pdf import pisa


# ======================
# DASHBOARD & HOME
# ======================

@login_required
def dashboard(request):
    user = request.user
    income_by_month = (
        Payment.objects.annotate(month=TruncMonth('paid_on'))
        .values('month')
        .annotate(total=Sum('amount_paid'))
        .order_by('month')
    )
    labels = [entry['month'].strftime('%b %Y') for entry in income_by_month]
    data = [entry['total'] for entry in income_by_month]

    context = {
        'chart_labels': labels,
        'chart_data': data,
        'patient_count': Patient.objects.filter(hospital=user.hospital).count(),
        'appointment_count': Appointment.objects.filter(hospital=user.hospital).count(),
        'bill_count': Bill.objects.filter(hospital=user.hospital).count(),
        'total_income': Payment.objects.aggregate(total=Sum('amount_paid'))['total'] or 0,
    }

    # Map role to template
    template_map = {
        'admin': 'billing/dashboard_admin.html',
        'doctor': 'billing/dashboard_doctor.html',
        'receptionist': 'billing/dashboard_receptionist.html',
        'accountant': 'billing/dashboard_accountant.html',
        'radiologist': 'billing/dashboard_radiologist.html',
        'lab_technician': 'billing/dashboard_lab.html',
        'pharmacist': 'billing/dashboard_pharmacist.html',
    }

    template = template_map.get(user.role, 'billing/dashboard.html')
    return render(request, template, context)


from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

def home(request):
    if request.user.is_authenticated:
        # Redirect logged-in users to their role dashboard
        if request.user.role == 'admin':
            return redirect('admin_dashboard')
        elif request.user.role == 'doctor':
            return redirect('doctor_dashboard')
        elif request.user.role == 'receptionist':
            return redirect('receptionist_dashboard')
        elif request.user.role == 'accountant':
            return redirect('accountant_dashboard')
        elif request.user.role == 'radiologist':
            return redirect('radiologist_dashboard')
        elif request.user.role == 'lab':
            return redirect('lab_dashboard')
        elif request.user.role == 'pharmacist':
            return redirect('pharmacist_dashboard')
        else:
            return redirect('dashboard')  # fallback
    else:
        # Show welcome page to guests
        return render(request, 'home.html')



# ======================
# PATIENT MANAGEMENT
# ======================

@login_required
def patient_list(request):
    query = request.GET.get('q', '')
    # For now, fetch all patients until hospital linking is implemented
    if query:
        patients = Patient.objects.filter(full_name__icontains=query)
    else:
        patients = Patient.objects.all()

    return render(request, 'billing/patient_list.html', {
        'patients': patients,
        'query': query
    })


@login_required
def create_patient(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        dob = request.POST.get('dob')
        phone = request.POST.get('phone')

        hospital = request.user.hospital
        if not hospital:
            messages.error(request, "No hospital found.")
            return redirect('receptionist_dashboard')

        patient = Patient.objects.create(
            full_name=name,
            date_of_birth=dob,
            phone_number=phone,
            hospital=hospital
        )
        messages.success(request, 'Patient created successfully.')
        # Redirect to appointment form with this patient pre-selected
        return redirect(f'/appointments/create/?patient={patient.id}')

    return render(request, 'billing/create_patient.html')

from django.db.models import Q
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Appointment, Patient, CustomUser

# ======================
# APPOINTMENT LIST
# ======================
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
            Q(patient__full_name__icontains=query) |
            Q(reason__icontains=query)
        )

    appointments = appointments.select_related("patient", "doctor").order_by("-date", "-time")

    return render(request, "billing/appointment_list.html", {
        "appointments": appointments,
        "query": query
    })


# ======================
# CREATE APPOINTMENT
# ======================
@login_required
def create_appointment(request):
    try:
        hospital = request.user.hospital
        patients = Patient.objects.filter(hospital=hospital)
        doctors = CustomUser.objects.filter(role='doctor', hospital=hospital)

        # Preselect patient if provided
        preselected_patient_id = request.GET.get("patient")

        if request.method == 'POST':
            patient_id = request.POST.get('patient')
            doctor_id = request.POST.get('doctor')
            date = request.POST.get('date')
            time = request.POST.get('time')
            reason = request.POST.get('reason')

            patient = get_object_or_404(Patient, id=patient_id, hospital=hospital)
            doctor = get_object_or_404(CustomUser, id=doctor_id, hospital=hospital)

            Appointment.objects.create(
                hospital=hospital,
                patient=patient,
                doctor=doctor,
                date=date,
                time=time,
                reason=reason,
                status='scheduled'
            )
            messages.success(request, "Appointment created successfully.")
            return redirect('appointment_list')

        return render(request, 'billing/create_appointment.html', {
            'patients': patients,
            'doctors': doctors,
            'preselected_patient_id': preselected_patient_id
        })

    except Exception as e:
        print(f"Error creating appointment: {e}")
        return HttpResponse("Server error", status=500)


# ======================
# BILLING & INVOICES
# ======================

@login_required
def create_bill(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    services = Service.objects.filter(hospital=patient.hospital)

    if request.method == 'POST':
        items_data = []
        total = 0
        service_ids = request.POST.getlist('service')
        quantities = request.POST.getlist('quantity')

        for i in range(len(service_ids)):
            service = get_object_or_404(Service, id=service_ids[i])
            qty = int(quantities[i])
            subtotal = service.price * qty
            total += subtotal
            items_data.append({
                'service': service,
                'quantity': qty,
                'subtotal': subtotal
            })

        bill = Bill.objects.create(
            patient=patient,
            total_amount=total,
            created_by=request.user,
            hospital=patient.hospital
        )
        log_action(request.user, 'create', 'Bill', bill.id, f"Created bill of ${total} for {patient}")

        for item in items_data:  # ✅ Fixed: was `items_`
            BillItem.objects.create(
                bill=bill,
                service=item['service'],
                quantity=item['quantity'],
                subtotal=item['subtotal']
            )

        return redirect('view_invoice', bill_id=bill.id)

    return render(request, 'billing/create_bill.html', {
        'patient': patient,
        'services': services
    })

@login_required
def view_invoice(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    items = bill.items.all()
    payments = bill.payment_set.all()
    paid = sum(p.amount_paid for p in payments)
    due = bill.total_amount - paid

    return render(request, 'billing/invoice.html', {
        'bill': bill,
        'items': items,
        'payments': payments,
        'paid': paid,
        'due': due
    })


@login_required
def download_invoice_pdf(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    items = bill.items.all()
    payments = bill.payment_set.all()
    paid = sum(p.amount_paid for p in payments)
    due = bill.total_amount - paid

    context = {
        'bill': bill,
        'items': items,
        'payments': payments,
        'paid': paid,
        'due': due
    }

    template = get_template('billing/invoice.html')
    html = template.render(context)

    buffer = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=buffer, encoding='UTF-8')
    buffer.seek(0)

    if pisa_status.err:
        return HttpResponse('PDF generation error', status=500)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{bill.invoice_no}.pdf"'
    return response


@login_required
def record_payment(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    if request.method == 'POST':
        amount = request.POST.get('amount')
        payment_method = request.POST.get('payment_method')
        Payment.objects.create(
            bill=bill,
            amount_paid=amount,
            payment_mode=payment_method,
            hospital=bill.hospital
        )
        messages.success(request, "Payment recorded successfully.")
        return redirect('view_invoice', bill_id=bill.id)
    return render(request, 'billing/record_payment.html', {'bill': bill})


# ======================
# REPORTS & LOGS
# ======================

@login_required
def income_report(request):
    payments = Payment.objects.all().order_by('-paid_on')
    total_income = payments.aggregate(total=Sum('amount_paid'))['total'] or 0

    monthly_data = payments.annotate(month=TruncMonth('paid_on')) \
        .values('month') \
        .annotate(total=Sum('amount_paid')) \
        .order_by('month')

    labels = [item['month'].strftime('%B %Y') for item in monthly_data]
    data = [float(item['total']) for item in monthly_data]

    return render(request, 'billing/income_report.html', {
        'payments': payments,
        'total_income': total_income,
        'labels': labels,
        'data': data,
    })


@login_required
def audit_logs(request):
    if not (request.user.role in ['admin', 'accountant']):
        return HttpResponseForbidden("You are not authorized to view this page.")
    logs = AuditLog.objects.all().order_by('-timestamp')
    return render(request, 'billing/audit_logs.html', {'logs': logs})


# ======================
# MESSAGING SYSTEM
# ======================

@login_required
def inbox(request):
    messages_list = Message.objects.filter(recipient=request.user).order_by('-timestamp')
    return render(request, 'billing/inbox.html', {'messages': messages_list})


@login_required
def sent_messages(request):
    messages_list = Message.objects.filter(sender=request.user).order_by('-timestamp')
    return render(request, 'billing/sent.html', {'messages': messages_list})


@login_required
def send_message(request):
    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.sender = request.user
            msg.save()
            messages.success(request, "Message sent.")
            return redirect('inbox')
    else:
        form = MessageForm()
    return render(request, 'billing/send_message.html', {'form': form})


# ======================
# ROLE-BASED DASHBOARDS
# ======================

@login_required
def redirect_by_role(request):
    user = request.user
    role_redirects = {
        'admin': 'admin_dashboard',
        'doctor': 'doctor_dashboard',
        'receptionist': 'receptionist_dashboard',
        'accountant': 'accountant_dashboard',
        'radiologist': 'radiologist_dashboard',
        'lab_technician': 'lab_dashboard',
        'pharmacist': 'pharmacist_dashboard',
    }
    return redirect(role_redirects.get(user.role, 'dashboard'))


@login_required
def admin_dashboard(request):
    return render(request, 'billing/dashboard_admin.html')


@login_required
def doctor_dashboard(request):
    return render(request, 'billing/dashboard_doctor.html')


@login_required
def receptionist_dashboard(request):
    return render(request, 'billing/dashboard_receptionist.html')


@login_required
def accountant_dashboard(request):
    return render(request, 'billing/dashboard_accountant.html')


@login_required
def radiologist_dashboard(request):
    return render(request, 'billing/dashboard_radiologist.html')


@login_required
def lab_dashboard(request):
    return render(request, 'billing/dashboard_lab.html')


@login_required
def pharmacist_dashboard(request):
    return render(request, 'billing/dashboard_pharmacist.html')


# ======================
# USER REGISTRATION
# ======================

from .models import Hospital

def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()

            # Always link to Main Hospital
            hospital, created = Hospital.objects.get_or_create(name="Main Hospital")
            user.hospital = hospital
            user.save()

            messages.success(request, 'Account created successfully.')
            return redirect('login')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/register.html', {'form': form})
