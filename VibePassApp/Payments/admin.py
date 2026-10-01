from django.contrib import admin
from .models import Payment, Withdrawal, EscrowModel, PlatformRevenue


# Register your models here.
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Admin interface for the Payment model."""

    list_display = (
        "payment_id",
        "user",
        "event",
        "amount",
        "payment_status",
        "created_at",
    )
    search_fields = ("payment_id", "user__username", "event__Event_title")
    list_filter = ("payment_status", "created_at")
    readonly_fields = ("payment_id", "amount", "created_at", "updated_at")


@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    """Admin interface for the Withdrawal model."""

    list_display = (
        "withdrawal_id",
        "organiser",
        "amount",
        "status",
        "created_at",
    )
    search_fields = ("withdrawal_id", "organiser__username")
    list_filter = ("status", "created_at")
    readonly_fields = ("withdrawal_id", "amount", "created_at", "updated_at")


@admin.register(EscrowModel)
class EscrowModelAdmin(admin.ModelAdmin):
    """Admin interface for the EscrowModel."""

    list_display = (
        "payment",
        "event",
        "organiser",
        "amount",
        "payout_status",
        "release_date",
        "released_at",
        "created_at",
    )
    search_fields = ("payment__payment_id", "event__Event_title", "organiser__username")
    list_filter = ("payout_status", "release_date", "released_at", "created_at")
    readonly_fields = ("payment", "event", "organiser", "amount", "created_at")


@admin.register(PlatformRevenue)
class PlatformRevenueAdmin(admin.ModelAdmin):
    """Admin interface for the PlatformRevenue model."""

    list_display = (
        "organiser",
        "fee_amount",
        "source",
        "created_at",
    )
    search_fields = ("organiser__username", "source")
    list_filter = ("created_at",)
    readonly_fields = ("fee_amount", "source", "created_at")
