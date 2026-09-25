from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from unittest.mock import patch
from django.utils import timezone
from Events.models import Event
from .models import Payment, Withdrawal, PlatformRevenue
from Users.models import OrganizerWallet, OrganizerProfile
from .tasks import check_b2c_callback_task, process_mpesa_b2c_callbacks
from .utils import calculate_user_account_balance
from datetime import date, time
import uuid
from decimal import Decimal

User = get_user_model()


class PaymentModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.organizer = User.objects.create_user(
            username="organizer",
            email="org@example.com",
            password="testpass123",
            is_organiser=True,
        )
        self.event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title="Test Event",
            Event_flyer="test.jpg",
            Event_category="test",
            Event_details="Details",
            Event_location="Location",
            Event_date=date.today(),
            Event_time=time(18, 0),
            Event_is_free=False,
        )
        self.payment = Payment.objects.create(
            user=self.user,
            event=self.event,
            amount=100.00,
            mpesa_number="254712345678",
            payment_status="Pending",
        )

    def test_payment_creation(self):
        self.assertEqual(self.payment.user, self.user)
        self.assertEqual(self.payment.event, self.event)
        self.assertEqual(self.payment.amount, 100.00)
        self.assertEqual(self.payment.payment_status, "Pending")

    def test_payment_str(self):
        expected = f"Payment {self.payment.payment_id} - User: {self.user.username} - Event: {self.event.Event_title} - Amount: {self.payment.amount}"
        self.assertEqual(str(self.payment), expected)

    def test_payment_waiting_requires_payment_owner(self):
        payment_url = reverse("payment_waiting", args=[self.payment.payment_id])

        response = self.client.get(payment_url)
        self.assertRedirects(response, f"/users/login/?next={payment_url}")

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(payment_url)
        self.assertEqual(response.status_code, 200)

        other_user = User.objects.create_user(
            username="otheruser", password="testpass123"
        )
        self.client.force_login(other_user)
        response = self.client.get(payment_url)
        self.assertEqual(response.status_code, 404)


