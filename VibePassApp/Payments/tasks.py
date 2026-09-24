import os
import uuid
import json
import base64
import logging
import requests
from celery import shared_task
from datetime import timedelta, datetime
from decimal import Decimal
from decouple import config
from django.db import transaction
from .signals import payment_successful
from django.utils import timezone
from django.shortcuts import redirect
from Events.models import Event, ReportEvent
from django.conf import settings
from .models import Payment, Withdrawal, EscrowModel
from Users.models import OrganizerWallet
from .utils import (
    generate_access_token,
    generate_timestamp,
    calculate_net_earnings,
    generate_mpesa_security_credential,
)
from .consumers import (
    send_payment_status_update,
    update_dashboard_balance_after_withdraw,
)

logger = logging.getLogger(__name__)


def mark_withdrawal_failed(withdrawal_id, reason):
    """Fail an open withdrawal without overwriting a later provider callback."""
    updated = Withdrawal.objects.filter(
        withdrawal_id=withdrawal_id,
        status__in=["pending", "processing"],
    ).update(status="failed", reason=str(reason)[:1000])
    if updated:
        logger.error("Withdrawal %s failed: %s", withdrawal_id, reason)


@shared_task()
def check_b2c_callback_task(withdrawal_id):
    """Move an unresolved B2C withdrawal to reconciliation after the callback grace period."""
    updated = Withdrawal.objects.filter(
        withdrawal_id=withdrawal_id,
        status__in=["pending", "processing"],
    ).update(
        status="reconciling",
        reason="No B2C callback received; transaction requires reconciliation",
    )
    if updated:
        logger.error(
            "No B2C callback received for withdrawal %s; marked for reconciliation",
            withdrawal_id,
        )


