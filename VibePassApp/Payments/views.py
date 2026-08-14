from django.shortcuts import render, redirect, get_object_or_404
from .tasks import (
    process_mpesa_stk_callbacks,
    process_mpesa_b2c_callbacks,
    initiate_mpesa_stk_push_task,
    check_payment_status_task,
    initiate_b2c_request_task,
)
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.csrf import csrf_exempt
from Events.models import Event, TicketType
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from .utils import format_phone_number
from .models import Payment, Withdrawal
import json
import os
import logging

logger = logging.getLogger(__name__)


# Create your views here.
@login_required
def initiate_payment(request, slug):
    """
    Initiates the payment process for a specific event.
    Retrieves the checkout data from the session, validates the event and user input,
    and initiates the M-PESA STK push for payment.
    """
    checkout_data = request.session.get("checkout_data") or {}
    try:
        print(f"Checkoutdat: {checkout_data}")
        event = get_object_or_404(Event, slug=slug)
        amount = checkout_data.get("grand_total", 0)
        checkout_items = checkout_data.get("items", [])
    except Exception as e:
        print(f"Error occured: {e}")
        messages.error(request, "Unable to load checkout details. Please try again.")
        return redirect("event_details", slug=slug)

    if not checkout_items:
        messages.error(
            request, "Your cart is empty. Please select tickets before continuing."
        )
        return redirect("event_details", slug=slug)

    if request.method == "POST":
        phone_number = request.POST.get("phone_number", "").strip()
        agreed_to_terms = (
            "terms" in request.POST
        )  # To this (evaluates to True if checked, False if not)
        # validate if event is expired
        current_time = timezone.now().date()  # gets current date
        if event.Event_date < current_time:
            messages.info(request, "Sorry this event is out of date!")
            return redirect("event_details", slug=event.slug)
        # Validates the phone number
        if not phone_number:
            messages.error(request, "Please enter a phone number.")
            return redirect("event_details", slug=event.slug)
        # validates if user has agreed to terms & conditions
        if not agreed_to_terms:
            messages.error(request, "Agree to the Terms and Conditions")
            return redirect("event_details", slug=event.slug)
        # validates format of the phone number
        formatted_phone = format_phone_number(phone_number)
        if not formatted_phone.startswith("254") or len(formatted_phone) != 12:
            messages.error(request, "Invalid phone number.")
            return redirect("event_details", slug=event.slug)
        with transaction.atomic():
            try:
                for checkout_item in checkout_items:
                    ticket_type_id = checkout_item.get("id")
                    quantity_requested = checkout_item.get("quantity", 0)

                    ticket_type = TicketType.objects.select_for_update().get(
                        id=ticket_type_id, event=event
                    )
                    # Ensures user can't buy a ticket if there no tickets
                    if not ticket_type.has_available:
                        messages.error(
                            request,
                            f"Sorry there are no more tickets for: {ticket_type.name}",
                        )
                        return redirect("event_details", slug=slug)
                    # Ensures the user can't buy more tickets than are actually available
                    if ticket_type.get_available_count() < quantity_requested:
                        messages.error(
                            request,
                            f"Sorry, there are not enough tickets available for {ticket_type.name}.",
                        )
                        return redirect("event_details", slug=event.slug)

                # create a payment record in the database
                payment = Payment.objects.create(
                    user=request.user,
                    event=event,
                    amount=amount,
                    mpesa_number=formatted_phone,
                    is_agreed_to_terms=agreed_to_terms,
                    payment_status="Pending",
                    checkout_data_snapshot=checkout_data,
                )
            except Exception as stock_error:
                print(f"Database/Stock validation failed: {stock_error}")
                messages.error(
                    request,
                    "An error occurred while matching ticket availability. Please try again.",
                )
                return redirect("event_details", slug=event.slug)

            # initiate mpesa stk push
            try:
                data = {
                    "formatted_phone": formatted_phone,
                    "amount": amount,
                    "Event_id": event.id,
                    "Payment_id": payment.payment_id,
                }
                initiate_mpesa_stk_push_task.delay(data)
                check_payment_status_task.apply_async(
                    (payment.payment_id,), countdown=50
                )  # Check after 50 seconds
                return redirect("payment_waiting", payment_id=payment.payment_id)
            except Exception as e:
                print(f"Error initiating payment: {str(e)}")
                return redirect("event_details", slug=event.slug)
    return render(request, "payments/checkout.html", {"event": event})


