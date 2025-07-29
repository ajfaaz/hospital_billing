from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import BillItem, Payment, Appointment
from .models import Patient

class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ['full_name', 'date_of_birth', 'phone_number']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
        }


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
        fields = ("username", "email", "role", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.role = self.cleaned_data["role"]
        if commit:
            user.save()
        return user



class BillItemForm(forms.ModelForm):
    class Meta:
        model = BillItem
        fields = '__all__'


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = '__all__'


# Appointment Form
from django.forms.widgets import DateInput, TimeInput, Textarea, Select

class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ['patient', 'date', 'time', 'reason']
        widgets = {
            'date': DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }, format='%Y-%m-%d'),  # ✅ Required format!
            'time': TimeInput(attrs={
                'type': 'time',
                'class': 'form-control'
            }, format='%H:%M'),  # Optional, but good practice
            'reason': Textarea(attrs={
                'rows': 3,
                'class': 'form-control'
            }),
            'patient': Select(attrs={
                'class': 'form-select'
            }),
        }

    def __init__(self, *args, **kwargs):
        super(AppointmentForm, self).__init__(*args, **kwargs)
        self.fields['date'].input_formats = ['%Y-%m-%d']  # ✅ Match HTML date format
        self.fields['time'].input_formats = ['%H:%M']     # 🕐 Match HTML time format

    def save(self, commit=True):  # line 63
        appointment = super().save(commit=False)
        if commit:
            appointment.save()
        return appointment
