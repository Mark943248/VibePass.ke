from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from .models import Event
from datetime import date, time

User = get_user_model()

class EventModelTest(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer',
            email='org@example.com',
            password='testpass123',
            is_organiser=True
        )
        self.event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title='Test Event',
            Event_flyer='test_flyer.jpg',  # Mock file
            Event_category='music',
            Event_details='Test event details',
            Event_location='Test Location',
            Event_date=date.today(),
            Event_time=time(18, 0),
            Event_ticket_price=100.00,
            Event_is_free=False,
            Event_total_tickets=100,
            Event_mpesa_number='254712345678'
        )

    def test_event_creation(self):
        self.assertEqual(self.event.Event_title, 'Test Event')
        self.assertEqual(self.event.Event_organiser, self.organizer)
        self.assertEqual(self.event.Event_category, 'music')
        self.assertEqual(self.event.Event_ticket_price, 100.00)
        self.assertFalse(self.event.Event_is_free)
        self.assertEqual(self.event.Event_total_tickets, 100)

    def test_get_available_tickets(self):
        # Initially all tickets available
        self.assertEqual(self.event.get_available_tickets(), 100)

    def test_get_sold_tickets(self):
        # Initially no tickets sold
        self.assertEqual(self.event.get_sold_tickets(), 0)

    def test_event_str(self):
        self.assertEqual(str(self.event), f'Event: {self.event.Event_title}')


class EventViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.organizer = User.objects.create_user(
            username='organizer',
            email='org@example.com',
            password='testpass123',
            is_organiser=True
        )
        self.regular_user = User.objects.create_user(
            username='user',
            email='user@example.com',
            password='testpass123'
        )
        # Create a mock file for testing
        self.mock_flyer = SimpleUploadedFile(
            name='test_flyer.jpg',
            content=b'fake image content',
            content_type='image/jpeg'
        )

    def test_create_event_view_unauthenticated(self):
        response = self.client.get(reverse('create_event'))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('create_event')}")

    def test_create_event_view_non_organizer(self):
        self.client.login(username='user', password='testpass123')
        response = self.client.get(reverse('create_event'))
        self.assertRedirects(response, reverse('login'))

    def test_create_event_view_get(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('create_event'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'events/create_event.html')

    def test_create_event_view_post_success(self):
        self.client.login(username='organizer', password='testpass123')
        data = {
            'Event_title': 'New Test Event',
            'Event_flyer': self.mock_flyer,
            'Event_category': 'sports',
            'Event_details': 'New event details',
            'Event_location': 'New Location',
            'Event_date': date.today().isoformat(),
            'Event_time': '20:00',
            'Event_total_tickets': 50,
            'Event_is_free': 'off',  # Not free
            'Event_mpesa_number': '254712345678',
            'Event_ticket_price': '150.00'
        }
        response = self.client.post(reverse('create_event'), data)
        self.assertRedirects(response, reverse('list_event'))
        self.assertTrue(Event.objects.filter(Event_title='New Test Event').exists())

    def test_list_event_view(self):
        response = self.client.get(reverse('list_event'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'events/list_event.html')

    def test_search_event_view(self):
        response = self.client.get(reverse('search_event'), {'q': 'test'})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'events/list_event.html')

    def test_filter_by_category_view(self):
        response = self.client.get(reverse('filter_by_category', args=['music']))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'events/list_event.html')

    def test_filter_by_time_view(self):
        response = self.client.get(reverse('filter_by_time'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'events/list_event.html')

    def test_event_details_view(self):
        event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title='Details Test Event',
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
        response = self.client.get(reverse('event_details', args=[event.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'events/event_details.html')
