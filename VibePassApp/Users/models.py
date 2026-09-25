from django.db import models
from django.contrib.auth.models import AbstractUser


# Create your models here.
class User(AbstractUser):
    """Custom user model extending Django's AbstractUser to include additional fields for event organizers and account balance."""

    is_organiser = models.BooleanField(
        default=False
    )  # False for Event Finder, True for Event Organiser
    mpesa_number = models.CharField(max_length=15, blank=True, null=True)

    def is_Event_Organizer(self):
        return self.is_organiser

    def __str__(self):
        return self.username


class OrganizerProfile(models.Model):
    """Verification state and organizer metadata for an organizer account."""

    user = models.OneToOneField(
        User, on_delete=models.PROTECT, related_name="organizer_profile"
    )
    is_verified = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Organizer profile for {self.user.username}"

class OrganizerWallet(models.Model):
    """Model to represent amount the organiser can withdraw"""
    organiser = models.OneToOneField(User, on_delete=models.PROTECT, related_name="organiser")
    available_withdraw_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    pending_escrow_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    updated_at = models.DateTimeField(auto_now=True)