@shared_task(
    bind=True, 
    max_retries=3,
)
def initiate_mpesa_stk_push_task(self, data):
    """Perform an M-Pesa STK Push request and return a JSON-serializable response."""
    event = Event.objects.get(id=data["Event_id"])
    formatted_phone = data["formatted_phone"]
    access_token = generate_access_token()
    if not access_token:
        raise Exception("Failed to obtain access token")

    timestamp = generate_timestamp()
    short_code = os.getenv("MPESA_SHORT_CODE")
    passkey = os.getenv("MPESA_PASSKEY")
    data_to_encode = f"{short_code}{passkey}{timestamp}"
    online_password = base64.b64encode(data_to_encode.encode()).decode()
    callback_base = config("MPESA_CALLBACK_URL")
    callback_url = callback_base.rstrip("/")
    if not callback_url.endswith("/payments/mpesa_callback"):
        callback_url = f"{callback_url}/payments/mpesa_callback"

    payload = {
        "BusinessShortCode": short_code,
        "Password": online_password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(data["amount"]),
        "PartyA": formatted_phone,
        "PartyB": short_code,
        "PhoneNumber": formatted_phone,
        "CallBackURL": callback_url,
        "AccountReference": f"Purchase of {event.Event_title} ticket - {data['Payment_id']}",
        "TransactionDesc": "Event Ticket Purchase",
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    stk_push_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

    try:
        response = requests.post(
            stk_push_url, 
            json=payload, 
            headers=headers, 
            timeout=(15, 30)
        )
        response.raise_for_status()
        payment = Payment.objects.get(payment_id=data["Payment_id"])
        if response.json().get("ResponseCode") == "0":
            payment.checkout_request_id = response.json().get("CheckoutRequestID")
            payment.save(update_fields=["checkout_request_id"])
            logger.info(
                f"STK Push initiated successfully for payment_id: {payment.payment_id}"
            )
        else:
            payment.payment_status = "Failed"
            payment.save(update_fields=["payment_status"])
            send_payment_status_update(payment)
            logger.error(
                f"STK Push failed for payment_id: {payment.payment_id} - Error: {response.json().get('ResultDesc', 'Error in stk push')}"
            )
    except (requests.exceptions.Timeout, requests.exceptions.RequestException) as exc:
        if self.request.retries < self.max_retries:
            countdown = 10 * (2**self.request.retries)
            logger.warning(
                "STK Push attempt %s failed for payment_id %s; retrying in %s seconds: %s",
                self.request.retries + 1,
                data["Payment_id"],
                countdown,
                exc,
            )
            raise self.retry(exc=exc, countdown=countdown)
        payment = Payment.objects.get(payment_id=data["Payment_id"])
        payment.payment_status = "Failed"
        payment.save(update_fields=["payment_status"])
        send_payment_status_update(payment)
        logger.error(
            f"STK Push failed after {self.max_retries + 1} attempts for payment_id: {payment.payment_id} - Error: {exc}"
        )
    except Exception as exc:
        payment = Payment.objects.get(payment_id=data["Payment_id"])
        payment.payment_status = "Failed"
        payment.save(update_fields=["payment_status"])
        send_payment_status_update(payment)
        logger.exception(
            f"Unexpected error during STK Push for payment_id: {payment.payment_id} - Error: {exc}"
        )

@shared_task(
    bind=True,
    max_retries=3,
)
def check_payment_status_task(self, payment_id):
    try:
        payment = Payment.objects.get(payment_id=payment_id)
    except Payment.DoesNotExist:
        logger.error(f"Payment not found with payment_id: {payment_id}")
        return None

    # Idempotency check: Exit early if callback or previous query already resolved it
    if payment.payment_status != "Pending":
        logger.info(
            f"Payment status for payment_id {payment_id} is already {payment.payment_status}. No action needed."
        )
        return None

    timestamp = generate_timestamp()
    short_code = os.getenv("MPESA_SHORT_CODE")
    passkey = os.getenv("MPESA_PASSKEY")
    password = base64.b64encode(f"{short_code}{passkey}{timestamp}".encode()).decode()
    access_token = generate_access_token()

    payload = {
        "BusinessShortCode": short_code,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": payment.checkout_request_id,
    }

    url = "https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query"

    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=(5, 40),
        )
        response.raise_for_status()
        data = response.json()
        raw_result_code = data.get("ResultCode")

        try:
            result_code = int(raw_result_code)
        except (TypeError, ValueError):
            result_code = -1

        with transaction.atomic():
            # Lock the row to prevent race conditions with incoming webhook callbacks
            payment = Payment.objects.select_for_update().get(payment_id=payment_id)
            
            # Double check status inside atomic block
            if payment.payment_status != "Pending":
                logger.info(f"Payment {payment_id} was updated concurrently to {payment.payment_status}. Aborting.")
                return None

            if result_code == 0:
                payment.payment_status = "Completed"
                receipt_number = data.get("MpesaReceiptNumber")
                if receipt_number:
                    payment.mpesa_receipt_number = receipt_number
                
                payment.save()
                logger.info(f"Payment query confirmed success for payment_id: {payment.payment_id}")

                # -----------------------------------------------------------
                # FEED ESCROW MODEL & UPDATE WALLET
                # -----------------------------------------------------------
                event = payment.event
                event_datetime = datetime.combine(event.Event_date, event.Event_time)
                release_window = event_datetime + timedelta(hours=24)

                EscrowModel.objects.create(
                    payment=payment,
                    organizer=event.Event_organiser,
                    event=event,
                    amount=payment.amount,
                    release_date=release_window
                )

                wallet, _ = OrganizerWallet.objects.get_or_create(organiser=event.Event_organiser)
                wallet.pending_escrow_balance += payment.amount
                wallet.save()

                # Dispatch completion signals
                payment_successful.send(sender=Payment, payment=payment)
                send_payment_status_update(payment)

            else:
                payment.payment_status = "Failed"
                payment.save()
                logger.info(
                    f'Payment failed query for payment ID {payment.payment_id} (Code: {result_code}): {data.get("ResultDesc", "Unknown error")}'
                )
                send_payment_status_update(payment)

    except (requests.exceptions.Timeout, requests.exceptions.RequestException) as exc:
        if self.request.retries < self.max_retries:
            countdown = 10 * (2 ** self.request.retries)
            logger.warning(
                "Payment status check attempt %s failed for payment_id %s; retrying in %s seconds: %s",
                self.request.retries + 1,
                payment_id,
                countdown,
                exc,
            )
            raise self.retry(exc=exc, countdown=countdown)

        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(payment_id=payment_id)
            if payment.payment_status == "Pending":
                payment.payment_status = "Failed"
                payment.save()
                send_payment_status_update(payment)

        logger.error(
            f"Payment status check failed after {self.max_retries + 1} attempts for payment_id: {payment_id} - Error: {exc}"
        )

    except Exception as exc:
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(payment_id=payment_id)
            if payment.payment_status == "Pending":
                payment.payment_status = "Failed"
                payment.save()
                send_payment_status_update(payment)

        logger.exception(
            f"Unexpected error during payment status check for payment_id: {payment_id} - Error: {exc}"
        )


