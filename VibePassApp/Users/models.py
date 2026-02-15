from django.db import models
from django.contrib.auth.models import AbstractUser
# Create your models here.
class User(AbstractUser):
    is_organiser = models.BooleanField(default=False)  # False for Event Finder, True for Event Organiser

    def is_Event_Organizer(self):
        return self.is_organiser
    
    def __str__(self):
        return self.username