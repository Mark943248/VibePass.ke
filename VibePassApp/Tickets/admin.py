from django.contrib import admin
from .models import Ticket

# Register your models here.
@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    """Admin interface for the Ticket model."""
    list_display = (
        "ticket_id",
        "user",
        "event",
        "ticket_type",
        "created_at",
        "is_scanned",
    )
    search_fields = ("ticket_id", "user__username", "event__Event_title")
    list_filter = ("is_scanned", "created_at", "event")
    readonly_fields = ("ticket_id", "created_at")
