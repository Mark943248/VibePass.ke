from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from Events.models import Event
from Payments.models import Payment
from .models import Ticket
from datetime import date, time
import uuid

User = get_user_model()

class TicketModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.organizer = User.objects.create_user(
            username='organizer',
            email='org@example.com',
            password='testpass123',
            is_organiser=True
        )
        self.event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title='Test Event',
            Event_flyer='test.jpg',
            Event_category='test',
            Event_details='Details',
            Event_location='Location',
            Event_date=date.today(),
            Event_time=time(18, 0),
            Event_ticket_price=0,
            Event_is_free=True,
            Event_total_tickets=10
        )
        self.ticket = Ticket.objects.create(
            event=self.event,
            user=self.user,
            status='active'
        )

    def test_ticket_creation(self):
        self.assertEqual(self.ticket.event, self.event)
        self.assertEqual(self.ticket.user, self.user)
        self.assertEqual(self.ticket.status, 'active')
        self.assertFalse(self.ticket.is_scanned)

    def test_mark_as_scanned(self):
        success, message = self.ticket.mark_as_scanned()
        self.assertTrue(success)
        self.assertEqual(message, "Ticket marked as scanned successfully.")
        self.ticket.refresh_from_db()
        self.assertTrue(self.ticket.is_scanned)
        self.assertEqual(self.ticket.status, 'scanned')
        self.assertIsNotNone(self.ticket.scanned_at)

    def test_mark_as_scanned_already_scanned(self):
        self.ticket.is_scanned = True
        self.ticket.status = 'scanned'
        self.ticket.save()
        success, message = self.ticket.mark_as_scanned()
        self.assertFalse(success)
        self.assertEqual(message, "Ticket has already been scanned.")

    def test_ticket_str(self):
        expected = f"Ticket {self.ticket.ticket_id} for {self.event.Event_title} by {self.user.username}"
        self.assertEqual(str(self.ticket), expected)


class TicketViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.organizer = User.objects.create_user(
            username='organizer',
            email='org@example.com',
            password='testpass123',
            is_organiser=True
        )
        self.free_event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title='Free Event',
            Event_flyer='test.jpg',
            Event_category='test',
            Event_details='Details',
            Event_location='Location',
            Event_date=date.today(),
            Event_time=time(18, 0),
            Event_ticket_price=0,
            Event_is_free=True,
            Event_total_tickets=10
        )
        self.paid_event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title='Paid Event',
            Event_flyer='test.jpg',
            Event_category='test',
            Event_details='Details',
            Event_location='Location',
            Event_date=date.today(),
            Event_time=time(18, 0),
            Event_ticket_price=100.00,
            Event_is_free=False,
            Event_total_tickets=10,
            Event_mpesa_number='254712345678'
        )

    def test_book_free_ticket_unauthenticated(self):
        response = self.client.get(reverse('book_free_ticket', args=[self.free_event.slug]))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('book_free_ticket', args=[self.free_event.slug])}")

    def test_book_free_ticket_not_free(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('book_free_ticket', args=[self.paid_event.slug]))
        self.assertRedirects(response, reverse('event_details', args=[self.paid_event.slug]))

    def test_book_free_ticket_success(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('book_free_ticket', args=[self.free_event.slug]))
        # Should redirect to users_tickets
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Ticket.objects.filter(event=self.free_event, user=self.user).exists())

    def test_book_free_ticket_already_has_ticket(self):
        # Create existing ticket
        Ticket.objects.create(event=self.free_event, user=self.user, status='active')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('book_free_ticket', args=[self.free_event.slug]))
        self.assertRedirects(response, reverse('event_details', args=[self.free_event.slug]))

    def test_create_ticket_function(self):
        from .views import create_ticket
        payment = Payment.objects.create(
            user=self.user,
            event=self.paid_event,
            amount=100.00,
            mpesa_number='254712345678',
            payment_status='Completed'
        )
        ticket = create_ticket(payment_id=payment.payment_id)
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.event, self.paid_event)
        self.assertEqual(ticket.user, self.user)
        self.assertEqual(ticket.payment, payment)
