from django.urls import path
from . import views
from django.contrib.auth.views import LogoutView
from django.contrib.auth import views as auth_views
from .views import (
    admin_dashboard,
    doctor_dashboard,
    receptionist_dashboard,
    accountant_dashboard,
)


    

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('patients/', views.patient_list, name='patient_list'),
    path('bills/create/<int:patient_id>/', views.create_bill, name='create_bill'),
    path('bills/<int:bill_id>/payment/', views.record_payment, name='record_payment'),
    path('bills/<int:bill_id>/invoice/', views.view_invoice, name='view_invoice'),
    path('bills/<int:bill_id>/invoice/pdf/', views.download_invoice_pdf, name='download_invoice_pdf'),
    path('reports/income/', views.income_report, name='income_report'),
    path('logs/audit/', views.audit_logs, name='audit_logs'),
    path('appointments/', views.appointment_list, name='appointment_list'),
    path('appointments/new/', views.create_appointment, name='create_appointment'),
    path('register/', views.register, name='register'),
    path('admin-dashboard/', admin_dashboard, name='admin_dashboard'),
    path('doctor-dashboard/', doctor_dashboard, name='doctor_dashboard'),
    path('receptionist-dashboard/', receptionist_dashboard, name='receptionist_dashboard'),
    path('accountant-dashboard/', accountant_dashboard, name='accountant_dashboard'),
    
    # Auth
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),

    
    
    # other paths...
    path('redirect-by-role/', views.redirect_by_role, name='redirect_by_role'),


    # Password reset
    path('password-reset/', auth_views.PasswordResetView.as_view(template_name='registration/password_reset_form.html'), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='password_reset_complete'),
]
