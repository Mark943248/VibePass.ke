from datetime import date, time

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from .models import Event, TicketType

User = get_user_model()


class EventModelTest(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer',
            email='org@example.com',
            password='testpass123',
            is_organiser=True,
        )
        self.event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title='Test Event',
            Event_flyer='https://example.com/flyer.jpg',
            Event_category='music',
            Event_details='Test event details',
            Event_location='Test Location',
            Event_date=date.today(),
            Event_time=time(18, 0),
            Event_is_free=False,
            Event_mpesa_number='254712345678',
        )
        self.ticket_type = TicketType.objects.create(
            event=self.event,
            name='Regular',
            description='Standard access',
            price=1000.00,
            capacity=50,
        )

    def test_event_creation(self):
        self.assertEqual(self.event.Event_title, 'Test Event')
        self.assertEqual(self.event.Event_organiser, self.organizer)
        self.assertEqual(self.event.Event_category, 'music')
        self.assertFalse(self.event.Event_is_free)
        self.assertTrue(self.event.slug)

    def test_ticket_capacity_and_price_summary(self):
        TicketType.objects.create(
            event=self.event,
            name='VIP',
            description='Premium access',
            price=2500.00,
            capacity=20,
        )

        self.assertEqual(self.event.total_ticket_capacity, 70)
        self.assertEqual(self.event.min_ticket_price, 1000.00)
        self.assertEqual(self.event.price_summary, 'KES 1000.00')

    def test_get_sold_tickets_and_percentage(self):
        self.assertEqual(self.event.get_sold_tickets(), 0)
        self.assertEqual(self.event.percentage_of_sold_tickets(), 0)

    def test_event_str(self):
        self.assertEqual(str(self.event), self.event.Event_title)


class EventViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.organizer = User.objects.create_user(
            username='organizer',
            email='org@example.com',
            password='testpass123',
            is_organiser=True,
        )
        self.regular_user = User.objects.create_user(
            username='user',
            email='user@example.com',
            password='testpass123',
        )

    def test_create_event_view_unauthenticated(self):
        response = self.client.get(reverse('create_event'))
        self.assertRedirects(response, f"/account/login/?next={reverse('create_event')}")

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
            'Event_category': 'sports',
            'Event_details': 'New event details',
            'Event_location': 'New Location',
            'Event_date': date.today().isoformat(),
            'Event_time': '20:00',
            'Event_is_free': 'on',
            'ticket_name[]': ['VIP'],
            'ticket_price[]': ['150.00'],
            'ticket_capacity[]': ['50'],
            'ticket_description[]': ['VIP access'],
        }
        files = {
            'Event_flyer': SimpleUploadedFile(
                'flyer.jpg',
                b'fake-image-content',
                content_type='image/jpeg',
            )
        }
        response = self.client.post(reverse('create_event'), data=data, files=files)
        self.assertRedirects(response, reverse('list_event'))
        self.assertTrue(Event.objects.filter(Event_title='New Test Event').exists())
        self.assertTrue(TicketType.objects.filter(event__Event_title='New Test Event', name='VIP').exists())

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

    def test_event_details_view(self):
        event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title='Details Test Event',
            Event_flyer='https://example.com/details.jpg',
            Event_category='tech events',
            Event_details='Details',
            Event_location='Location',
            Event_date=date.today(),
            Event_time=time(18, 0),
            Event_is_free=True,
        )
        TicketType.objects.create(
            event=event,
            name='Regular',
            description='General access',
            price=0.00,
            capacity=10,
        )
        response = self.client.get(reverse('event_details', args=[event.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'events/event_details.html')
