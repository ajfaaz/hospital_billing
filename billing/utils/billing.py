from decimal import Decimal
from billing.models import PatientCoverage
from billing.models import ThirdPartyPayer
from decimal import Decimal as D


def calculate_bill_split(patient, total_amount):
    """Return (patient_payable, third_party_payable, payer_instance) using coverage percentages."""
    total_amount = D(total_amount)

    coverage = (
        PatientCoverage.objects.filter(patient=patient, active=True)
        .select_related("payer")
        .first()
    )

    if not coverage:
        return total_amount, D("0.00"), None

    patient_payable = (total_amount * D(coverage.patient_percentage)) / D("100")
    third_party_payable = (total_amount * D(coverage.government_percentage)) / D("100")

    return patient_payable, third_party_payable, coverage.payer


def apply_coverage_to_bill(bill):
    """Apply PatientCoverage percentages to a Bill and map payer to ThirdPartyPayer.

    Sets `patient_payable`, `third_party_payable`, attempts to map the
    coverage.payer.code to a `ThirdPartyPayer` and assigns it to
    `bill.third_party`. Also sets `is_fully_paid` when patient_payable is zero.
    """
    coverage = (
        PatientCoverage.objects.filter(patient=bill.patient, active=True)
        .select_related("payer")
        .first()
    )

    if not coverage:
        bill.patient_payable = bill.total_amount
        bill.third_party_payable = D("0.00")
        bill.third_party = None
        bill.is_fully_paid = False
        bill.save()
        return

    bill.patient_payable = (D(bill.total_amount) * D(coverage.patient_percentage)) / D("100")
    bill.third_party_payable = (D(bill.total_amount) * D(coverage.government_percentage)) / D("100")

    # Map Payer -> ThirdPartyPayer by code if possible
    mapped = None
    payer_code = getattr(coverage.payer, "code", None)
    if payer_code:
        mapped = ThirdPartyPayer.objects.filter(code=payer_code).first()

    bill.third_party = mapped

    # mark fully paid for bills where patient owes nothing
    bill.is_fully_paid = (bill.patient_payable == D("0.00"))
    bill.save()
