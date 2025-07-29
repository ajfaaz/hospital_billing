from django.urls import path
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView
from . import views
from .views import AuditLogListView
from .views import (
    # other views...
    radiologist_dashboard,
    lab_dashboard,
    pharmacist_dashboard,
)


urlpatterns = [
    # === Authentication & Onboarding ===
    path('', views.home, name='home'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('register/', views.register, name='register'),
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),


    # Password reset
    path('password-reset/',
         auth_views.PasswordResetView.as_view(template_name='registration/password_reset_form.html'),
         name='password_reset'),
    path('password-reset/done/',
         auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'),
         name='password_reset_done'),
    path('reset/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'),
         name='password_reset_confirm'),
    path('reset/done/',
         auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'),
         name='password_reset_complete'),

    # === Dashboard & Role-Based Redirect ===
    path('dashboard/', views.dashboard, name='dashboard'),
    path('redirect-by-role/', views.redirect_by_role, name='redirect_by_role'),
 

    # === Receptionist Routes ===
    path('receptionist-dashboard/', views.receptionist_dashboard, name='receptionist_dashboard'),
    path('receptionist/patients/add/', views.create_patient, name='create_patient'),
    path('receptionist/appointments/create/', views.create_appointment, name='create_appointment'),
    path('receptionist/appointments/', views.appointment_list, name='appointment_list'),
    path('receptionist/assign-patient/', views.assign_patient_to_doctor, name='assign_patient_to_doctor'),
    



    # === Patient Management (General) ===
    path('patients/', views.patient_list, name='patient_list'),
    

    # === Billing Routes ===
    path('bills/create/<int:patient_id>/', views.create_bill, name='create_bill'),
    path('bills/<int:bill_id>/payment/', views.record_payment, name='record_payment'),
    path('bills/<int:bill_id>/invoice/', views.view_invoice, name='view_invoice'),
    path('bills/<int:bill_id>/invoice/pdf/', views.download_invoice_pdf, name='download_invoice_pdf'),

    # === Reports & Audit ===
    path('reports/income/', views.income_report, name='income_report'),
    path('audit-logs/', views.audit_logs, name='audit_logs'),
    path('audit-logs/', AuditLogListView.as_view(), name='audit_logs'),

    # === Dashboards (Role-Specific) ===
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('doctor-dashboard/', views.doctor_dashboard, name='doctor_dashboard'),
    path('accountant-dashboard/', views.accountant_dashboard, name='accountant_dashboard'),
    path('radiologist/dashboard/', radiologist_dashboard, name='radiologist_dashboard'),
    path('lab/dashboard/', lab_dashboard, name='lab_dashboard'),
    path('pharmacist/dashboard/', pharmacist_dashboard, name='pharmacist_dashboard'),

    # Optional: General appointment access (can be same as receptionist one)
    # path('appointments/', views.appointment_list, name='appointment_list'),
]