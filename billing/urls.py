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
    path('patients/<int:patient_id>/doctor-note/add/', views.add_doctor_note, name='add_doctor_note'),
    path('patients/<int:patient_id>/', views.patient_detail, name='patient_detail'),
    path('patients/<int:patient_id>/emr/', views.patient_emr, name='patient_emr'),
    path('patients/<int:patient_id>/lab/add/', views.add_lab_report, name='add_lab_report'),
    path("patients/<int:patient_id>/emr/print/", views.export_emr_pdf, name="export_emr_pdf"),    
    path("emr/template/<str:key>/", views.load_note_template, name="load_note_template"),
    path("emr/<int:patient_id>/add-note/", views.add_emr_note, name="add_emr_note"),

    # Vital Signs
    path(
        "patients/<int:patient_id>/vitals/graphs/",
        views.patient_vitals_graphs,
        name="patient_vitals_graphs",
    ),
    path(
        "patients/<int:patient_id>/vitals/add/",
        views.add_vital_sign,     # FIXED
        name="add_vital_sign"
    ),
    # Vital alert actions
    path(
        "alerts/<int:alert_id>/acknowledge/",
        views.acknowledge_vital_alert,
        name="acknowledge_vital_alert",
    ),
    path(
        "alerts/<int:alert_id>/resolve/",
        views.resolve_vital_alert,
        name="resolve_vital_alert",
    ),

    path(
        "doctor/alerts/",
        views.doctor_alert_dashboard,
        name="doctor_alert_dashboard"
    ),

    path(
        "app/alerts/",
        views.admin_alert_dashboard,
        name="admin_alert_dashboard"
    ),

    path(
        "app/sla/edit/",
        views.hospital_sla_settings,
        name="hospital_sla_settings"
    ),

    path(
        "app/sla/settings/",
        views.sla_settings,
        name="sla_settings"
    ),

    path(
        "app/sla/doctors/",
        views.doctor_sla_dashboard,
        name="doctor_sla_dashboard"
    ),

    path(
        "app/doctors/<int:doctor_id>/sla/",
        views.doctor_scorecard,
        name="doctor_sla_scorecard"
    ),

    path(
        "app/sla/departments/",
        views.department_sla_dashboard,
        name="department_sla_dashboard"
    ),

    path(
        "doctor/sla/",
        views.doctor_sla_self_view,
        name="doctor_sla_self"
    ),

    path(
        "app/sla/leaderboard/",
        views.doctor_sla_leaderboard,
        name="doctor_sla_leaderboard"
    ),
    
    path("app/sla/trend/", views.doctor_sla_trend, name="doctor_sla_trend"),


    # NHIS Claims Dashboard
    path(
        "accountant/claims/",
        views.nhis_claims_dashboard,
        name="nhis_claims_dashboard",
    ),


    # Appointments
    path('appointments/', views.appointment_list, name='appointment_list'),
    path('appointments/create/', views.create_appointment, name='create_appointment'),

    # Billing
    path('bills/', views.bill_list, name='bill_list'),
    path('bills/create/', views.create_bill_index, name='create_bill'),
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

    # Autocomplete API Endpoint
    path("api/medicine-autocomplete/", views.medicine_autocomplete, name="medicine_autocomplete"),

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
    path("patients/register/", views.register_patient, name="register_patient"),


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

    # --- MEDICINE INVENTORY ROUTES ---
    path('medicines/', views.medicine_list, name='medicine_list'),
    path('medicines/add/', views.add_medicine, name='add_medicine'),
    path('medicines/<int:pk>/', views.medicine_detail, name='medicine_detail'),
    path('medicines/<int:pk>/edit/', views.edit_medicine, name='edit_medicine'),
    path('medicines/<int:pk>/delete/', views.delete_medicine, name='delete_medicine'),

    path('medicines/stock-logs/', views.stock_logs_view, name='stock_logs'),
    path('medicines/export/csv/', views.export_medicines_csv, name='export_medicines_csv'),
    path('pharmacy/', views.inventory_dashboard, name='inventory_dashboard'),

    # Print prescriptions per visit
    path('visits/<int:visit_id>/prescriptions/print/', views.print_visit_prescriptions, name='print_visit_prescriptions'),

    # --- CATEGORY MANAGEMENT ROUTES ---
    path("categories/", views.category_list, name="category_list"),
    path("categories/add/", views.add_category, name="add_category"),
    path("categories/<int:category_id>/edit/", views.edit_category, name="edit_category"),
    path("categories/<int:cat_id>/delete/", views.delete_category, name="delete_category"),

]
