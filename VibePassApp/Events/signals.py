import logging
from django.dispatch import Signal, receiver
from django.db.models.signals import post_save
from Payments.models import EscrowModel
from django.db import transaction
from .models import Event, ReportEvent, ReviewEvent
from .services import schedule_organizer_verification
from .tasks import send_report_notification_email_to_admins_task

logger = logging.getLogger(__name__)
report_3_submitted = Signal()


def _schedule_for_event(sender, instance, created, **kwargs):
    if created:
        schedule_organizer_verification(instance.event.Event_organiser_id)


post_save.connect(_schedule_for_event, sender=ReviewEvent)
post_save.connect(_schedule_for_event, sender=ReportEvent)

@receiver(report_3_submitted)
def handle_report_3_submission(sender, **kwargs):
    event = kwargs.get("event")
    reporter_username = kwargs.get("reporter_username")

    if not event:
        logger.error("Event not provided in signal kwargs.")
        return

    with transaction.atomic():
        # 1. Update event flagged state
        event.Event_is_flagged = True
        event.save(update_fields=["Event_is_flagged"])

        # 2. Freeze all active escrow holds for this event in a single atomic SQL query
        updated_holds_count = EscrowModel.objects.filter(
            event=event,
            payout_status="Held"  # Only freeze holds that are currently Held (don't overwrite already Released/Refunded)
        ).update(payout_status="Frozen")

        logger.info(f"Event #{event.id} flagged. Frozen {updated_holds_count} escrow holds.")

    # 3. Trigger admin email task asynchronously after transaction commits
    send_report_notification_email_to_admins_task.delay(event.id, reporter_username)

