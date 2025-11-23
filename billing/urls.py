from django.urls import path
from . import views

urlpatterns = [
    # Home & Dashboard
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('redirect-by-role/', views.redirect_by_role, name='redirect_by_role'),

    # Patients
    path('patients/', views.patient_list, name='patient_list'),
    path('patients/add/', views.create_patient, name='create_patient'),
    path('patients/<int:patient_id>/history/add/', views.add_medical_record, name='add_medical_record'),
    path('patients/<int:patient_id>/history/', views.patient_history, name='patient_history'),
    path('patients/<int:patient_id>/emr/', views.patient_emr, name='patient_emr'),
    path('patients/<int:patient_id>/lab/add/', views.add_lab_report, name='add_lab_report'),
    path('patients/<int:patient_id>/radiology/add/', views.add_radiology_report, name='add_radiology_report'),

    # Appointments
    path('appointments/', views.appointment_list, name='appointment_list'),
    path('appointments/create/', views.create_appointment, name='create_appointment'),

    # Billing
    path('bills/create/<int:patient_id>/', views.create_bill, name='create_bill'),
    path('bills/<int:bill_id>/invoice/', views.view_invoice, name='view_invoice'),
    path('bills/<int:bill_id>/invoice/pdf/', views.download_invoice_pdf, name='download_invoice_pdf'),
    path('bills/<int:bill_id>/payment/', views.record_payment, name='record_payment'),

    # Reports
    path('reports/income/', views.income_report, name='income_report'),
    path('audit-logs/', views.audit_logs, name='audit_logs'),

    # Messaging
    path("messages/inbox/", views.inbox, name="inbox"),
    path("messages/sent/", views.sent_messages, name="sent_messages"),
    path("messages/compose/", views.compose_message, name="compose_message"),
    path("messages/<int:pk>/", views.message_detail, name="message_detail"),
    path("conversation/<int:sender_id>/", views.conversation, name="conversation"),

    # Role Dashboards
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('doctor-dashboard/', views.doctor_dashboard, name='doctor_dashboard'),
    path('receptionist-dashboard/', views.receptionist_dashboard, name='receptionist_dashboard'),
    path('accountant-dashboard/', views.accountant_dashboard, name='accountant_dashboard'),
    path('radiologist-dashboard/', views.radiologist_dashboard, name='radiologist_dashboard'),
    path('lab-dashboard/', views.lab_dashboard, name='lab_dashboard'),
    path("pharmacist/dashboard/", views.pharmacist_dashboard, name="pharmacist_dashboard"),

    # Registration
    path('register/', views.register, name='register'),

    # Prescriptions
    path("doctor/prescriptions/", views.doctor_prescriptions, name="doctor_prescriptions"),
    path("pharmacist/medicines/", views.medicine_inventory, name="medicine_inventory"),
    path("patients/<int:patient_id>/prescription/add/", views.add_prescription, name="add_prescription"),
    path("prescriptions/pending/", views.pending_prescriptions, name="pending_prescriptions"),
    path("pharmacist/medicines/add/", views.add_medicine, name="add_medicine"),
    path(
        "pharmacist/history/",
        views.dispense_history,
        name="dispense_history"
 ),



    # ✅ Pharmacist-specific routes
    path(
        "pharmacist/prescriptions/",
        views.pharmacist_prescriptions,
        name="pharmacist_prescriptions"
    ),
    path(
        "pharmacist/prescriptions/<int:prescription_id>/dispense/",
        views.dispense_prescription,
        name="pharmacist_dispense_prescription"
    ),
    path(
        "pharmacist/medicines/",
        views.medicine_list,
        name="medicine_list"
    ),
]

