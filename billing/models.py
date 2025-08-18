# hospital_billing/billing/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
import uuid


class Hospital(models.Model):
    """
    Represents a hospital (or clinic) that owns this instance.
    All data is scoped to a hospital.
    """
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Hospital"
        verbose_name_plural = "Hospitals"


class CustomUser(AbstractUser):
    """
    Extended user model with role and hospital affiliation.
    """
    USER_ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('receptionist', 'Receptionist'),
        ('doctor', 'Doctor'),
        ('lab', 'Lab Technician'),
        ('radiologist', 'Radiologist'),
        ('pharmacist', 'Pharmacist'),
        ('accountant', 'Accountant'),  # ✅ Added
    ]

    role = models.CharField(
        max_length=20,
        choices=USER_ROLE_CHOICES,
        default='receptionist'
    )

    hospital = models.ForeignKey(
        'Hospital',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    def is_admin(self):
        return self.role == 'admin'

    def is_doctor(self):
        return self.role == 'doctor'

    def is_receptionist(self):
        return self.role == 'receptionist'

    def is_lab_technician(self):
        return self.role == 'lab'

    def is_radiologist(self):
        return self.role == 'radiologist'

    def is_pharmacist(self):
        return self.role == 'pharmacist'

    def is_accountant(self):  # ✅ Now safe to define this
        return self.role == 'accountant'

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

class Patient(models.Model):
    hospital = models.ForeignKey('Hospital', on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    phone_number = models.CharField(max_length=15)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name

    class Meta:
        ordering = ['full_name']


class Service(models.Model):
    hospital = models.ForeignKey('Hospital', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return f"{self.name} - ${self.price}"

    class Meta:
        unique_together = ('hospital', 'name')


class Bill(models.Model):
    hospital = models.ForeignKey('Hospital', on_delete=models.CASCADE)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    invoice_no = models.CharField(max_length=20, unique=True, default=uuid.uuid4)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice {self.invoice_no} - {self.patient}"

    class Meta:
        ordering = ['-created_at']


class BillItem(models.Model):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='items')
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        self.subtotal = self.service.price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.service.name} x{self.quantity}"


class Payment(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('transfer', 'Bank Transfer'),
    ]

    hospital = models.ForeignKey('Hospital', on_delete=models.CASCADE)
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    paid_on = models.DateTimeField(auto_now_add=True)
    payment_mode = models.CharField(max_length=50, choices=PAYMENT_METHODS)

    def __str__(self):
        return f"{self.bill.invoice_no} - ${self.amount_paid}"


class AuditLog(models.Model):
    ACTIONS = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=10, choices=ACTIONS)
    model_name = models.CharField(max_length=50)
    object_id = models.PositiveIntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)
    description = models.TextField()

    def __str__(self):
        return f"{self.timestamp} - {self.user} - {self.action} {self.model_name} ({self.object_id})"

    class Meta:
        ordering = ['-timestamp']


class Appointment(models.Model):
    hospital = models.ForeignKey('Hospital', on_delete=models.CASCADE)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        limit_choices_to={'role': 'doctor'}
    )
    date = models.DateField()
    time = models.TimeField()
    reason = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20,
        choices=[
            ('scheduled', 'Scheduled'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled')
        ],
        default='scheduled'
    )

    def __str__(self):
        return f"{self.patient} with Dr. {self.doctor} on {self.date}"

    class Meta:
        unique_together = ('doctor', 'date', 'time')
        ordering = ['date', 'time']


class Medicine(models.Model):
    hospital = models.ForeignKey('Hospital', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return self.name

    class Meta:
        unique_together = ('hospital', 'name')


class PatientVisit(models.Model):
    hospital = models.ForeignKey('Hospital', on_delete=models.CASCADE)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    assigned_doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='visits',
        limit_choices_to={'role': 'doctor'}
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='assigned_visits',
        limit_choices_to={'role': 'receptionist'}
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('under_diagnosis', 'Under Diagnosis'),
            ('lab_requested', 'Lab Requested'),
            ('lab_completed', 'Lab Completed'),
            ('radiology_requested', 'Radiology Requested'),
            ('radiology_completed', 'Radiology Completed'),
            ('prescribed', 'Prescribed'),
            ('completed', 'Completed'),
        ],
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.patient} - {self.status}"

    class Meta:
        ordering = ['-created_at']


class LabTestRequest(models.Model):
    hospital = models.ForeignKey('Hospital', on_delete=models.CASCADE)
    visit = models.ForeignKey(PatientVisit, on_delete=models.CASCADE)
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='lab_requests',
        limit_choices_to={'role': 'doctor'}
    )
    lab_technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_labs',
        limit_choices_to={'role': 'lab'}
    )
    test_type = models.CharField(max_length=100)
    notes = models.TextField(blank=True)
    result = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=[('requested', 'Requested'), ('completed', 'Completed')],
        default='requested'
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.test_type} - {self.status}"


class RadiologyRequest(models.Model):
    hospital = models.ForeignKey('Hospital', on_delete=models.CASCADE)
    visit = models.ForeignKey(PatientVisit, on_delete=models.CASCADE)
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='radiology_requests',
        limit_choices_to={'role': 'doctor'}
    )
    radiologist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_radiologies',
        limit_choices_to={'role': 'radiologist'}
    )
    imaging_type = models.CharField(max_length=100)
    notes = models.TextField(blank=True)
    findings = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=[('requested', 'Requested'), ('completed', 'Completed')],
        default='requested'
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.imaging_type} - {self.status}"


class Prescription(models.Model):
    hospital = models.ForeignKey('Hospital', on_delete=models.CASCADE)
    visit = models.ForeignKey(PatientVisit, on_delete=models.CASCADE)
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='prescriptions_made',
        limit_choices_to={'role': 'doctor'}
    )
    pharmacist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prescriptions_filled',
        limit_choices_to={'role': 'pharmacist'}
    )
    medicines = models.TextField(help_text="Format: Drug name - dosage - duration")
    status = models.CharField(
        max_length=20,
        choices=[('issued', 'Issued'), ('dispensed', 'Dispensed')],
        default='issued'
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    dispensed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Rx for {self.visit.patient} by {self.doctor}"


class Message(models.Model):
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='received_messages')
    subject = models.CharField(max_length=255)
    content = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"From {self.sender} to {self.receiver}: {self.subject}"

