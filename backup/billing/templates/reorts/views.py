from django.db.models import Sum
from billing.models import Bill
from django.utils import timezone

def daily_income_report(request):
    today = timezone.now().date()
    bills_today = Bill.objects.filter(date__date=today)
    total_income = bills_today.aggregate(Sum('total'))['total__sum'] or 0
    return render(request, 'reports/daily_report.html', {'bills': bills_today, 'total': total_income})
