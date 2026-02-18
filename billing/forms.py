from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.forms.widgets import DateInput, TimeInput, Textarea, Select
from .models import (
    Patient,
    PatientCoverage,
    Payer,
    Appointment,
    Bill,
    BillItem,
    Payment,
    MedicalRecord,
    LabReport,
    RadiologyReport,
    CustomUser,
    Prescription,
)

# ----------------- PATIENT -----------------
class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ['full_name', 'date_of_birth', 'phone_number', 'address']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
        }


class PatientRegistrationForm(forms.ModelForm):
    payer = forms.ModelChoiceField(
        queryset=Payer.objects.all(),
        required=True,
        label="Payment Scheme"
    )

    class Meta:
        model = Patient
        fields = [
            "full_name",
            "date_of_birth",
            "phone_number",
            "address",
        ]

    def save(self, commit=True):
        patient = super().save(commit=commit)

        # Only create coverage when the patient has been saved (commit=True).
        if commit:
            payer = self.cleaned_data.get('payer')
            if payer:
                PatientCoverage.objects.update_or_create(
                    patient=patient,
                    defaults={
                        'payer': payer,
                        'patient_percentage': 0,
                        'government_percentage': 100,
                        'active': True,
                    }
                )

        return patient


# ----------------- USER -----------------
User = get_user_model()

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(
        choices=User.USER_ROLE_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = User
        fields = ("username", "email", "role", "specialty", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.role = self.cleaned_data["role"]
        if commit:
            user.save()
        return user


# ----------------- BILLING -----------------
class BillItemForm(forms.ModelForm):
    class Meta:
        model = BillItem
        fields = '__all__'


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = '__all__'


# ----------------- APPOINTMENT -----------------
class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ['patient', 'date', 'time', 'reason']
        widgets = {
            'date': DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'time': TimeInput(attrs={'type': 'time', 'class': 'form-control'}, format='%H:%M'),
            'reason': Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'patient': Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].input_formats = ['%Y-%m-%d']
        self.fields['time'].input_formats = ['%H:%M']

    def save(self, commit=True):
        appointment = super().save(commit=False)
        if commit:
            appointment.save()
        return appointment


        # Group recipients by role
        roles = CustomUser.objects.values_list('role', flat=True).distinct()
        grouped_choices = []
        for role in roles:
            users = CustomUser.objects.filter(role=role)
            choices = [(u.id, f"{u.username}") for u in users]
            grouped_choices.append((role.capitalize(), choices))

        self.fields['recipient'].choices = grouped_choices
        self.fields['subject'].widget.attrs.update({'class': 'form-control'})
        self.fields['body'].widget.attrs.update({'class': 'form-control', 'rows': 5})


# ----------------- MEDICAL RECORD -----------------
class MedicalRecordForm(forms.ModelForm):
    class Meta:
        model = MedicalRecord
        fields = ["patient", "diagnosis", "treatment", "notes"]  # ✅ fixed (note not notes)

from django import forms
from .models import LabReport

class LabReportForm(forms.ModelForm):
    class Meta:
        model = LabReport
        fields = ["test_name", "result"]   


class RadiologyReportForm(forms.ModelForm):
    patient_name = forms.CharField(
        label="Patient",
        required=False,
        disabled=True,   # ✅ readonly
    )

    class Meta:
        model = RadiologyReport
        fields = ["patient_name", "scan_type", "report"]  # ✅ show patient but not editable

    def __init__(self, *args, **kwargs):
        patient = kwargs.pop("patient", None)
        super().__init__(*args, **kwargs)
        if patient:
            self.fields["patient_name"].initial = patient.full_name



# ----------------- Prescription -----------------
from django import forms
from .models import Prescription

class PrescriptionForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = ["medicines", "dosage", "duration", "instructions"]
        widgets = {
            "medicines": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "Enter one medicine per line, e.g.\nParacetamol 500mg - twice daily\nIbuprofen 200mg - after meals"
                }
            ),
            "dosage": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., 1 tablet"}),
            "duration": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., 5 days"}),
            "instructions": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Additional notes for the patient"
                }
            ),
        }

# ----------------- Hospital SLA Form -----------------

from .models import Hospital, SLAPolicy

class HospitalSLAForm(forms.ModelForm):
    class Meta:
        model = Hospital
        fields = [
            "sla_doctor_ack_minutes",
            "sla_head_doctor_minutes",
            "sla_admin_minutes",
        ]

class SLAPolicyForm(forms.ModelForm):
    class Meta:
        model = SLAPolicy
        fields = [
            "severity",
            "response_time_minutes",
            "escalation_time_minutes",
            "max_escalation_level",
            "active",
        ]