class WithdrawalModelTest(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(
            username="organizer",
            email="org@example.com",
            password="testpass123",
            is_organiser=True,
        )
        self.withdrawal = Withdrawal.objects.create(
            organiser=self.organizer,
            amount=500.00,
            mpesa_number="254712345678",
            status="pending",
        )

    def test_withdrawal_creation(self):
        self.assertEqual(self.withdrawal.organiser, self.organizer)
        self.assertEqual(self.withdrawal.amount, 500.00)
        self.assertEqual(self.withdrawal.status, "pending")

    def test_withdrawal_str(self):
        expected = f"Withdrawal {self.withdrawal.withdrawal_id} - Organizer: {self.organizer.username} - Amount: {self.withdrawal.amount} - Status: {self.withdrawal.status}"
        self.assertEqual(str(self.withdrawal), expected)

    def test_b2c_callback_watchdog_moves_open_withdrawal_to_reconciliation(self):
        self.withdrawal.status = "processing"
        self.withdrawal.save(update_fields=["status"])

        check_b2c_callback_task(str(self.withdrawal.withdrawal_id))

        self.withdrawal.refresh_from_db()
        self.assertEqual(self.withdrawal.status, "reconciling")
        self.assertIn("No B2C callback", self.withdrawal.reason)

    def test_b2c_callback_resolves_reconciling_withdrawal(self):
        self.withdrawal.status = "reconciling"
        self.withdrawal.originator_conversation_id = "originator-123"
        self.withdrawal.save(update_fields=["status", "originator_conversation_id"])
        OrganizerWallet.objects.create(
            organiser=self.organizer,
            available_withdraw_balance=Decimal("500.00"),
        )

        process_mpesa_b2c_callbacks(
            {
                "Result": {
                    "OriginatorConversationID": "originator-123",
                    "ResultCode": 0,
                    "TransactionID": "transaction-123",
                    "ResultDesc": "The service request is processed successfully.",
                }
            }
        )

        self.withdrawal.refresh_from_db()
        self.assertEqual(self.withdrawal.status, "completed")
        self.assertEqual(self.withdrawal.Transaction_id, "transaction-123")


class AccountBalanceCalculationTest(TestCase):
    def test_calculate_user_account_balance_uses_completed_payments_and_withdrawals(
        self,
    ):
        organizer = User.objects.create_user(
            username="balanceorganizer",
            email="balance@example.com",
            password="testpass123",
            is_organiser=True,
        )
        event = Event.objects.create(
            Event_organiser=organizer,
            Event_title="Balance Test Event",
            Event_flyer="test.jpg",
            Event_category="test",
            Event_details="Details",
            Event_location="Location",
            Event_date=date.today(),
            Event_time=time(18, 0),
            Event_is_free=False,
        )

        Payment.objects.create(
            user=organizer,
            event=event,
            amount=Decimal("100.00"),
            mpesa_number="254712345678",
            payment_status="Completed",
        )
        Payment.objects.create(
            user=organizer,
            event=event,
            amount=Decimal("50.00"),
            mpesa_number="254712345678",
            payment_status="Pending",
        )
        Withdrawal.objects.create(
            organiser=organizer,
            amount=Decimal("25.00"),
            mpesa_number="254712345678",
            status="completed",
        )
        Withdrawal.objects.create(
            organiser=organizer,
            amount=Decimal("20.00"),
            mpesa_number="254712345678",
            status="pending",
        )

        balance = calculate_user_account_balance(organizer)

        self.assertEqual(balance, Decimal("75.00"))
        self.assertEqual(
            OrganizerWallet.objects.get(organiser=organizer).available_withdraw_balance,
            Decimal("75.00"),
        )


class PaymentViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.organizer = User.objects.create_user(
            username="organizer",
            email="org@example.com",
            password="testpass123",
            is_organiser=True,
        )
        self.event = Event.objects.create(
            Event_organiser=self.organizer,
            Event_title="Test Event",
            Event_flyer="test.jpg",
            Event_category="test",
            Event_details="Details",
            Event_location="Location",
            Event_date=date.today(),
            Event_time=time(18, 0),
            Event_is_free=False,
        )

    def test_initiate_payment_view_unauthenticated(self):
        response = self.client.get(reverse("initiate_payment", args=[self.event.slug]))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('initiate_payment', args=[self.event.slug])}",
        )

    def test_initiate_payment_view_get(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("initiate_payment", args=[self.event.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "payments/checkout.html")

    def test_mpesa_callback_view_invalid_method(self):
        response = self.client.get(reverse("mpesa_callback"))
        self.assertEqual(response.status_code, 400)

    def test_request_withdrawal_view_unauthenticated(self):
        response = self.client.get(reverse("request_withdrawal"))
        self.assertRedirects(
            response, f"{reverse('login')}?next={reverse('request_withdrawal')}"
        )

    def test_request_withdrawal_view_non_organizer(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("request_withdrawal"))
        self.assertRedirects(response, f"{reverse("login")}?next={reverse('request_withdrawal')}")

    def test_request_withdrawal_view_get(self):
        self.client.login(username="organizer", password="testpass123")
        response = self.client.get(reverse("request_withdrawal"))
        self.assertEqual(response.status_code, 405)

    def test_request_withdrawal_requires_post(self):
        self.client.login(username="organizer", password="testpass123")
        response = self.client.post(reverse("request_withdrawal"))
        self.assertRedirects(response, reverse("organizers_dashboard"))
        self.assertFalse(Withdrawal.objects.filter(organiser=self.organizer).exists())

    @patch("Payments.views.initiate_b2c_request_task.delay")
    def test_flagged_event_blocks_withdrawal_even_with_other_event_payout_number(
        self, initiate_b2c
    ):
        wallet, _ = OrganizerWallet.objects.get_or_create(organiser=self.organizer)
        wallet.available_withdraw_balance = 500
        wallet.save(update_fields=["available_withdraw_balance"])
        Event.objects.create(
            Event_organiser=self.organizer,
            Event_title="Flagged Event",
            Event_flyer="flagged.jpg",
            Event_category="test",
            Event_details="Details",
            Event_location="Location",
            Event_date=date.today(),
            Event_time=time(18, 0),
            Event_is_free=False,
            Event_is_flagged=True,
        )

        self.client.login(username="organizer", password="testpass123")
        response = self.client.post(reverse("request_withdrawal"))

        self.assertRedirects(response, reverse("organizers_dashboard"))
        self.assertFalse(Withdrawal.objects.filter(organiser=self.organizer).exists())
        initiate_b2c.assert_not_called()

    @patch("Payments.views.initiate_b2c_request_task.delay")
    def test_withdrawal_allowed_when_all_events_are_clear(self, initiate_b2c):
        wallet, _ = OrganizerWallet.objects.get_or_create(organiser=self.organizer)
        wallet.available_withdraw_balance = 500
        self.organizer.mpesa_number = "254712345678"
        self.organizer.save(update_fields=["mpesa_number"])
        wallet.save(update_fields=["available_withdraw_balance"])

        self.client.login(username="organizer", password="testpass123")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("request_withdrawal"))

        self.assertRedirects(response, reverse("organizers_dashboard"))
        withdrawal = Withdrawal.objects.get(organiser=self.organizer)
        self.assertEqual(withdrawal.status, "pending")
        initiate_b2c.assert_called_once()

    @patch("Payments.views.initiate_b2c_request_task.delay")
    def test_verified_organizer_can_early_withdraw_with_5_percent_fee(self, initiate_b2c):
        wallet, _ = OrganizerWallet.objects.get_or_create(organiser=self.organizer)
        wallet.available_withdraw_balance = Decimal("200.00")
        wallet.pending_escrow_balance = Decimal("1000.00")
        wallet.save(update_fields=["available_withdraw_balance", "pending_escrow_balance"])

        OrganizerProfile.objects.update_or_create(
            user=self.organizer,
            defaults={"is_verified": True},
        )
        self.organizer.mpesa_number = "254712345678"
        self.organizer.save(update_fields=["mpesa_number"])

        self.client.login(username="organizer", password="testpass123")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("request_withdrawal"))

        self.assertRedirects(response, reverse("organizers_dashboard"))
        wallet.refresh_from_db()
        self.assertEqual(wallet.pending_escrow_balance, Decimal("500.00"))
        self.assertEqual(wallet.available_withdraw_balance, Decimal("675.00"))

        self.assertTrue(
            PlatformRevenue.objects.filter(
                organiser=self.organizer,
                source="Early-Payout",
                fee_amount=Decimal("25.00"),
            ).exists()
        )

        withdrawal = Withdrawal.objects.get(organiser=self.organizer)
        self.assertEqual(withdrawal.amount, Decimal("607.50"))
        self.assertEqual(initiate_b2c.call_args.args[0]["amount"], Decimal("607.50"))

    @patch("Payments.views.initiate_b2c_request_task.delay")
    def test_platform_fee_is_cut_from_withdrawal_amount(self, initiate_b2c):
        wallet, _ = OrganizerWallet.objects.get_or_create(organiser=self.organizer)
        wallet.available_withdraw_balance = Decimal("300.00")
        wallet.pending_escrow_balance = Decimal("0.00")
        wallet.save(update_fields=["available_withdraw_balance", "pending_escrow_balance"])
        self.organizer.mpesa_number = "254712345678"
        self.organizer.save(update_fields=["mpesa_number"])

        self.client.login(username="organizer", password="testpass123")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("request_withdrawal"))

        self.assertRedirects(response, reverse("organizers_dashboard"))
        withdrawal = Withdrawal.objects.get(organiser=self.organizer)
        self.assertEqual(withdrawal.amount, Decimal("270.00"))
        self.assertEqual(initiate_b2c.call_args.args[0]["amount"], Decimal("270.00"))
        self.assertTrue(
            PlatformRevenue.objects.filter(
                organiser=self.organizer,
                source="10% ticketsales",
                fee_amount=Decimal("30.00"),
            ).exists()
        )
