import logging

from django.apps import apps
from django.db import transaction
from django.db.models import Avg, Q
from django.utils import timezone

from .models import Event, ReportEvent, ReviewEvent

logger = logging.getLogger(__name__)

COMPLETED_EVENT_COUNT = 3
MINIMUM_AVERAGE_RATING = 3.5
MINIMUM_REVIEW_COUNT = 5
ACTIVE_REPORT_STATUSES = ("pending", "under_review", "action_taken")


def evaluate_organizer_verification(organizer_id):
    """Recalculate and persist verification for one organizer safely."""
    profile_model = apps.get_model("Users", "OrganizerProfile")

    with transaction.atomic():
        profile, _ = profile_model.objects.get_or_create(user_id=organizer_id)
        profile = (
            profile_model.objects.select_for_update()
            .select_related("user")
            .get(pk=profile.pk)
        )
        today = timezone.localdate()

        # 1. Base queryset for completed events
        completed_events = Event.objects.filter(
            Event_organiser_id=organizer_id
        ).filter(Q(Event_date__lt=today) | Q(Event_is_active=False) | Q(Event_is_flagged=False))
        
        completed_event_count = completed_events.count()

        # 2. Reviews ONLY from completed events
        reviews = ReviewEvent.objects.filter(event__in=completed_events)
        review_count = reviews.count()
        average_rating = reviews.aggregate(average=Avg("rating"))["average"] or 0

        # 3. Reports: Keep across ALL events to catch active pre-event scams/issues
        active_report_count = ReportEvent.objects.filter(
            event__Event_organiser_id=organizer_id,
            report_status__in=ACTIVE_REPORT_STATUSES,
        ).count()

        qualifies = (
            completed_event_count >= COMPLETED_EVENT_COUNT
            and active_report_count == 0
            and average_rating >= MINIMUM_AVERAGE_RATING
            and review_count >= MINIMUM_REVIEW_COUNT
        )

        if profile.is_verified != qualifies:
            profile.is_verified = qualifies
            profile.save(update_fields=["is_verified", "updated_at"])

        return qualifies


def schedule_organizer_verification(organizer_id):
    """Run verification after the creating transaction commits.

    Signal handlers must not make a failed verification query roll back a
    successfully-created rating or report.
    """
    transaction.on_commit(
        lambda: _run_scheduled_verification(organizer_id)
    )


def _run_scheduled_verification(organizer_id):
    try:
        evaluate_organizer_verification(organizer_id)
    except Exception:
        logger.exception(
            "Organizer verification failed for organizer %s", organizer_id
        )