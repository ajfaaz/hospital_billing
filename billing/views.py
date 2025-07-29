from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import login
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
)
from .forms import (
    BillItemForm,
    PaymentForm,
    AppointmentForm,
    CustomUserCreationForm,
)
from .utils import log_action
from io import BytesIO
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.http import HttpResponseServerError
from django.shortcuts import render, redirect
from .models import Patient, Hospital
from django.http import HttpResponseForbidden



@login_required
def dashboard(request):
    user = request.user

    # Income Chart Data
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
        'patient_count': Patient.objects.count(),
        'appointment_count': Appointment.objects.count(),
        'bill_count': Bill.objects.count(),
        'total_income': Payment.objects.aggregate(total=Sum('amount_paid'))['total'] or 0,
    }

    # Dynamic dashboard template based on user role
    if user.is_admin():
        return render(request, 'billing/dashboard_admin.html', context)
    elif user.is_doctor():
        return render(request, 'billing/dashboard_doctor.html', context)
    elif user.is_receptionist():
        return render(request, 'billing/dashboard_receptionist.html', context)
    elif hasattr(user, 'is_accountant') and user.is_accountant():
        return render(request, 'billing/dashboard_accountant.html', context)
    else:
        return render(request, 'billing/dashboard.html', context)


@login_required
def home(request):
    patient_count = Patient.objects.count()
    appointment_count = Appointment.objects.count()
    bill_count = Bill.objects.count()
    return render(request, 'billing/home.html', {
        'patient_count': patient_count,
        'appointment_count': appointment_count,
        'bill_count': bill_count,
    })


@login_required
def patient_list(request):
    hospital = request.user.hospital
    query = request.GET.get('q', '')
    
    if query:
        patients = Patient.objects.filter(
            hospital=hospital,
            full_name__icontains=query
        )
    else:
        patients = Patient.objects.filter(hospital=hospital)
        
    return render(request, 'billing/patient_list.html', {
        'patients': patients,
        'query': query
    })


@login_required
def appointment_list(request):
    query = request.GET.get('q')
    appointments = Appointment.objects.all()
    if query:
        appointments = appointments.filter(
            Q(patient__full_name__icontains=query) |
            Q(reason__icontains=query)
        )
    return render(request, 'billing/appointment_list.html', {
        'appointments': appointments
    })


from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Hospital
from .forms import PatientForm

@login_required
def create_patient(request):
    if request.method == 'POST':
        form = PatientForm(request.POST)
        if form.is_valid():
            patient = form.save(commit=False)
            hospital = Hospital.objects.first()  # Adjust based on user or context
            if not hospital:
                messages.error(request, "No hospital found.")
                return redirect('receptionist_dashboard')

            patient.hospital = hospital
            patient.save()
            messages.success(request, 'Patient created successfully.')
            return redirect('patient_list')  # Replace with correct view name
        else:
            messages.error(request, "Please correct the form errors.")
    else:
        form = PatientForm()

    # ✅ Always return a response, even if GET or invalid POST
    return render(request, 'billing/create_patient.html', {'form': form})


@login_required
def create_appointment(request):
    try:
        hospital = request.user.hospital
        patients = Patient.objects.filter(hospital=hospital)
        doctors = CustomUser.objects.filter(role='doctor')

        if request.method == 'POST':
            patient_id = request.POST.get('patient')
            doctor_id = request.POST.get('doctor')
            date = request.POST.get('date')
            time = request.POST.get('time')
            reason = request.POST.get('reason')

            patient = Patient.objects.get(id=patient_id)
            doctor = CustomUser.objects.get(id=doctor_id)

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
            'doctors': doctors
        })

    except Exception as e:
        print(f"Error creating appointment: {e}")
        return HttpResponseServerError("Internal Server Error")


