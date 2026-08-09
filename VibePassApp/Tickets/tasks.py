import logging
import urllib.request
import cloudinary.utils
from celery import shared_task
from .models import Ticket
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)

@shared_task(max_retries=3, default_retry_delay=60)
def send_ticket_qr_code_to_user_task(ticket_id):
    """
    Fetches the QR code image from Cloudinary via URL, 
    attaches it to the email, and sends it asynchronously to the ticket buyer.
    """
    ticket = Ticket.objects.select_related('user', 'event').get(ticket_id=ticket_id)
    subject = f"Event Ticket For {ticket.event.Event_title}"
    recipient_list = [ticket.user.email]
    from_email = None
    logger.info(f"Email subject: {subject} - the recepients: {recipient_list}")

    text_content = (
        f"Hello {ticket.user.username}, \n\n"
        f"Thank you for your ticket purchase from VibePass, your details: \n"
        f"Event: {ticket.event.Event_title}"
        f"Ticket ID: {ticket.ticket_id}"
        f"Your QR code is attached down below"
    )

    msg = EmailMultiAlternatives(subject, text_content, from_email, recipient_list)

    image_url = ticket.ticket_qr_image.url
    
    if image_url:
        try:
            # Download the raw image bytes from Cloudinary in memory
            req = urllib.request.Request(
                image_url, 
                headers={'User-Agent': 'Mozilla/5.0'}  # Avoid potential CDN blocks
            )
            with urllib.request.urlopen(req) as response:
                image_bytes = response.read()

            # Attach as an image attachment (e.g., ticket_qr.png)
            filename = f"ticket_qr_{ticket.ticket_id}.png"
            msg.attach(filename, image_bytes, "image/png")

        except Exception as e:
            # Log issue or retry if Cloudinary fails to respond
            logger.error(f"Failed to download QR code from Cloudinary: {e}")


    try:
        msg.send(fail_silently=False)
        logger.info(f"Successfully sent ticket with QR code to {ticket.user.email}")
        return True
    except Exception as exc:
        logger.error(f"Failed to send email to user {exc}")
        return False

