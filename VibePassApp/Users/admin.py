from django.contrib import admin
from .models import User, OrganizerProfile, OrganizerWallet


# Register your models here.
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Admin interface for the custom User model."""

    list_display = ("username", "email", "is_active", "is_staff", "is_superuser")
    search_fields = ("username", "email")
    list_filter = ("is_active", "is_staff", "is_superuser")
    fieldsets = (
        (None, {"fields": ("username", "email", "password")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
        ("Important dates", {"fields": ("last_login",)}),
    )


@admin.register(OrganizerProfile)
class OrganizerProfileAdmin(admin.ModelAdmin):
    """Admin interface for OrganizerProfile model."""

    list_display = ("user", "is_verified", "updated_at")
    search_fields = ("user__username", "user__email")
    list_filter = ("is_verified",)


@admin.register(OrganizerWallet)
class OrganizerWalletAdmin(admin.ModelAdmin):
    """Admin interface for OrganizerWallet model."""

    list_display = (
        "organiser",
        "available_withdraw_balance",
        "pending_escrow_balance",
        "updated_at",
    )
    search_fields = ("organiser__username", "organiser__email")
    list_filter = ("updated_at",)
