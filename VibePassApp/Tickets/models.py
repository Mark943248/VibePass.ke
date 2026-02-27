from django.db import models
from Events.models import Event
from Payments.models import Payment
from django.utils import timezone
import uuid
# Create your models here.
class Ticket(models.Model):
    ticket_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='tickets')
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='tickets')
    is_scanned = models.BooleanField(default=False)
    scanned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def mark_as_scanned(self):
        if self.is_scanned:
            return False, "Ticket has already been scanned."
        self.is_scanned = True
        self.scanned_at = timezone.now()
        self.save()
        return True, "Ticket marked as scanned successfully."
           

    def __str__(self):
        return f"Ticket {self.id} for {self.event.Event_title} by {self.user.username}"
