from django.contrib import admin
from .models import CustomUser, Patient
from django.contrib.auth.admin import UserAdmin
from .models import Service, Bill, BillItem, Payment
from .models import Medicine


class BillItemInline(admin.TabularInline):
    model = BillItem
    extra = 1

class BillAdmin(admin.ModelAdmin):
    inlines = [BillItemInline]
    list_display = ['invoice_no', 'patient', 'total_amount', 'created_by', 'created_at']

admin.site.register(Service)
admin.site.register(Bill, BillAdmin)
admin.site.register(Payment)


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['username', 'email', 'role']

admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Patient)


