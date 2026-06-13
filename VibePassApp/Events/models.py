from django.db import models
from django.db.models import Sum, Min
from cloudinary.models import CloudinaryField
from django.core.exceptions import ValidationError
from django.utils.text import slugify

# limits image size to 2MB
def validate_image_size(file):
    # Limit to 2MB (2 * 1024 * 1024 bytes)
    limit_mb = 2
    # Skip validation for CloudinaryResource objects (already hosted on Cloudinary)
    if hasattr(file, 'size'):
        if file.size > limit_mb * 1024 * 1024:
            raise ValidationError(f"Maximum file size is {limit_mb}MB")

# Event model
class Event(models.Model):

    EVENT_CATEGORIES = [
        ('live music', 'Live Music'),
        ('sports', 'Sports'),
        ('workshop', 'Workshop'),
        ('campus parties', 'Campus Parties'),
        ('tech events', 'Tech Events'),
        ('networking', 'Networking'),
        ('festivals', 'Festivals'),
        ('other', 'Other'),
    ]
    
    # Event basic info
    Event_organiser = models.ForeignKey(
        'Users.User', 
        on_delete=models.CASCADE, 
        related_name='organized_events'
        )
    Event_title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    Event_flyer = CloudinaryField('image', allowed_formats=['jpg', 'jpeg', 'png'], validators=[validate_image_size])
    Event_category = models.CharField(max_length=50, choices=EVENT_CATEGORIES, default='other')
    Event_details = models.TextField()
    Event_location = models.CharField(max_length=200)
    Event_date = models.DateField()
    Event_time = models.TimeField()
    Event_mpesa_number = models.CharField(max_length=15, blank=True, null=True)  # Optional field for event-specific payment number 
    # Event ticketing info
    Event_is_free = models.BooleanField(default=False)
    # Event status
    Event_is_active = models.BooleanField(default=True)
    Event_created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_ticket_capacity(self):
        return self.ticket_types.aggregate(total=Sum('capacity'))['total'] or 0

    @property
    def min_ticket_price(self):
        price = self.ticket_types.filter(is_active=True).aggregate(min_price=Min('price'))['min_price']
        if price is None:
            price = self.ticket_types.aggregate(min_price=Min('price'))['min_price']
        return price or 0

    @property
    def price_summary(self):
        if self.Event_is_free:
            return 'FREE'
        price = self.min_ticket_price
        return f"KES {price:.2f}" if price else 'FREE'

    def get_sold_tickets(self):
        """Returns the number of sold tickets for this event"""
        sold_tickets = self.tickets.filter(status__in=['active', 'scanned']).count()
        return sold_tickets

    def percentage_of_sold_tickets(self):
        sold_tickets = self.get_sold_tickets()
        total_tickets = self.total_ticket_capacity
        return round(sold_tickets * 100 / total_tickets, 2) if total_tickets else 0
    
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


class TicketType(models.Model):
    """
    Model to represent different ticket types for an event.
    Examples: Early Bird, VIP, Regular, Standard, etc.
    """
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='ticket_types')
    name = models.CharField(max_length=100)  # e.g., "Early Bird", "VIP", "Regular"
    description = models.TextField(blank=True, null=True)  # Additional description for the ticket type
    price = models.DecimalField(max_digits=10, decimal_places=2)
    capacity = models.PositiveIntegerField()  # Maximum number of tickets available for this type
    sold_count = models.PositiveIntegerField(default=0)  # Number of tickets sold
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        unique_together = ('event', 'name')  # Prevent duplicate ticket types for the same event

    def get_available_count(self):
        """Get the number of available tickets for this ticket type"""
        return self.capacity - self.sold_count
    
    def get_total_tickets(self):
        return self.event.ticket_types.aggregate(total=Sum('capacity'))['total'] or 0

    def has_available(self):
        """Check if this ticket type has available tickets"""
        return self.get_available_count() > 0

    
    def deactivate_ticket_type(self):
        if not self.has_available:
            self.is_active = False

    def __str__(self):
        return f"{self.event.Event_title} - {self.name}"
  
