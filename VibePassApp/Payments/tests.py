from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from Events.models import Event
from .models import Payment, Withdrawal, calculate_user_account_balance
from datetime import date, time
import uuid
from decimal import Decimal

User = get_user_model()

class PaymentModelTest(TestCase):
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
            Event_ticket_price=100.00,
            Event_is_free=False,
            Event_total_tickets=10,
            Event_mpesa_number='254712345678'
        )
        self.payment = Payment.objects.create(
            user=self.user,
            event=self.event,
            amount=100.00,
            mpesa_number='254712345678',
            payment_status='Pending'
        )

    def test_payment_creation(self):
        self.assertEqual(self.payment.user, self.user)
        self.assertEqual(self.payment.event, self.event)
        self.assertEqual(self.payment.amount, 100.00)
        self.assertEqual(self.payment.payment_status, 'Pending')

    def test_payment_str(self):
        expected = f"Payment {self.payment.payment_id} - User: {self.user.username} - Event: {self.event.Event_title} - Amount: {self.payment.amount}"
        self.assertEqual(str(self.payment), expected)


class WithdrawalModelTest(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer',
            email='org@example.com',
            password='testpass123',
            is_organiser=True
        )
        self.withdrawal = Withdrawal.objects.create(
            organiser=self.organizer,
            amount=500.00,
            mpesa_number='254712345678',
            status='pending'
        )

    def test_withdrawal_creation(self):
        self.assertEqual(self.withdrawal.organiser, self.organizer)
        self.assertEqual(self.withdrawal.amount, 500.00)
        self.assertEqual(self.withdrawal.status, 'pending')

    def test_withdrawal_str(self):
        expected = f"Withdrawal {self.withdrawal.withdrawal_id} - Organizer: {self.organizer.username} - Amount: {self.withdrawal.amount} - Status: {self.withdrawal.status}"
        self.assertEqual(str(self.withdrawal), expected)


class AccountBalanceCalculationTest(TestCase):
    def test_calculate_user_account_balance_uses_completed_payments_and_withdrawals(self):
        organizer = User.objects.create_user(
            username='balanceorganizer',
            email='balance@example.com',
            password='testpass123',
            is_organiser=True
        )
        event = Event.objects.create(
            Event_organiser=organizer,
            Event_title='Balance Test Event',
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

        Payment.objects.create(
            user=organizer,
            event=event,
            amount=Decimal('100.00'),
            mpesa_number='254712345678',
            payment_status='Completed'
        )
        Payment.objects.create(
            user=organizer,
            event=event,
            amount=Decimal('50.00'),
            mpesa_number='254712345678',
            payment_status='Pending'
        )
        Withdrawal.objects.create(
            organiser=organizer,
            amount=Decimal('25.00'),
            mpesa_number='254712345678',
            status='completed'
        )
        Withdrawal.objects.create(
            organiser=organizer,
            amount=Decimal('20.00'),
            mpesa_number='254712345678',
            status='pending'
        )

        balance = calculate_user_account_balance(organizer)

        self.assertEqual(balance, Decimal('75.00'))
        self.assertEqual(organizer.account_balance, Decimal('75.00'))


class PaymentViewsTest(TestCase):
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
        self.event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title='Test Event',
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

    def test_initiate_payment_view_unauthenticated(self):
        response = self.client.get(reverse('initiate_payment', args=[self.event.slug]))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('initiate_payment', args=[self.event.slug])}")

    def test_initiate_payment_view_get(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('initiate_payment', args=[self.event.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'payments/checkout.html')

    def test_check_payment_status_view(self):
        self.client.login(username='testuser', password='testpass123')
        payment = Payment.objects.create(
            user=self.user,
            event=self.event,
            amount=100.00,
            mpesa_number='254712345678',
            payment_status='Pending'
        )
        response = self.client.get(reverse('check_payment_status', args=[payment.payment_id]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'Pending')
        self.assertEqual(data['payment_id'], str(payment.payment_id))

    def test_check_payment_status_not_found(self):
        self.client.login(username='testuser', password='testpass123')
        fake_id = uuid.uuid4()
        response = self.client.get(reverse('check_payment_status', args=[fake_id]))
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data['status'], 'error')

    def test_mpesa_callback_view_invalid_method(self):
        response = self.client.get(reverse('mpesa_callback'))
        self.assertEqual(response.status_code, 400)

    def test_request_withdrawal_view_unauthenticated(self):
        response = self.client.get(reverse('request_withdrawal'))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('request_withdrawal')}")

    def test_request_withdrawal_view_non_organizer(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('request_withdrawal'))
        self.assertRedirects(response, reverse('login'))

    def test_request_withdrawal_view_get(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('request_withdrawal'))
        self.assertEqual(response.status_code, 200)
        # Assuming it renders a template, check if it doesn't crash