# mpesa callback view
@csrf_exempt
def mpesa_callback(request):
    """
    Handle the M-PESA STK push callback.
    This view processes the callback from M-PESA after a payment attempt.
    then calls the celery worker to handle the updates of the payment status in the database and sends real-time updates via WebSocket.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            stk_json_path = os.path.join(
                settings.BASE_DIR, "mpesa_logs", "stk_callback.json"
            )
            with open(stk_json_path, "w") as f:
                json.dump(data, f, indent=4)
            process_mpesa_stk_callbacks.delay(data)
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON callback: {str(e)}")
        # Respond with a success acknowledgement expected by M-PESA
        return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})

    return JsonResponse({"Error": "Invalid request method"}, status=400)


# Withdrawal request view for event organizers
@login_required
@user_passes_test(lambda u: u.is_organiser, login_url="login")
def request_withdrawal(request):
    """
    Handles withdrawal requests for event organizers.
    Validates the organizer's available balance and M-PESA number, creates a withdrawal record,
    and initiates a B2C payment request to M-PESA.
    """
    try:
        user = request.user
        events = Event.objects.filter(Event_organiser=user)

        # Calculate total revenue from all organizer's events
        total_revenue = user.account_balance

        # Get mpesa number from first event that has one
        mpesa_number = None
        for event in events:
            if event.Event_mpesa_number:
                mpesa_number = event.Event_mpesa_number
                break

        print(
            f"mpesa_number {mpesa_number} - available_balance {total_revenue}"
        )  # Debugging log

        # Validate inputs
        if total_revenue <= 0 or not mpesa_number:
            messages.error(request, "Insufficient funds please try again !.")
            return redirect("organizers_dashboard")

        # Format phone number
        formatted_mpesa_number = format_phone_number(mpesa_number)
        with transaction.atomic():
            # Create withdrawal record
            withdrawal = Withdrawal.objects.create(
                organiser=request.user,
                amount=total_revenue,
                mpesa_number=formatted_mpesa_number,
                status="pending",
            )

            # Initiate B2C payment
            data = {
                "amount": total_revenue,
                "phone_number": formatted_mpesa_number,
                "withdrawal_id": withdrawal.withdrawal_id,
            }
            transaction.on_commit(lambda dt=data: initiate_b2c_request_task.delay(dt))
            return redirect("organizers_dashboard")

    except Exception as e:
        messages.error(request, "An unexpected error occurred. Please try again.")
        print(f"Unexpected error in withdrawal request: {str(e)}")
        return redirect("organizers_dashboard")


@csrf_exempt
def mpesa_b2c_callback(request):
    """
    Handle the M-PESA B2C callback.
    This view processes the callback from M-PESA after a B2C withdrawal attempt.
    calls the celery worket to update the withdrawal status in the database based on the result of the transaction.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            print(f"Error decoding B2C callback JSON: {e}")
            return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})

        b2c_callback_json_path = os.path.join(
            settings.BASE_DIR, "mpesa_logs", "b2c_callback.json"
        )
        with open(b2c_callback_json_path, "w") as f:
            json.dump(data, f, indent=4)
        logger.info(f"MPESA B2C Callback received: {data}")

        process_mpesa_b2c_callbacks.delay(data)
        # Acknowledge receipt to M-PESA
        return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})

    return JsonResponse({"Error": "Invalid request method"}, status=400)


@csrf_exempt
def mpesa_timeout_handler(request):
    """Handle the M-PESA B2C timeout callback.
    This view processes the timeout callback from M-PESA for B2C transactions.
    It updates the withdrawal status in the database to 'failed' due to timeout."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            print(f"Error decoding B2C timeout JSON: {e}")
            return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})

        originator_conversation_id = data.get("Result", {}).get(
            "OriginatorConversationID", "unknown"
        )
        b2c_timeout_json_path = os.path.join(
            settings.BASE_DIR, "mpesa_logs", "b2c_timeout.json"
        )
        with open(b2c_timeout_json_path, "w") as f:
            json.dump(data, f, indent=4)
        timeout_details = data.get("Result", {})
        transaction_id = timeout_details.get("TransactionID")
        result_desc = timeout_details.get("ResultDesc")
        try:
            withdrawal = Withdrawal.objects.get(
                originator_conversation_id=originator_conversation_id
            )
        except Withdrawal.DoesNotExist:
            print(
                f"Timeout callback transaction does not exist: {originator_conversation_id}"
            )
        else:
            withdrawal.status = "failed"
            withdrawal.reason = f"Timeout: {result_desc}"
            withdrawal.Transaction_id = transaction_id
            withdrawal.save()
            print(
                f"Withdrawal timed out: {withdrawal.withdrawal_id} - Reason: {result_desc}"
            )

        return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})

    return JsonResponse({"Error": "Invalid request method"}, status=400)


# render checkout page
def checkout(request, slug):
    """Render the checkout page for a specific event.
    Retrieves the event and checkout data from the session, and displays the checkout page with the event details and selected items.
    """
    event = get_object_or_404(Event, slug=slug)
    print(f"Event slug: {event.slug}")
    checkout_data = request.session.get("checkout_data")
    print(f"Check out data: {checkout_data}")

    if not checkout_data:
        messages.error(
            request, "You have not selected the amount of tickets you wish to buy!"
        )
        redirect("event_details")

    context = {
        "event": event,
        "items": checkout_data["items"],
        "grand_total": checkout_data["grand_total"],
    }

    return render(request, "payments/checkout.html", context)


def payment_waiting(request, payment_id):
    """Render the payment waiting page for a specific payment.
    This view retrieves the payment record based on the provided payment ID and displays the waiting page while the payment is being processed.
    """
    payment = get_object_or_404(Payment, payment_id=payment_id)
    context = {"payment": payment}
    return render(request, "payments/payment_waiting.html", context)