@shared_task
def process_mpesa_stk_callbacks(data):
    """
    Processes M-Pesa STK callbacks via a Celery worker.
    """
    mpesa_info = data.get("Body", {}).get("stkCallback", {})
    checkout_request_id = mpesa_info.get("CheckoutRequestID")
    raw_result_code = mpesa_info.get("ResultCode")
    result_desc = mpesa_info.get("ResultDesc", "Unknown error")

    if not checkout_request_id:
        logger.error("No checkout_request_id in callback data")
        return None

    # Parse ResultCode safely without overwriting it
    try:
        result_code = int(raw_result_code)
    except (TypeError, ValueError):
        logger.warning(f"Unexpected ResultCode type: {raw_result_code}")
        result_code = -1

    with transaction.atomic():
        try:
            # Use select_for_update to lock the row during transaction
            payment = Payment.objects.select_for_update().get(checkout_request_id=checkout_request_id)
        except Payment.DoesNotExist:
            logger.error(f"Payment not found with checkout_request_id: {checkout_request_id}")
            return None

        # Idempotency check: Skip if already processed
        if payment.payment_status in ["Completed", "Failed"]:
            logger.info(f"Payment {payment.payment_id} already processed as {payment.payment_status}")
            return None

        if result_code == 0:
            payment.payment_status = "Completed"
            
            # Extract receipt number cleanly
            items = mpesa_info.get("CallbackMetadata", {}).get("Item", [])
            for item in items:
                if item.get("Name") == "MpesaReceiptNumber":
                    payment.mpesa_receipt_number = item.get("Value")
                    break

            payment.save()
            logger.info(f"Payment successful for payment_id: {payment.payment_id}")

            # -----------------------------------------------------------
            # ESCROW & WALLET INGESTION (Fed on Payment Success)
            # -----------------------------------------------------------
            event = payment.event
            event_datetime = datetime.combine(event.Event_date, event.Event_time)
            release_window = event_datetime + timedelta(hours=24)

            # 1. Feed Escrow Hold
            EscrowModel.objects.create(
                payment=payment,
                organiser=event.Event_organiser,
                event=event,
                amount=payment.amount,
                release_date=release_window
            )

            # 2. Increment Organizer Pending Balance
            wallet, _ = OrganizerWallet.objects.get_or_create(organiser=event.Event_organiser)
            wallet.pending_escrow_balance += payment.amount
            wallet.save()

            # Dispatch success signals (e.g., to generate QR ticket, send SMS/email)
            payment_successful.send(sender=Payment, payment=payment)
            send_payment_status_update(payment)

        else:
            payment.payment_status = "Failed"
            payment.save()
            logger.info(f"Payment failed for payment ID {payment.payment_id} (Code {result_code}): {result_desc}")
            send_payment_status_update(payment)



