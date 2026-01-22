from django.core.management.base import BaseCommand
from billing.services.sla_monitor import run_sla_monitor

class Command(BaseCommand):
    help = "Run SLA enforcement engine"

    def handle(self, *args, **kwargs):
        run_sla_monitor()
        self.stdout.write("SLA monitor executed")
