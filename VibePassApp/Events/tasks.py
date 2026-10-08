import logging
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from Tickets.models import Ticket

logger = logging.getLogger(__name__)


@shared_task
def deactivate_past_events_and_expire_tickets():
    """Deactivate active events whose calendar date has passed."""
    from .models import Event

    past_active_events = Event.objects.filter(
        Event_is_active=True,
        Event_date__lt=timezone.localdate(),
    )

    past_events_tickets = Ticket.objects.filter(event__in=past_active_events, status="active").update(
        status="expired"
    )

    updated_events = past_active_events.update(Event_is_active=False)
    updated_count = updated_events + past_events_tickets
    logger.info("Deactivated %s past event(s) & expired %s ticket(s).", updated_events, past_events_tickets)

    return updated_count


@shared_task
def send_report_notification_email_to_admins_task(event_id, reporter_username):
    """Sends an email notification to the admins when an event receives 3 or more unique reports."""
    from .models import Event

    try:
        event = Event.objects.get(id=event_id)

        # Use standard model field attribute (adjust if your field is named differently)
        event_title = getattr(event, "Event_title")

        subject = f"[ALERT] Event Flagged: {event_title}"
        message = (
            f"The event '{event_title}' (ID: {event.id}) has received 3 unique"
            " reports and its payout status has been automatically frozen.\n\n"
            f"3rd Reporter: {reporter_username}\n\n"
            "Please log into the admin dashboard to review organizer defense proof"
            " and resolve this dispute."
        )

        # Get admin emails safely from django.conf.settings
        admin_emails = [admin[1] for admin in getattr(settings, "ADMINS", [])]

        if not admin_emails:
            logger.warning(
                "No ADMINS configured in settings.ADMINS. Email notification was not"
                " sent."
            )
            return

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=admin_emails,
            fail_silently=False,
        )
        logger.info(
            f"Report notification email successfully sent for Event ID {event_id}."
        )

    except Event.DoesNotExist:
        logger.error(
            f"Event with ID {event_id} does not exist. Cannot send report"
            " notification email."
        )
    except Exception as e:
        logger.exception(
            f"Failed to send report notification email for Event ID {event_id}:" f" {e}"
        )


@shared_task
def send_event_cancellation_email_to_buyers(ticket_ids):
    """Notify each buyer whose ticket was cancelled for an event."""
    from Tickets.models import Ticket

    tickets = Ticket.objects.filter(
        ticket_id__in=ticket_ids,
        status="cancelled",
    ).select_related("event", "user")

    buyers = {}
    for ticket in tickets:
        if ticket.user and ticket.user.email:
            buyer = buyers.setdefault(
                ticket.user_id,
                {"user": ticket.user, "event": ticket.event, "ticket_ids": []},
            )
            buyer["ticket_ids"].append(str(ticket.ticket_id))

    sent_count = 0
    for buyer in buyers.values():
        user = buyer["user"]
        event = buyer["event"]
        ticket_list = "\n".join(buyer["ticket_ids"])
        message = (
            f"Hello {user.username},\n\n"
            f"The event '{event.Event_title}' has been cancelled. "
            "Your ticket(s) are now cancelled:\n"
            f"{ticket_list}\n\n"
            "Please contact the event organizer if you have questions about a refund."
        )

        send_mail(
            subject=f"Event cancelled: {event.Event_title}",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        sent_count += 1

    logger.info("Sent %s event cancellation email(s).", sent_count)
    return sent_count
