from django import template

register = template.Library()

@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except:
        return 0


from django.template.loader import render_to_string
from xhtml2pdf import pisa
from django.http import HttpResponse
from .models import Bill

def generate_invoice_pdf(request, bill_id):
    bill = Bill.objects.get(pk=bill_id)
    html = render_to_string('bill_invoice.html', {'bill': bill})
    response = HttpResponse(content_type='application/pdf')
    pisa.CreatePDF(html, dest=response)
    return response

