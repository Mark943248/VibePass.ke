from django.contrib import admin
from .models import Payment, Withdrawal

# Register your models here.
admin.site.register(Payment)
admin.site.register(Withdrawal)