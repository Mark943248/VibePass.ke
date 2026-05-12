from django.db import models
from django.contrib.auth.models import AbstractUser
# Create your models here.
class User(AbstractUser):
    is_organiser = models.BooleanField(default=False)  # False for Event Finder, True for Event Organiser
    account_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # New field for account balance
    def is_Event_Organizer(self):
        return self.is_organiser
    
    def __str__(self):
        return self.username