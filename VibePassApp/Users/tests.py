from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.contrib.auth.models import Group

User = get_user_model()

class UserModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_user_creation(self):
        self.assertEqual(self.user.username, 'testuser')
        self.assertEqual(self.user.email, 'test@example.com')
        self.assertFalse(self.user.is_organiser)

    def test_is_event_organizer(self):
        self.assertFalse(self.user.is_Event_Organizer())
        self.user.is_organiser = True
        self.assertTrue(self.user.is_Event_Organizer())

    def test_user_str(self):
        self.assertEqual(str(self.user), 'testuser')


class UserViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        # Create groups if they don't exist
        Group.objects.get_or_create(name='Event Finders')
        Group.objects.get_or_create(name='Event Organizers')

    def test_register_view_get(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/register.html')

    def test_register_view_post_success(self):
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'newpass123'
        }
        response = self.client.post(reverse('register'), data)
        self.assertRedirects(response, reverse('login'))
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_register_view_post_duplicate_username(self):
        data = {
            'username': 'testuser',  # existing
            'email': 'new@example.com',
            'password': 'newpass123'
        }
        response = self.client.post(reverse('register'), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Username already taken!')

    def test_login_view_get(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/login.html')

    def test_login_view_post_success(self):
        data = {
            'username': 'testuser',
            'password': 'testpass123'
        }
        response = self.client.post(reverse('login'), data)
        self.assertRedirects(response, reverse('finders_dashboard'))

    def test_login_view_post_invalid(self):
        data = {
            'username': 'testuser',
            'password': 'wrongpass'
        }
        response = self.client.post(reverse('login'), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid login credentials')

    def test_logout_view(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('logout'))
        self.assertRedirects(response, reverse('login'))

    def test_make_event_organiser(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('make_organiser'))
        self.assertRedirects(response, reverse('organizers_dashboard'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_organiser)

    def test_event_finders_dashboard(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('finders_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/Event_finder.html')

    def test_event_organizers_dashboard_unauthorized(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('organizers_dashboard'))
        # Pass target_status_code=302 to handle the appended next parameter smoothly
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('organizers_dashboard')}")

    def test_event_organizers_dashboard_authorized(self):
        self.user.is_organiser = True
        self.user.save()
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('organizers_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/Event_organiser.html')
