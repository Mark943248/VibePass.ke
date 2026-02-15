from django.db import models
from cloudinary.models import CloudinaryField
from django.core.exceptions import ValidationError
from django.utils.text import slugify

# limits image size to 2MB
def validate_image_size(file):
    # Limit to 2MB (2 * 1024 * 1024 bytes)
    limit_mb = 2
    if file.size > limit_mb * 1024 * 1024:
        raise ValidationError(f"Maximum file size is {limit_mb}MB")

# Event model
class Event(models.Model):

    # Event basic info
    Event_organiser = models.ForeignKey(
        'Users.User', 
        on_delete=models.CASCADE, 
        related_name='organized_events'
        )
    Event_title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    Event_flyer = CloudinaryField('image', allowed_formats=['jpg', 'jpeg', 'png'], validators=[validate_image_size])
    Event_category = models.CharField(max_length=50, default='other')
    Event_details = models.TextField()
    Event_location = models.CharField(max_length=200)
    Event_date = models.DateField()
    Event_time = models.TimeField()
    Event_mpesa_number = models.CharField(max_length=15)
    # Event ticketing info
    Event_ticket_price = models.DecimalField(max_digits=10, decimal_places=2)
    Event_is_free = models.BooleanField(default=False)
    Event_total_tickets = models.PositiveIntegerField()
    # Event status
    Event_is_active = models.BooleanField(default=True)
    Event_created_at = models.DateTimeField(auto_now_add=True)
    
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.Event_title)
        super(Event, self).save(*args, **kwargs)


    def __str__(self):
        return self.Event_title
  
