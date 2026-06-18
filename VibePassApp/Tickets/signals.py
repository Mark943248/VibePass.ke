from django.dispatch import receiver
from Payments.signals import payment_successful
from .views import create_ticket
import logging

logger = logging.getLogger(__name__)


@receiver(payment_successful)
def create_ticket_on_payment_success(sender, payment, **kwargs):
    """Create ticket with QR code when payment is successful and update inventory"""
    try:
        # Ticket generation step
        ticket = create_ticket(None, payment.payment_id)
        if ticket:
            logger.info(f"Ticket created successfully for payment {payment.payment_id}")
        else:
            logger.error(f"Failed to create ticket for payment {payment.payment_id}")
        
    except Exception as e:
        logger.error(f"Error in create_ticket_on_payment_success signal: {str(e)}", exc_info=True)