from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
import uuid


# ==============================
# CORE ORGANIZATIONAL MODELS
# ==============================

class Hospital(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name


class CustomUser(AbstractUser):
    USER_ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('receptionist', 'Receptionist'),
        ('doctor', 'Doctor'),
        ('lab', 'Lab Technician'),
        ('radiologist', 'Radiologist'),
        ('pharmacist', 'Pharmacist'),
        ('accountant', 'Accountant'),
    ]

    role = models.CharField(max_length=20, choices=USER_ROLE_CHOICES, default='receptionist')
    hospital = models.ForeignKey(Hospital, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    # ✅ Add these helper methods
    def is_admin(self):
        return self.role == "admin"

    def is_pharmacist(self):
        return self.role == "pharmacist"

    def is_doctor(self):
        return self.role == "doctor"

    def is_receptionist(self):
        return self.role == "receptionist"

    def is_lab(self):
        return self.role == "lab"

    def is_radiologist(self):
        return self.role == "radiologist"

    def is_accountant(self):
        return self.role == "accountant"



# ==============================
# PATIENT & VISIT MANAGEMENT
# ==============================

class Patient(models.Model):
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    phone_number = models.CharField(max_length=20)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name


class PatientVisit(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('under_diagnosis', 'Under Diagnosis'),
        ('lab_requested', 'Lab Requested'),
        ('lab_completed', 'Lab Completed'),
        ('radiology_requested', 'Radiology Requested'),
        ('radiology_completed', 'Radiology Completed'),
        ('prescribed', 'Prescribed'),
        ('completed', 'Completed'),
    ]

    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    assigned_doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="visits",
        limit_choices_to={'role': 'doctor'},
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="assigned_visits",
        limit_choices_to={'role': 'receptionist'},
    )
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.patient} - {self.status}"


# ==============================
# SERVICES & BILLING
# ==============================

class Service(models.Model):
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        unique_together = ('hospital', 'name')

    def __str__(self):
        return f"{self.name} - ₦{self.price}"


class Bill(models.Model):
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    invoice_no = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice {self.invoice_no}"


class BillItem(models.Model):
    bill = models.ForeignKey(Bill, related_name='items', on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        self.subtotal = self.service.price * self.quantity
        super().save(*args, **kwargs)


class Payment(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('transfer', 'Bank Transfer'),
    ]

    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE)
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    paid_on = models.DateTimeField(auto_now_add=True)
    payment_mode = models.CharField(max_length=50, choices=PAYMENT_METHODS)

    def __str__(self):
        return f"{self.bill.invoice_no} - ₦{self.amount_paid}"


# ==============================
# MEDICINES & CATEGORIES
# ==============================

class MedicineCategory(models.Model):
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    class Meta:
        unique_together = ('hospital', 'name')

    def __str__(self):
        return self.name


class Medicine(models.Model):
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(MedicineCategory, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = ('hospital', 'name')

    def __str__(self):
        return self.name


# ==============================
# PRESCRIPTIONS & STOCK LOGS
# ==============================

class Prescription(models.Model):
    STATUS_CHOICES = [('issued', 'Issued'), ('dispensed', 'Dispensed')]

    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE)
    visit = models.ForeignKey(PatientVisit, on_delete=models.CASCADE)
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="prescriptions_made",
        limit_choices_to={'role': 'doctor'},
    )
    pharmacist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prescriptions_filled",
        limit_choices_to={'role': 'pharmacist'},
    )
    medicines = models.TextField()
    dosage = models.CharField(max_length=100, default="N/A")
    duration = models.CharField(max_length=100, default="N/A")
    instructions = models.TextField(default="No special instructions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='issued')
    issued_at = models.DateTimeField(auto_now_add=True)
    dispensed_at = models.DateTimeField(null=True, blank=True)
    dispensed_notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Rx for {self.visit.patient}"


class StockLog(models.Model):
    ACTIONS = [('in', 'Stock In'), ('out', 'Stock Out'), ('adjust', 'Adjustment')]

    medicine = models.ForeignKey(Medicine, related_name='stock_logs', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=10, choices=ACTIONS)
    quantity = models.IntegerField()
    notes = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']


# ==============================
# LAB & RADIOLOGY
# ==============================

class LabTestRequest(models.Model):
    STATUS_CHOICES = [('requested', 'Requested'), ('completed', 'Completed')]

    hospital = models.ForeignKey('Hospital', on_delete=models.CASCADE)
    visit = models.ForeignKey(PatientVisit, on_delete=models.CASCADE)

    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='lab_tests_requested',
        limit_choices_to={'role': 'doctor'}
    )

    lab_technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lab_tests_performed',
        limit_choices_to={'role': 'lab'}
    )

    test_type = models.CharField(max_length=100)
    notes = models.TextField(blank=True)
    result = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='requested')
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.test_type} - {self.status}"


class RadiologyRequest(models.Model):
    STATUS_CHOICES = [('requested', 'Requested'), ('completed', 'Completed')]

    hospital = models.ForeignKey('Hospital', on_delete=models.CASCADE)
    visit = models.ForeignKey(PatientVisit, on_delete=models.CASCADE)

    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='radiology_tests_requested',
        limit_choices_to={'role': 'doctor'}
    )

    radiologist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='radiology_tests_performed',
        limit_choices_to={'role': 'radiologist'}
    )

    imaging_type = models.CharField(max_length=100)
    notes = models.TextField(blank=True)
    findings = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='requested')
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.imaging_type} - {self.status}"


# ==============================
# REPORTS
# ==============================

class LabReport(models.Model):
    patient = models.ForeignKey(Patient, related_name="lab_reports", on_delete=models.CASCADE)
    lab_technician = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    test_name = models.CharField(max_length=200)
    result = models.TextField()
    date = models.DateTimeField(auto_now_add=True)


class RadiologyReport(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    scan_type = models.CharField(max_length=100)
    report = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    radiologist = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)


# ==============================
# MEDICAL RECORDS & AUDIT
# ==============================

class MedicalRecord(models.Model):
    patient = models.ForeignKey(Patient, related_name="medical_history", on_delete=models.CASCADE)
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    diagnosis = models.TextField()
    treatment = models.TextField()
    notes = models.TextField(blank=True, null=True)
    prescribed_medicines = models.ManyToManyField(Medicine, blank=True, related_name="medical_records")
    created_at = models.DateTimeField(auto_now_add=True)


class AuditLog(models.Model):
    ACTIONS = [('create', 'Create'), ('update', 'Update'), ('delete', 'Delete')]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=10, choices=ACTIONS)
    model_name = models.CharField(max_length=50)
    object_id = models.PositiveIntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)
    description = models.TextField()

    class Meta:
        ordering = ['-timestamp']


# ==============================
# APPOINTMENTS
# ==============================

class Appointment(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    date = models.DateField()
    time = models.TimeField()
    reason = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')

    class Meta:
        unique_together = ('doctor', 'date', 'time')
        ordering = ['date', 'time']


# ==============================
# VITAL SIGNS
# ==============================

class VitalSign(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    visit = models.ForeignKey(PatientVisit, on_delete=models.CASCADE, null=True, blank=True)

    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True)
    pulse = models.PositiveIntegerField(null=True)
    respiratory_rate = models.PositiveIntegerField(null=True)
    systolic = models.PositiveIntegerField(null=True)
    diastolic = models.PositiveIntegerField(null=True)
    spo2 = models.PositiveIntegerField(null=True)

    recorded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
