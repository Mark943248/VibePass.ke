import logging
from django.core.mail import EmailMultiAlternatives
from .models import User
from celery import shared_task

logger = logging.getLogger(__name__)    


@shared_task()
def send_otp_email_task(user_id):
    """
    Sends an OTP email to the user for email verification.
    This function is executed asynchronously as a Celery task.
    """
    user = User.objects.get(id=user_id)
    subject = "Your OTP Code for Email Verification"
    recipient_list = [user.email]
    from_email = None

    text_content = (
        f"Hello {user.username}, \n\n"
        f"Thank you for signing up with VibePass! "
        f"Please use the following OTP code to verify your email address: {user.otp_code}\n\n"
        f"This code will expire in 5 minutes."
    )

    msg = EmailMultiAlternatives(subject, text_content, from_email, recipient_list)

    try:
        msg.send(fail_silently=False)
        return True
    except Exception as exc:
       logger.error(f"Error sending OTP email to {user.email}: {exc}")
       return False