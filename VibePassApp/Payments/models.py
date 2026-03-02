from django.db import models
from Events.models import Event
from Users.models import User
import uuid
# Create your models here.
class Payment(models.Model):
    payment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # relationships
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='payments')
    # payment details
    checkout_request_id = models.CharField(max_length=255, unique=True)
    mpesa_receipt_number = models.CharField(max_length=255, unique=True)  # receipt number for each transaction by mpesa
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    mpesa_number = models.CharField(max_length=20)  # phone number used for payment
    payment_status = models.CharField(max_length=20)  # e.g., 'Pending', 'Completed', 'Failed'
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def __str__(self):
        return f"Payment {self.payment_id} - User: {self.user.username} - Event: {self.event.Event_title} - Amount: {self.amount}"