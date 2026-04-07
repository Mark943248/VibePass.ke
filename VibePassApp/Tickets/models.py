from django.db import models
from Events.models import Event
from Payments.models import Payment
from Users.models import User
from django.utils import timezone
import uuid

TICKET_STATUS = [
    ('active', 'Active'),
    ('scanned', 'Scanned'),
    ('cancelled', 'Cancelled'),
]

class Ticket(models.Model):
    ticket_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='tickets')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='booked_tickets')
    payment = models.OneToOneField(
        Payment, 
        on_delete=models.CASCADE, 
        related_name='ticket',
        null=True,
        blank=True
    )
    status = models.CharField(max_length=20, choices=TICKET_STATUS, default='active')
    is_scanned = models.BooleanField(default=False)
    scanned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def mark_as_scanned(self):
        if self.is_scanned:
            return False, "Ticket has already been scanned."
        self.is_scanned = True
        self.status = 'scanned'
        self.scanned_at = timezone.now()
        self.save()
        return True, "Ticket marked as scanned successfully."

    def __str__(self):
        return f"Ticket {self.ticket_id} for {self.event.Event_title} by {self.user.username}"
