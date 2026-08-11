from django.contrib import admin
from .models import Event, TicketType, EventScanner


# Create an inline admin for TicketType
class TicketTypeInline(admin.TabularInline):
    model = TicketType
    extra = 1  # Show one extra empty form for adding new ticket types
    fields = ("name", "description", "price", "capacity", "is_active")


# Register Event with TicketType inline
@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "Event_title",
        "Event_organiser",
        "Event_date",
        "Event_location",
        "Event_is_active",
    )
    search_fields = ("Event_title", "Event_location")
    list_filter = ("Event_category", "Event_is_active", "Event_date")
    inlines = [TicketTypeInline]


# Register TicketType separately for direct management
@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "event", "price", "capacity", "sold_count", "is_active")
    search_fields = ("name", "event__Event_title")
    list_filter = ("is_active", "event")
    readonly_fields = ("sold_count", "created_at", "updated_at")
    fieldsets = (
        ("Ticket Type Info", {"fields": ("event", "name", "description")}),
        ("Pricing & Capacity", {"fields": ("price", "capacity", "sold_count")}),
        ("Status", {"fields": ("is_active",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(EventScanner)
class EventScannerAdmin(admin.ModelAdmin):
    list_display = ("scanner_id", "event", "user", "added_by")
    search_fields = ("event__Event_title", "user__username", "added_by__username")
    list_filter = ("event",)
    readonly_fields = ("scanner_id",)
