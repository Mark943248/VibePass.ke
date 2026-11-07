from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.contrib.auth.models import Group
from django.core import mail
from django.utils import timezone
from django.test import override_settings
from datetime import date, time
from Events.models import Event
from django.test import RequestFactory
from allauth.account.signals import user_signed_up
from allauth.socialaccount.models import SocialAccount, SocialLogin
from Users.tasks import send_otp_email_task
from Users.views import EMAIL_VERIFICATION_USER_SESSION_KEY

User = get_user_model()


class UserModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_user_creation(self):
        self.assertEqual(self.user.username, "testuser")
        self.assertEqual(self.user.email, "test@example.com")
        self.assertFalse(self.user.is_organiser)

    def test_is_event_organizer(self):
        self.assertFalse(self.user.is_Event_Organizer())
        self.user.is_organiser = True
        self.assertTrue(self.user.is_Event_Organizer())

    def test_user_str(self):
        self.assertEqual(str(self.user), "testuser")


class UserViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        # Create groups if they don't exist
        Group.objects.get_or_create(name="Event Finders")
        Group.objects.get_or_create(name="Event Organizers")

    def test_register_view_get(self):
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/register.html")

    def test_register_view_post_success(self):
        data = {
            "username": "newuser",
            "email": "new@example.com",
            "password": "newpass123",
        }
        response = self.client.post(reverse("register"), data)
        self.assertRedirects(response, reverse("verify_email"))
        user = User.objects.get(username="newuser")
        self.assertEqual(len(user.otp_code), 6)
        self.assertTrue(user.otp_code.isdigit())
        self.assertEqual(
            self.client.session[EMAIL_VERIFICATION_USER_SESSION_KEY], user.pk
        )

    def test_verify_email_accepts_the_pending_users_valid_otp(self):
        self.user.otp_code = "012345"
        self.user.otp_expiry = timezone.now() + timezone.timedelta(minutes=5)
        self.user.save(update_fields=["otp_code", "otp_expiry"])
        session = self.client.session
        session[EMAIL_VERIFICATION_USER_SESSION_KEY] = self.user.pk
        session.save()

        response = self.client.post(reverse("verify_email"), {"otp": "012345"})

        self.assertRedirects(response, reverse("login"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_verified)
        self.assertIsNone(self.user.otp_code)
        self.assertIsNone(self.user.otp_expiry)

    def test_verify_email_rejects_an_incorrect_otp(self):
        self.user.otp_code = "012345"
        self.user.otp_expiry = timezone.now() + timezone.timedelta(minutes=5)
        self.user.save(update_fields=["otp_code", "otp_expiry"])
        session = self.client.session
        session[EMAIL_VERIFICATION_USER_SESSION_KEY] = self.user.pk
        session.save()

        response = self.client.post(reverse("verify_email"), {"otp": "999999"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "verification code is invalid")
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_email_verified)

    def test_register_view_post_duplicate_username(self):
        data = {
            "username": "testuser",  # existing
            "email": "new@example.com",
            "password": "newpass123",
        }
        response = self.client.post(reverse("register"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Username already taken!")

    def test_login_view_get(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/login.html")

    def test_login_view_post_success(self):
        self.user.is_email_verified = True
        self.user.save(update_fields=["is_email_verified"])
        data = {"username": "testuser", "password": "testpass123"}
        response = self.client.post(reverse("login"), data)
        self.assertRedirects(response, reverse("finders_dashboard"))

    def test_login_view_when_email_not_verified(self):
        data = {"username": "testuser", "password": "testpass123"}
        response = self.client.post(reverse("login"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid login credentials")

    def test_login_view_post_invalid(self):
        data = {"username": "testuser", "password": "wrongpass"}
        response = self.client.post(reverse("login"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid login credentials")

    def test_logout_view(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("logout"))
        self.assertRedirects(response, reverse("login"))

    def test_make_event_organiser(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(
            reverse("make_organiser"), {"mpesa_number": "0712345678"}
        )
        self.assertRedirects(response, reverse("organizers_dashboard"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_organiser)
        self.assertEqual(self.user.mpesa_number, "254712345678")

    def test_make_event_organiser_requires_valid_mpesa_number(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(
            reverse("make_organiser"), {"mpesa_number": "invalid"}
        )
        self.assertRedirects(response, reverse("finders_dashboard"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_organiser)

    def test_event_finders_dashboard(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("finders_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/Event_finder.html")

    def test_event_organizers_dashboard_unauthorized(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("organizers_dashboard"))
        # Pass target_status_code=302 to handle the appended next parameter smoothly
        self.assertRedirects(
            response, f"{reverse('login')}?next={reverse('organizers_dashboard')}"
        )

    def test_event_organizers_dashboard_authorized(self):
        self.user.is_organiser = True
        self.user.save()
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("organizers_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/Event_organiser.html")

    def test_flagged_event_banner_persists_until_event_is_resolved(self):
        self.user.is_organiser = True
        self.user.save()
        event = Event.objects.create(
            Event_organiser=self.user,
            Event_title="Flagged Event",
            Event_flyer="flagged.jpg",
            Event_category="other",
            Event_details="Details",
            Event_location="Location",
            Event_date=date.today(),
            Event_time=time(18, 0),
            Event_is_flagged=True,
        )
        self.client.login(username="testuser", password="testpass123")

        response = self.client.get(reverse("organizers_dashboard"))
        self.assertContains(response, "Action required: an event has been flagged")
        self.assertContains(response, event.Event_title)

        event.Event_is_flagged = False
        event.save(update_fields=["Event_is_flagged"])
        response = self.client.get(reverse("organizers_dashboard"))
        self.assertNotContains(response, "Action required: an event has been flagged")

class GoogleSignupVerificationTest(TestCase):
    def test_allauth_google_signup_marks_email_verified(self):
        user = User.objects.create_user(
            username="googleuser",
            email="googleuser@example.com",
            password="test-password",
        )
        request = RequestFactory().get("/")
        sociallogin = SocialLogin(
            account=SocialAccount(
                provider="google",
                uid="google-user-id",
                user=user,
            )
        )

        user_signed_up.send(
            sender=User,
            request=request,
            user=user,
            sociallogin=sociallogin,
        )

        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SendOtpEmailTaskTest(TestCase):
    def test_send_otp_email_task_sends_code_to_user(self):
        user = User.objects.create_user(
            username="otpuser",
            email="otpuser@example.com",
            password="test-password",
            otp_code="012345",
        )

        result = send_otp_email_task.run(user.pk)

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        self.assertEqual(
            mail.outbox[0].subject, "Your OTP Code for Email Verification"
        )
        self.assertIn("012345", mail.outbox[0].body)
