from datetime import date, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from .models import Event, ReportEvent, ReviewEvent, TicketType
from Tickets.models import Ticket
from .services import evaluate_organizer_verification
from .tasks import deactivate_past_events, send_event_cancellation_email_to_buyers
from Users.models import OrganizerProfile
from Payments.models import EscrowModel, Payment

User = get_user_model()


class EventModelTest(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(
            username="organizer",
            email="org@example.com",
            password="testpass123",
            is_organiser=True,
        )
        self.event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title="Test Event",
            Event_flyer="https://example.com/flyer.jpg",
            Event_category="music",
            Event_details="Test event details",
            Event_location="Test Location",
            Event_date=date.today(),
            Event_time=time(18, 0),
            Event_is_free=False,
        )
        self.ticket_type = TicketType.objects.create(
            event=self.event,
            name="Regular",
            description="Standard access",
            price=1000.00,
            capacity=50,
        )

        self.payment = Payment.objects.create(
            user=self.organizer,
            event=self.event,
            amount=100.00,
            mpesa_number="254712345678",
            payment_status="Pending",
        )

    def test_event_creation(self):
        self.assertEqual(self.event.Event_title, "Test Event")
        self.assertEqual(self.event.Event_organiser, self.organizer)
        self.assertEqual(self.event.Event_category, "music")
        self.assertFalse(self.event.Event_is_free)
        self.assertTrue(self.event.slug)

    def test_deactivate_past_events_updates_only_past_active_events(self):
        past_event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title="Past Event",
            Event_flyer="https://example.com/past.jpg",
            Event_category="music",
            Event_details="Details",
            Event_location="Location",
            Event_date=date.today() - timedelta(days=1),
            Event_time=time(18, 0),
            Event_is_free=True,
        )
        today_event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title="Today Event",
            Event_flyer="https://example.com/today.jpg",
            Event_category="music",
            Event_details="Details",
            Event_location="Location",
            Event_date=date.today(),
            Event_time=time(18, 0),
            Event_is_free=True,
        )
        future_event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title="Future Event",
            Event_flyer="https://example.com/future.jpg",
            Event_category="music",
            Event_details="Details",
            Event_location="Location",
            Event_date=date.today() + timedelta(days=1),
            Event_time=time(18, 0),
            Event_is_free=True,
        )

        self.assertEqual(deactivate_past_events(), 1)

        past_event.refresh_from_db()
        today_event.refresh_from_db()
        future_event.refresh_from_db()
        self.assertFalse(past_event.Event_is_active)
        self.assertTrue(today_event.Event_is_active)
        self.assertTrue(future_event.Event_is_active)

    def test_ticket_capacity_and_price_summary(self):
        TicketType.objects.create(
            event=self.event,
            name="VIP",
            description="Premium access",
            price=2500.00,
            capacity=20,
        )

        self.assertEqual(self.event.total_ticket_capacity, 70)
        self.assertEqual(self.event.min_ticket_price, 1000.00)
        self.assertEqual(self.event.price_summary, "KES 1000.00")

    def test_get_sold_tickets_and_percentage(self):
        self.assertEqual(self.event.get_sold_tickets(), 0)
        self.assertEqual(self.event.percentage_of_sold_tickets(), 0)

    def test_event_str(self):
        self.assertEqual(str(self.event), self.event.Event_title)

    def test_delete_event_soft_deletes_unsold_event(self):
        self.client.force_login(self.organizer)

        response = self.client.post(reverse("delete_event", args=[self.event.slug]))

        self.assertEqual(response.status_code, 200)
        self.event.refresh_from_db()
        self.assertTrue(self.event.is_deleted)
        self.assertEqual(self.event.Event_status, "deleted")
        self.assertFalse(self.event.Event_is_active)

    def test_delete_event_rejects_sold_event(self):
        self.client.force_login(self.organizer)
        Ticket.objects.create(
            event=self.event,
            user=self.organizer,
            ticket_type=self.ticket_type,
            status="active",
        )

        response = self.client.post(reverse("delete_event", args=[self.event.slug]))

        self.assertRedirects(response, reverse("organizers_dashboard"))
        self.event.refresh_from_db()
        self.assertFalse(self.event.is_deleted)

    def test_cancel_event_freezes_escrow_for_sold_event(self):
        self.client.force_login(self.organizer)
        Ticket.objects.create(
            event=self.event,
            user=self.organizer,
            ticket_type=self.ticket_type,
            status="active",
        )

        escrow = EscrowModel.objects.create(
            payment=self.payment,
            organiser=self.organizer,
            event=self.event,
            amount=5000.00,
            release_date=date.today(),
        )

        response = self.client.post(
            reverse("cancel_event", args=[self.event.slug])
        )

        self.assertRedirects(response, reverse("organizers_dashboard"))
        self.event.refresh_from_db()
        self.assertEqual(self.event.Event_status, "cancelled")
        self.assertTrue(self.event.is_deleted)
        escrow.refresh_from_db()
        self.assertEqual(escrow.payout_status, "frozen")

    @patch("Events.tasks.send_mail")
    def test_event_cancellation_email_sends_once_per_buyer(self, mock_send_mail):
        second_buyer = User.objects.create_user(
            username="buyer",
            email="buyer@example.com",
            password="testpass123",
        )
        first_ticket = Ticket.objects.create(
            event=self.event,
            user=self.organizer,
            ticket_type=self.ticket_type,
            status="cancelled",
        )
        second_ticket = Ticket.objects.create(
            event=self.event,
            user=self.organizer,
            ticket_type=self.ticket_type,
            status="cancelled",
        )
        third_ticket = Ticket.objects.create(
            event=self.event,
            user=second_buyer,
            ticket_type=self.ticket_type,
            status="cancelled",
        )

        sent_count = send_event_cancellation_email_to_buyers(
            [str(first_ticket.ticket_id), str(second_ticket.ticket_id), str(third_ticket.ticket_id)]
        )

        self.assertEqual(sent_count, 2)
        self.assertEqual(mock_send_mail.call_count, 2)
        recipients = {call.kwargs["recipient_list"][0] for call in mock_send_mail.call_args_list}
        self.assertEqual(recipients, {self.organizer.email, second_buyer.email})
        organizer_email = next(
            call for call in mock_send_mail.call_args_list
            if call.kwargs["recipient_list"] == [self.organizer.email]
        )
        self.assertIn(str(first_ticket.ticket_id), organizer_email.kwargs["message"])
        self.assertIn(str(second_ticket.ticket_id), organizer_email.kwargs["message"])


class EventViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.organizer = User.objects.create_user(
            username="organizer",
            email="org@example.com",
            password="testpass123",
            is_organiser=True,
        )
        self.regular_user = User.objects.create_user(
            username="user",
            email="user@example.com",
            password="testpass123",
        )

    def test_create_event_view_unauthenticated(self):
        response = self.client.get(reverse("create_event"))
        self.assertRedirects(
            response, f"/users/login/?next={reverse('create_event')}"
        )

    def test_create_event_view_non_organizer(self):
        self.client.login(username="user", password="testpass123")
        response = self.client.get(reverse("create_event"))
        self.assertRedirects(response, reverse("login"))

    def test_create_event_view_get(self):
        self.client.login(username="organizer", password="testpass123")
        response = self.client.get(reverse("create_event"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/create_event.html")

    def test_create_event_view_post_success(self):
        self.client.login(username="organizer", password="testpass123")
        data = {
            "Event_title": "New Test Event",
            "Event_category": "sports",
            "Event_details": "New event details",
            "Event_location": "New Location",
            "Event_date": date.today().isoformat(),
            "Event_time": "20:00",
            "Event_is_free": "on",
            "ticket_name[]": ["VIP"],
            "ticket_price[]": ["150.00"],
            "ticket_capacity[]": ["50"],
            "ticket_description[]": ["VIP access"],
        }
        files = {
            "Event_flyer": SimpleUploadedFile(
                "flyer.jpg",
                b"fake-image-content",
                content_type="image/jpeg",
            )
        }
        response = self.client.post(reverse("create_event"), data=data, files=files)
        self.assertRedirects(response, reverse("list_event"))
        self.assertTrue(Event.objects.filter(Event_title="New Test Event").exists())
        self.assertTrue(
            TicketType.objects.filter(
                event__Event_title="New Test Event", name="VIP"
            ).exists()
        )

    def test_list_event_view(self):
        response = self.client.get(reverse("list_event"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/list_event.html")

    def test_search_event_view(self):
        response = self.client.get(reverse("search_event"), {"q": "test"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/list_event.html")

    def test_filter_by_category_view(self):
        response = self.client.get(reverse("filter_by_category", args=["music"]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/list_event.html")

    def test_event_details_view(self):
        event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title="Details Test Event",
            Event_flyer="https://example.com/details.jpg",
            Event_category="tech events",
            Event_details="Details",
            Event_location="Location",
            Event_date=date.today(),
            Event_time=time(18, 0),
            Event_is_free=True,
        )
        TicketType.objects.create(
            event=event,
            name="Regular",
            description="General access",
            price=0.00,
            capacity=10,
        )
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse("event_details", args=[event.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/event_details.html")

    def test_event_details_displays_organizer_average_rating(self):
        event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title="Rated Details Event",
            Event_flyer="https://example.com/details.jpg",
            Event_category="tech events",
            Event_details="Details",
            Event_location="Location",
            Event_date=date.today(),
            Event_time=time(18, 0),
            Event_is_free=True,
        )
        reviewer = User.objects.create_user(username="reviewer", password="pass1234")
        ReviewEvent.objects.create(
            reviewed_by=reviewer, event=event, rating=4, review="Good"
        )
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse("event_details", args=(event.slug,)))

        self.assertEqual(response.context["organizer_average_rating"], 4)
        self.assertEqual(response.context["organizer_review_count"], 1)
        self.assertContains(response, "4.0/5 average rating")

    def test_rate_event_view_uses_slug_from_url(self):
        event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title="Past Rated Event",
            Event_flyer="https://example.com/rated.jpg",
            Event_category="music",
            Event_details="Details",
            Event_location="Location",
            Event_date=date.today() - timedelta(days=1),
            Event_time=time(18, 0),
            Event_is_free=True,
        )
        self.client.force_login(self.regular_user)

        response = self.client.post(
            reverse("review_event", args=[event.slug]),
            {"rating": "5", "review": "Excellent event"},
        )

        self.assertRedirects(response, reverse("finders_dashboard"))
        self.assertTrue(
            ReviewEvent.objects.filter(
                event=event, reviewed_by=self.regular_user, rating=5
            ).exists()
        )

@patch("Events.signals.send_report_notification_email_to_admins_task.delay")
def test_three_unique_reports_flag_event_and_freeze_payout(self, notify_admins):
    event = Event.objects.create(
        Event_organiser=self.organizer,
        Event_title="Reported Event",
        Event_flyer="reported.jpg",
        Event_category="music",
        Event_details="Details",
        Event_location="Location",
        Event_date=date.today(),
        Event_time=time(18, 0),
        Event_is_free=True,
    )
    reporters = [
        User.objects.create_user(username=f"reporter-{index}")
        for index in range(3)
    ]

    for reporter in reporters:
        self.client.force_login(reporter)
        response = self.client.post(
            reverse("report_event"),
            {
                "event_slug": event.slug,  # Double check if view expects event.id
                "reason": "other",
                "details": "Needs review",
            },
        )
        self.assertRedirects(response, reverse("finders_dashboard"))

    # Reload from DB after all 3 POST requests complete
    event.refresh_from_db()

    # Assertions
    self.assertEqual(event.reports.values("reported_by").distinct().count(), 3)
    self.assertTrue(event.Event_is_flagged)
    notify_admins.assert_called_once_with(event.id, reporters[2].username)

class OrganizerVerificationServiceTest(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(
            username="verified-organizer",
            password="testpass123",
            is_organiser=True,
        )
        self.reviewer = User.objects.create_user(
            username="verification-reviewer", password="testpass123"
        )

    def create_completed_event(self, title):
        return Event.objects.create(
            Event_organiser=self.organizer,
            Event_title=title,
            Event_flyer="https://example.com/event.jpg",
            Event_category="music",
            Event_details="Details",
            Event_location="Location",
            Event_date=date.today() - timedelta(days=1),
            Event_time=time(18, 0),
            Event_is_free=True,
        )

    def create_qualifying_data(self):
        events = [
            self.create_completed_event(f"Completed Event {index}")
            for index in range(4)
        ]
        for index in range(5):
            reviewer = User.objects.create_user(
                username=f"reviewer-{index}", password="testpass123"
            )
            ReviewEvent.objects.create(
                reviewed_by=reviewer,
                event=events[index % len(events)],
                rating=4 if index == 0 else 5,
                review="Reliable event",
            )
        return events

    def test_organizer_is_verified_when_all_requirements_are_met(self):
        self.create_qualifying_data()

        self.assertTrue(evaluate_organizer_verification(self.organizer.id))
        self.assertTrue(
            OrganizerProfile.objects.get(user=self.organizer).is_verified
        )

    def test_active_report_prevents_verification(self):
        events = self.create_qualifying_data()
        ReportEvent.objects.create(
            event=events[0],
            reported_by=self.reviewer,
            reason="other",
            report_status="pending",
        )

        self.assertFalse(evaluate_organizer_verification(self.organizer.id))
        self.assertFalse(
            OrganizerProfile.objects.get(user=self.organizer).is_verified
        )

    def test_new_review_triggers_verification_after_commit(self):
        events = self.create_qualifying_data()
        OrganizerProfile.objects.create(user=self.organizer)

        with self.captureOnCommitCallbacks(execute=True):
            ReviewEvent.objects.create(
                reviewed_by=self.reviewer,
                event=events[0],
                rating=5,
                review="Another reliable event",
            )

        self.assertTrue(
            OrganizerProfile.objects.get(user=self.organizer).is_verified
        )
