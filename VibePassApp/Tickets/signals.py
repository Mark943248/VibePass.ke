from django.dispatch import receiver
from Payments.signals import payment_successful
from .views import create_ticket


@receiver(payment_successful)
def create_ticket_on_payment_success(sender, payment, **kwargs):
    create_ticket(None, payment.id, redirect_to_qr=False)
