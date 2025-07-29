# hospital_billing/fix_services.py

from collections import defaultdict
from billing.models import Service
from django.db import transaction

@transaction.atomic
def run():
    print("🔍 Finding duplicate services...")
    services = list(Service.objects.all())  # Fetch all at once
    duplicates = defaultdict(list)

    for s in services:
        if s.name and s.hospital_id:
            key = (s.hospital_id, s.name.strip().lower())
            duplicates[key].append(s)
        else:
            print(f"⚠️ Invalid service: ID={s.id}, Name={s.name}, Hospital={s.hospital_id}")

    total_fixed = 0
    for key, service_list in duplicates.items():
        if len(service_list) > 1:
            hospital_id, name = key
            print(f"🔁 Found {len(service_list)} copies of '{name}' in Hospital {hospital_id}")
            # Keep first, delete others
            for dup in service_list[1:]:
                print(f"  ❌ Deleting ID {dup.id}")
                dup.delete()
                total_fixed += 1

    print(f"✅ Fixed {total_fixed} duplicates.")

if __name__ == "__main__":
    run()