@shared_task(
    bind=True,
    max_retries=3,
)
def initiate_b2c_request_task(self, data):
    """Initiate a Business to Customer (B2C) payment request to M-Pesa.
    This function generates an access token, prepares the request data, and sends a POST request to the M-Pesa B2C API endpoint. It returns the JSON response from the API.
    """
    withdrawal_id = data["withdrawal_id"]
    try:
        Withdrawal.objects.get(withdrawal_id=withdrawal_id)
    except Withdrawal.DoesNotExist:
        logger.error("Withdrawal %s does not exist", withdrawal_id)
        return None

    try:
        access_token = generate_access_token()
        api_url = "https://sandbox.safaricom.co.ke/mpesa/b2c/v3/paymentrequest"
        headers = {"Authorization": f"Bearer {access_token}"}
        callback_base = config("MPESA_CALLBACK_URL").rstrip("/")
        result_url = f"{callback_base}/payments/mpesa_b2c_callback"
        timeout_url = f"{callback_base}/payments/mpesa_b2c_timeout"
        originator_conversation_id = data.setdefault(
            "originator_conversation_id", str(uuid.uuid4())
        )
        request_data = {
            "OriginatorConversationID": originator_conversation_id,
            "InitiatorName": os.getenv("MPESA_INITIATOR_NAME"),
            "SecurityCredential": generate_mpesa_security_credential(),
            "CommandID": "BusinessPayment",
            "Amount": calculate_net_earnings(int(data["amount"])),
            "PartyA": os.getenv("MPESA_B2C_SHORT_CODE"),
            "PartyB": data["phone_number"],
            "Remarks": "remarked",
            "QueueTimeOutURL": timeout_url,
            "ResultURL": result_url,
            "Occassion": "VibePass Organizer Withdrawal",
        }
        response = requests.post(
            api_url, json=request_data, headers=headers, timeout=(15, 30)
        )
        response.raise_for_status()
        b2c_response = response.json()
        withdrawal = Withdrawal.objects.get(withdrawal_id=withdrawal_id)

        logger.info(
            f"B2C request initiated for withdrawal {withdrawal_id}: {b2c_response}"
        )

        # Handle M-Pesa B2C response
        if str(b2c_response.get("ResponseCode")) == "0":
            originator_conversation_id = b2c_response.get("OriginatorConversationID")
            conversation_id = b2c_response.get("ConversationID")
            if not originator_conversation_id or not conversation_id:
                mark_withdrawal_failed(
                    withdrawal_id,
                    "B2C response did not include conversation identifiers",
                )
                return None
            withdrawal.status = "processing"
            withdrawal.originator_conversation_id = originator_conversation_id
            withdrawal.mpesa_conversation_id = conversation_id
            withdrawal.save()
            check_b2c_callback_task.apply_async(
                (withdrawal_id,), countdown=10 * 60
            )
            logger.info(
                f"Withdrawal Request for {withdrawal.withdrawal_id} is successful"
            )
        else:
            withdrawal.status = "failed"
            withdrawal.reason = b2c_response.get(
                "ResponseDescription", "B2C request failed"
            )
            withdrawal.save()
            error_msg = b2c_response.get(
                "ResponseDescription",
                "Withdrawal initiation failed. Please try again.",
            )
            logger.error(f"B2C request failed: {error_msg}")

    except (requests.exceptions.Timeout, requests.exceptions.RequestException) as exc:
        if self.request.retries < self.max_retries:
            countdown = 10 * (2**self.request.retries)
            logger.warning(
                "B2C request attempt %s failed for withdrawal %s; retrying in %s seconds: %s",
                self.request.retries + 1,
                withdrawal_id,
                countdown,
                exc,
            )
            raise self.retry(exc=exc, countdown=countdown)
        mark_withdrawal_failed(
            withdrawal_id,
            f"B2C request failed after {self.max_retries + 1} attempts: {exc}",
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        mark_withdrawal_failed(withdrawal_id, f"B2C setup failed: {exc}")
    except Exception:
        logger.exception("Unexpected B2C initiation failure for %s", withdrawal_id)
        mark_withdrawal_failed(withdrawal_id, "Unexpected B2C initiation failure")


@shared_task()
def process_mpesa_b2c_callbacks(data):
    """
    Processes M-Pesa B2C (Business to Customer) withdrawal callback payloads
    asynchronously to update transaction status and adjust balance records.
    """

    originator_conversation_id = data.get("Result", {}).get(
        "OriginatorConversationID", "unknown"
    )
    mpesa_details = data.get("Result", {})
    result_code = mpesa_details.get("ResultCode")
    originator_conversation_id = mpesa_details.get("OriginatorConversationID")
    transaction_id = mpesa_details.get("TransactionID")
    result_desc = mpesa_details.get("ResultDesc")

    try:
        result_code = int(result_code)
    except (TypeError, ValueError):
        logger.error(
            "Invalid B2C ResultCode for conversation %s: %r",
            originator_conversation_id,
            result_code,
        )
        return None

    try:
        with transaction.atomic():
            withdrawal = Withdrawal.objects.select_for_update().get(
                originator_conversation_id=originator_conversation_id
            )

            organiser_wallet, created = OrganizerWallet.objects.select_for_update().get_or_create(
                organiser=withdrawal.organiser
            )
            organiser_withdrawable_balance = Decimal(
                str(organiser_wallet.available_withdraw_balance)
            )

            withdrawn_amount = withdrawal.amount

            if withdrawal.status in ["completed", "failed"]:
                logger.info(
                    "Ignoring duplicate terminal B2C callback for withdrawal %s",
                    withdrawal.withdrawal_id,
                )
                return None

            if result_code == 0:
                if organiser_withdrawable_balance < withdrawn_amount:
                    withdrawal.status = "reconciling"
                    withdrawal.reason = (
                        "Completed M-Pesa payout exceeds the organizer wallet balance; "
                        "manual reconciliation required."
                    )
                    withdrawal.Transaction_id = transaction_id
                    withdrawal.save(
                        update_fields=["status", "reason", "Transaction_id", "updated_at"]
                    )
                    logger.error(
                        "Withdrawal %s completed by M-Pesa but wallet balance is "
                        "insufficient: balance=%s, payout=%s",
                        withdrawal.withdrawal_id,
                        organiser_withdrawable_balance,
                        withdrawn_amount,
                    )
                    return None

                withdrawal.status = "completed"
                withdrawal.mpesa_receipt_number = transaction_id
                withdrawal.Transaction_id = transaction_id
                withdrawal.save()
                logger.info(
                    f"Withdrawal completed successfully: {withdrawal.withdrawal_id}"
                )
                new_balance = organiser_withdrawable_balance - withdrawn_amount
                organiser_wallet.available_withdraw_balance = new_balance
                organiser_wallet.save(update_fields=["available_withdraw_balance", "updated_at"])
                update_dashboard_balance_after_withdraw(withdrawal, new_balance)
                logger.info(f"Users account balance after deduction: {new_balance}")
            else:
                withdrawal.status = "failed"
                withdrawal.reason = result_desc
                withdrawal.Transaction_id = transaction_id
                withdrawal.save()
                logger.error(
                    f"Withdrawal failed: {withdrawal.withdrawal_id} - Reason: {result_desc}"
                )

    except Withdrawal.DoesNotExist:
        logger.error(f"Transaction does not exist: {originator_conversation_id}")


@shared_task
def release_matured_escrow_holds():
    """
    Periodic task that finds matured escrow holds and shifts funds
    from pending_hold_balance to available_balance.
    """
    now = timezone.now()

    # 1. Fetch holds that are past release_date and still HELD
    matured_holds = EscrowModel.objects.filter(
        payout_status="Held",
        release_date__lte=now,
        released_at__isnull=True,
    ).select_related('event', 'organiser')

    released_count = 0
    skipped_count = 0

    for hold in matured_holds:
        event = hold.event
        
        # 2. Check if the event has unresolved or upheld safety/fraud reports
        has_active_reports = ReportEvent.objects.filter(
            event=event,
            status__in=['Pending', 'Under_Review', 'Action_Taken']
        ).exists()

        if has_active_reports:
            logger.warning(
                f"Skipping release for EscrowHold #{hold.id} (Event: {event.id}) due to active reports."
            )
            # Freeze the hold automatically if there are pending reports
            hold.payout_status = "Frozen"
            hold.save()
            skipped_count += 1
            continue

        # 3. Transfer funds atomically
        with transaction.atomic():
            # Lock the wallet row for concurrent updates
            wallet, _ = OrganizerWallet.objects.select_for_update().get_or_create(
                organiser=hold.organiser
            )

            # Move funds from pending to available
            wallet.pending_escrow_balance -= hold.amount
            wallet.available_withdraw_balance += hold.amount
            wallet.save(update_fields=[
                "pending_escrow_balance",
                "available_withdraw_balance",
                "updated_at",
            ])

            # Mark hold as RELEASED
            hold.payout_status = "Released"
            hold.released_at = now
            hold.save(update_fields=["payout_status", "released_at"])

            released_count += 1

    logger.info(
        f"Escrow release task finished. Released: {released_count} | Frozen/Skipped: {skipped_count}"
    )
    return f"Released {released_count} holds."