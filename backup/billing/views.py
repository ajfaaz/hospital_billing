from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.template.loader import get_template
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from xhtml2pdf import pisa
import io
from datetime import datetime
from .models import Appointment  # make sure this model exists
from .models import Patient, Service, Bill, BillItem, Payment, Appointment, AuditLog
from .forms import BillItemForm, PaymentForm, AppointmentForm
from .utils import log_action

# billing/views.py
from .forms import CustomUserCreationForm
from django.contrib.auth import login
from django.shortcuts import render, redirect
from .forms import CustomUserCreationForm
from django.shortcuts import redirect
from django.db.models.functions import TruncMonth
from .models import Payment
import json
from django.db.models import Q
from django.utils import timezone
from django.db.models import Sum



def income_report(request):
    payments = Payment.objects.all().order_by('paid_on')

    labels = [payment.paid_on.strftime('%Y-%m-%d') for payment in payments]
    data = [float(payment.amount_paid) for payment in payments]

    return render(request, 'billing/income_report.html', {
        'labels': json.dumps(labels),
        'data': json.dumps(data),
    })


@login_required
def income_report(request):
    payments = Payment.objects.all().order_by('-paid_on')
    total_income = payments.aggregate(total=Sum('amount_paid'))['total'] or 0

    # Group income by month
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
def redirect_by_role(request):
    user = request.user

    if user.is_admin():
        return redirect('/admin/')  # or your admin dashboard
    elif user.is_doctor():
        return redirect('/doctor-dashboard/')
    elif user.is_receptionist():
        return redirect('/receptionist-dashboard/')
    elif user.is_accountant():
        return redirect('/accountant-dashboard/')
    else:
        return redirect('/')  # default fallback


def register(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('redirect_by_role')  # Redirect based on role
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/register.html', {'form': form})

def home(request):
    patient_count = Patient.objects.count()
    appointment_count = Appointment.objects.count()
    bill_count = Bill.objects.count()

    return render(request, 'billing/home.html', {
        'patient_count': patient_count,
        'appointment_count': appointment_count,
        'bill_count': bill_count,
    })


def view_audit_logs(request):
    if not request.user.is_superuser:
        return HttpResponse("Access Denied")
    logs = AuditLog.objects.all().order_by('-timestamp')
    return render(request, 'audit/logs.html', {'logs': logs})


@login_required
def audit_logs(request):
    logs = AuditLog.objects.order_by('-timestamp')[:100]
    return render(request, 'billing/audit_logs.html', {'logs': logs})


@login_required
def income_report(request):
    payments = Payment.objects.all().order_by('-paid_on')
    total_income = payments.aggregate(total=Sum('amount_paid'))['total'] or 0
    return render(request, 'billing/income_report.html', {
        'payments': payments,
        'total_income': total_income
    })


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
        'chart_labels': json.dumps(labels),
        'chart_data': json.dumps(data)
    }

    # Dynamic dashboard template
    if user.is_admin():
        return render(request, 'billing/dashboard_admin.html', context)
    elif user.is_doctor():
        return render(request, 'billing/dashboard_doctor.html', context)
    elif user.is_receptionist():
        return render(request, 'billing/dashboard_receptionist.html', context)
    elif user.is_accountant():
        return render(request, 'billing/dashboard_accountant.html', context)
    return render(request, 'billing/dashboard.html', context)



@login_required
def patient_list(request):
    query = request.GET.get('q')
    if query:
        patients = Patient.objects.filter(
            Q(full_name__icontains=query) | Q(phone__icontains=query)
        )
    else:
        patients = Patient.objects.all()
    return render(request, 'billing/patient_list.html', {'patients': patients, 'query': query})




@login_required
def create_bill(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    services = Service.objects.all()

    if request.method == 'POST':
        items_data = []
        total = 0
        for i in range(len(request.POST.getlist('service'))):
            service_id = request.POST.getlist('service')[i]
            qty = int(request.POST.getlist('quantity')[i])
            service = Service.objects.get(id=service_id)
            subtotal = service.price * qty
            total += subtotal
            items_data.append({'service': service, 'quantity': qty, 'subtotal': subtotal})

        bill = Bill.objects.create(
            patient=patient,
            total_amount=total,
            created_by=request.user
        )

        log_action(request.user, 'create', 'Bill', bill.id, f"Created bill of ${total} for {patient}")

        for item in items_data:
            BillItem.objects.create(
                bill=bill,
                service=item['service'],
                quantity=item['quantity'],
                subtotal=item['subtotal']
            )

        return redirect('view_invoice', bill.id)

    return render(request, 'billing/create_bill.html', {'patient': patient, 'services': services})


@login_required
def record_payment(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.bill = bill
            payment.save()
            return redirect('view_invoice', bill.id)
    else:
        form = PaymentForm()
    return render(request, 'billing/record_payment.html', {'form': form, 'bill': bill})


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

    template = get_template('billing/invoice_pdf.html')
    html = template.render({
        'bill': bill,
        'items': items,
        'payments': payments,
        'paid': paid,
        'due': due,
    })

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{bill.invoice_no}.pdf"'

    pisa_status = pisa.CreatePDF(io.StringIO(html), dest=response)
    if pisa_status.err:
        return HttpResponse('PDF generation failed')
    return response


@login_required
def appointment_list(request):
    query = request.GET.get('q')
    appointments = Appointment.objects.all()

    if query:
        appointments = appointments.filter(
            Q(patient__name__icontains=query) |
            Q(reason__icontains=query)
        )

    return render(request, 'billing/appointment_list.html', {'appointments': appointments})




@login_required
def create_appointment(request):
    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('appointment_list')
    else:
        form = AppointmentForm()
    return render(request, 'billing/create_appointment.html', {'form': form})


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
def dashboard(request):
    user = request.user

    context = {
        'patient_count': Patient.objects.count(),
        'appointment_count': Appointment.objects.count(),
        'bill_count': Bill.objects.count(),
        'total_income': Payment.objects.aggregate(total=Sum('amount_paid'))['total'] or 0,
    }

    if user.is_admin():
        return render(request, 'billing/dashboard_admin.html', context)
    elif user.is_doctor():
        return render(request, 'billing/dashboard_doctor.html', context)
    elif user.is_receptionist():
        return render(request, 'billing/dashboard_receptionist.html', context)
    elif user.is_accountant():
        return render(request, 'billing/dashboard_accountant.html', context)
    else:
        return render(request, 'billing/dashboard.html', context)  # fallback

@login_required
def dashboard(request):
    user = request.user

    context = {
        'patient_count': Patient.objects.count(),
        'appointment_count': Appointment.objects.count(),
        'bill_count': Bill.objects.count(),
        'total_income': Payment.objects.aggregate(total=Sum('amount_paid'))['total'] or 0,
    }

    if user.is_admin():
        return render(request, 'billing/dashboard_admin.html', context)
    elif user.is_doctor():
        return render(request, 'billing/dashboard_doctor.html', context)
    elif user.is_receptionist():
        return render(request, 'billing/dashboard_receptionist.html', context)
    elif user.is_accountant():
        return render(request, 'billing/dashboard_accountant.html', context)
    else:
        return render(request, 'billing/dashboard.html', context)


