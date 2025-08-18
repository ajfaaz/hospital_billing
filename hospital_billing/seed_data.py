from billing.models import Patient, CustomUser, Hospital
from datetime import date

# Get or create the hospital
hospital, _ = Hospital.objects.get_or_create(name="Main Hospital")

# --- Create some patients ---
patients_data = [
    ("John Doe", date(1990, 1, 1), "08012345678"),
    ("Jane Smith", date(1985, 5, 12), "08098765432"),
    ("Michael Johnson", date(2000, 7, 20), "08123456789"),
]

for full_name, dob, phone in patients_data:
    patient, created = Patient.objects.get_or_create(
        full_name=full_name,
        date_of_birth=dob,
        phone_number=phone,
        hospital=hospital,
    )
    if created:
        print(f"✅ Patient created: {full_name}")
    else:
        print(f"ℹ Patient already exists: {full_name}")

# --- Create some doctors ---
doctors_data = [
    ("drbrown", "Dr. Brown"),
    ("drlee", "Dr. Lee"),
]

for username, fullname in doctors_data:
    doctor, created = CustomUser.objects.get_or_create(
        username=username,
        role="doctor",
        hospital=hospital,
    )
    doctor.full_name = fullname
    if created:
        doctor.set_password("testpass123")
        print(f"✅ Doctor created: {fullname} (username: {username}, password: testpass123)")
    else:
        print(f"ℹ Doctor already exists: {fullname}")
    doctor.save()

print("🎉 Seeding complete!")