@login_required
def create_bill(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    services = Service.objects.all()

    if request.method == 'POST':
        items_data = []
        total = 0
        service_ids = request.POST.getlist('service')
        quantities = request.POST.getlist('quantity')

        for i in range(len(service_ids)):
            service = Service.objects.get(id=service_ids[i])
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
            hospital=patient.hospital  # ✅ Ensure bill is assigned to patient's hospital
        )
        log_action(request.user, 'create', 'Bill', bill.id, f"Created bill of ${total} for {patient}")

        for item in items_data:
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
    paid = sum(payment.amount_paid for payment in payments)
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
    paid = sum(payment.amount_paid for payment in payments)
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
            hospital=bill.hospital  # ✅ Assign to same hospital
        )
        messages.success(request, "Payment recorded successfully.")
        return redirect('view_invoice', bill_id=bill_id)

    return render(request, 'billing/record_payment.html', {
        'bill': bill
    })


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
    if not (request.user.is_authenticated and (request.user.role == 'admin' or request.user.role == 'accountant')):
        return HttpResponseForbidden("You are not authorized to view this page.")
    
    logs = AuditLog.objects.all().order_by('-timestamp')
    return render(request, 'billing/audit_logs.html', {'logs': logs})

def register(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('redirect_by_role')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


@login_required
def redirect_by_role(request):
    user = request.user
    if user.is_admin():
        return redirect('admin_dashboard')
    elif user.is_doctor():
        return redirect('doctor_dashboard')
    elif user.is_receptionist():
        return redirect('receptionist_dashboard')
    elif hasattr(user, 'is_accountant') and user.is_accountant():
        return redirect('accountant_dashboard')
    else:
        return redirect('dashboard')


# Dashboard Views (Simple redirects to templates)
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

@login_required
def redirect_by_role(request):
    user = request.user
    if user.is_admin():
        return redirect('admin_dashboard')
    elif user.is_doctor():
        return redirect('doctor_dashboard')
    elif user.is_receptionist():
        return redirect('receptionist_dashboard')
    elif hasattr(user, 'is_accountant') and user.is_accountant():
        return redirect('accountant_dashboard')
    elif user.is_radiologist():
        return redirect('radiologist_dashboard')
    elif user.is_lab_technician():
        return redirect('lab_dashboard')
    elif user.is_pharmacist():
        return redirect('pharmacist_dashboard')
    else:
        return redirect('dashboard')



from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import PatientVisit, Patient, CustomUser
from django.contrib import messages

@login_required
def assign_patient_to_doctor(request):
    if request.method == 'POST':
        patient_id = request.POST.get('patient_id')
        doctor_id = request.POST.get('doctor_id')

        patient = get_object_or_404(Patient, id=patient_id)
        doctor = get_object_or_404(CustomUser, id=doctor_id, role='doctor')

        visit = PatientVisit.objects.create(
            patient=patient,
            assigned_doctor=doctor,
            assigned_by=request.user,
            hospital=request.user.hospital
        )

        messages.success(request, f"Patient {patient.full_name} assigned to {doctor.username}.")
        return redirect('receptionist_dashboard')

    patients = Patient.objects.filter(hospital=request.user.hospital)
    doctors = CustomUser.objects.filter(hospital=request.user.hospital, role='doctor')

    return render(request, 'billing/assign_patient.html', {
        'patients': patients,
        'doctors': doctors
    })

from django.contrib.auth.decorators import login_required, user_passes_test

def is_admin_or_receptionist(user):
    return user.is_authenticated and (user.is_admin() or user.is_receptionist())


from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from .models import AuditLog

class RoleRequiredMixin:
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("You must be logged in.")
        if request.user.role not in self.allowed_roles:
            raise PermissionDenied("You are not authorized to view this page.")
        return super().dispatch(request, *args, **kwargs)

class AuditLogListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    model = AuditLog
    template_name = 'billing/audit_logs.html'
    context_object_name = 'logs'
    ordering = ['-timestamp']
    allowed_roles = ['admin', 'accountant']
