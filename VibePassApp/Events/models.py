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
    Event_mpesa_number = models.CharField(max_length=15, blank=True, null=True)  # Optional field for event-specific payment number 
    # Event ticketing info
    Event_ticket_price = models.DecimalField(max_digits=10, decimal_places=2)
    Event_is_free = models.BooleanField(default=False)
    Event_total_tickets = models.PositiveIntegerField()
    # Event status
    Event_is_active = models.BooleanField(default=True)
    Event_created_at = models.DateTimeField(auto_now_add=True)

    # return available tickets
    def get_available_tickets(self):
        """Returns the number of available tickets for this event"""
        claimed = self.tickets.filter(status__in=['active', 'scanned']).count()
        return self.Event_total_tickets - claimed
    
    # get sold tickets
    def get_sold_tickets(self):
        """Returns the number of sold tickets for this event"""
        sold_tickets = self.tickets.filter(status__in=['active', 'scanned']).count()
        return sold_tickets
    
    # get total revenue from completed payments
    def get_total_revenue(self):
        """Calculate total revenue from completed payments for this event"""
        from django.db.models import Sum
        revenue = self.payments.filter(payment_status='Completed').aggregate(total=Sum('amount'))['total'] or 0
        return revenue
    
    # checks if there are any available tickets
    def has_available_tickets(self):
        """Check if tickets are still available"""
        return self.get_available_tickets() > 0
    
    def percentage_of_sold_tickets(self):
        sold_tickets = self.get_sold_tickets()
        total_tickets = self.Event_total_tickets
        percentage = sold_tickets * 100 / total_tickets
        return percentage
    
    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.Event_title)
            slug = base_slug
            counter = 1
            while Event.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super(Event, self).save(*args, **kwargs)

    def __str__(self):
        return self.Event_title
  
