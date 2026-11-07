from allauth.account.signals import user_signed_up
from django.dispatch import receiver

@receiver(user_signed_up)
def verify_email_on_signup(request, user, **kwargs):
    """
    Signal receiver to handle email verification upon user signup.
    This function is triggered when a new user signs up using django-allauth.
    It sets the user's email as verified and saves the user instance.
    """
    user.is_email_verified = True
    user.save()