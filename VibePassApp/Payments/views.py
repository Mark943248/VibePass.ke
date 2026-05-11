from django.shortcuts import render, redirect, get_object_or_404
from .signals import payment_successful
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.csrf import csrf_exempt
from Events.models import Event
from django.http import JsonResponse
from django.contrib import messages
from django.conf import settings
from .utils import mpesa_stk_push, format_phone_number, initiate_b2c_request
from .models import Payment, Withdrawal
from .consumers import send_payment_status_update
import json
import os

# Create your views here.
@login_required
def initiate_payment(request, slug):
    event = get_object_or_404(Event, slug=slug)
    amount = event.Event_ticket_price
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number', '').strip()
        if not phone_number:
            messages.error(request, 'Please enter a phone number.')
            return redirect('event_details', slug=event.slug)

        formatted_phone = format_phone_number(phone_number)
        if not formatted_phone.startswith('254') or len(formatted_phone) != 12:
            messages.error(request, 'Invalid phone number.')
            return redirect('event_details', slug=event.slug)

        # create a payment record in the database
        payment = Payment.objects.create(
            user=request.user,
            event=event,
            amount=amount,
            mpesa_number=formatted_phone,
            payment_status='Pending'
        )
        # initiate mpesa stk push
        try:
            response = mpesa_stk_push(formatted_phone, amount, event.Event_title, payment.payment_id)
            stk_json_path = os.path.join(settings.BASE_DIR, 'mpesa_logs', 'stk.json')
            with open(stk_json_path, 'w') as f:
                json.dump(response, f, indent=4)
            # handle the response from mpesa
            if response.get('ResponseCode') == '0':
                payment.checkout_request_id = response.get('CheckoutRequestID')
                payment.save()
                print(f'MPESA STK Push initiated successfully for payment ID {payment.payment_id}')
                return render(request, 'payments/payment_waiting.html', {'event': event, 'payment': payment})
            else:
                payment.payment_status = 'Failed'
                payment.save()
                error_msg = response.get('ResultDesc', 'Payment initiation failed. Please try again.')
                print(f'MPESA STK Push failed for payment ID {payment.payment_id}: {error_msg} {response}')
                return redirect('event_details', slug=event.slug)
        except Exception as e:
            print(f'Error initiating payment: {str(e)}')
            return redirect('event_details', slug=event.slug)
    return render(request, 'payments/checkout.html', {'event': event})


# Check payment status endpoint
@login_required
def check_payment_status(request, payment_id):
    """
    Check the current status of a payment
    Returns JSON with status and message
    """
    try:
        payment = Payment.objects.get(payment_id=payment_id, user=request.user)
        
        status = payment.payment_status
        message = ""
        
        if status == 'Completed':
            message = "Payment successful. Your ticket is being generated."
        elif status == 'Failed':
            message = "Payment failed. Please try again."
        elif status == 'Pending':
            message = "Payment is being processed..."
        
        return JsonResponse({
            'status': status,
            'message': message,
            'payment_id': str(payment.payment_id),
            'amount': str(payment.amount),
            'receipt_number': payment.mpesa_receipt_number or ''
        })
    except Payment.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Payment not found'
        }, status=404)


# mpesa callback view
@csrf_exempt
def mpesa_callback(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            stk_json_path = os.path.join(settings.BASE_DIR, 'mpesa_logs', 'stk_callback.json')
            with open(stk_json_path, 'w') as f:
                json.dump(data, f, indent=4)
            mpesa_info = data.get('Body', {}).get('stkCallback', {})
            checkout_request_id = mpesa_info.get('CheckoutRequestID')
            result_code = mpesa_info.get('ResultCode')
            result_desc = mpesa_info.get('ResultDesc', 'Unknown error')
            
            if not checkout_request_id:
                print('Error: No CheckoutRequestID in callback')
                return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})
            
            try:
                payment = Payment.objects.get(checkout_request_id=checkout_request_id)
                
                if result_code == 0:
                    # Payment successful
                    payment.payment_status = 'Completed'
                    items = mpesa_info.get('CallbackMetadata', {}).get('item', [])
                    for item in items:
                        if item.get('Name') == "MpesaReceiptNumber":
                            payment.mpesa_receipt_number = item.get('Value')
                    payment.save()
                    print(f'Payment successful payment_id : {payment.payment_id}')
                    payment_successful.send(sender=Payment, payment=payment)  # send signal when payment is successful
                    send_payment_status_update(payment)  # send WebSocket update
                else:
                    # Payment failed or cancelled 
                    payment.payment_status = 'Failed'
                    payment.save()
                    print(f'Payment failed for payment ID {payment.payment_id} (Result Code: {result_code}): {result_desc}')
                    send_payment_status_update(payment)  # send WebSocket update
            
            except Payment.DoesNotExist:
                print(f'Payment record not found for the given checkout request ID: {checkout_request_id}')
            
            # Always return success to M-PESA to acknowledge receipt
            return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})
        
        except json.JSONDecodeError as e:
            print(f'Error decoding JSON callback: {str(e)}')
            return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})
        except Exception as e:
            print(f'Error processing MPESA callback: {str(e)}')
            return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})
    
    return JsonResponse({"Error": "Invalid request method"}, status=400)


# Withdrawal request view for event organizers
@login_required
@user_passes_test(lambda u: u.is_organiser, login_url='login')
def request_withdrawal(request):
    try:
        user = request.user
        events = Event.objects.filter(Event_organiser=user)
        
        # Calculate total revenue from all organizer's events
        from django.db.models import Sum
        total_revenue = Payment.objects.filter(
            event__Event_organiser=user, 
            payment_status='Completed'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Get mpesa number from first event that has one
        mpesa_number = None
        for event in events:
            if event.Event_mpesa_number:
                mpesa_number = event.Event_mpesa_number
                break
        
        print(f"mpesa_number {mpesa_number} - amount {total_revenue}")
        
        # Validate inputs
        if not total_revenue or not mpesa_number:
            messages.error(request, 'Insufficient funds please try again !.')
            return redirect('organizers_dashboard') 
        
        # Format phone number
        formatted_mpesa_number = format_phone_number(mpesa_number)
        
        # Create withdrawal record
        withdrawal = Withdrawal.objects.create(
            organizer=request.user,
            amount=total_revenue,
            mpesa_number=formatted_mpesa_number,
            status='pending'
        )
        
        # Initiate B2C payment
        try:
            response = initiate_b2c_request(
                amount=total_revenue,
                phone_number=formatted_mpesa_number,
            )

            b2c_json_path = os.path.join(settings.BASE_DIR, 'mpesa_logs', 'b2c.json')
            with open(b2c_json_path, 'w') as f:
                json.dump(response, f, indent=4)

            # Handle M-Pesa B2C response
            if response.get('ResponseCode') == '0':
                withdrawal.status = 'processing'
                withdrawal.originator_conversation_id = response.get('OriginatorConversationID')
                withdrawal.mpesa_conversation_id = response.get('ConversationID')
                withdrawal.save()
                messages.success(request, f'Withdrawal of KES {total_revenue} initiated successfully!')
                print(f'B2C withdrawal initiated successfully for {user.username}: Withdrawal ID {withdrawal.withdrawal_id}')
            else:
                withdrawal.status = 'failed'
                withdrawal.reason = response.get('ResponseDescription', 'B2C request failed')
                withdrawal.save()
                error_msg = response.get('ResponseDescription', 'Withdrawal initiation failed. Please try again.')
                messages.error(request, error_msg)
                print(f'B2C withdrawal failed for {user.username}: {error_msg}')
        
        except Exception as e:
            withdrawal.status = 'failed'
            withdrawal.reason = str(e)
            withdrawal.save()
            error_msg = str(e)
            messages.error(request, 'Error initiating withdrawal. Please try again.')
            print(f'Error initiating B2C withdrawal for {user.username}: {error_msg}')
        
        return redirect('organizers_dashboard')
    
    except Exception as e:
        messages.error(request, 'An unexpected error occurred. Please try again.')
        print(f'Unexpected error in withdrawal request: {str(e)}')
        return redirect('organizers_dashboard')

@csrf_exempt
def mpesa_b2c_callback(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            print(f'Error decoding B2C callback JSON: {e}')
            return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})

        originator_conversation_id = data.get("Result", {}).get("OriginatorConversationID", "unknown")
        b2c_callback_json_path = os.path.join(settings.BASE_DIR, 'mpesa_logs', 'b2c_callback.json')
        with open(b2c_callback_json_path, 'w') as f:
            json.dump(data, f, indent=4)
        print(f'MPESA B2C Callback received: {data}')
        mpesa_details = data.get("Result", {})
        Result_code = mpesa_details.get("ResultCode")
        originator_conversation_id = mpesa_details.get("OriginatorConversationID")
        transaction_id = mpesa_details.get("TransactionID")
        Result_desc = mpesa_details.get("ResultDesc")
        try:
            withdrawals = Withdrawal.objects.filter(originator_conversation_id=originator_conversation_id)
            if not withdrawals.exists():
                print(f'Transaction does not exist: {originator_conversation_id}')
            else:
                if Result_code == 0:
                    for withdrawal in withdrawals:
                        withdrawal.status = 'completed'
                        withdrawal.mpesa_receipt_number = transaction_id
                        withdrawal.save()
                        print(f'Withdrawal completed successfully: {withdrawal.withdrawal_id}')
                else:
                    for withdrawal in withdrawals:
                        withdrawal.status = 'failed'
                        withdrawal.reason = Result_desc
                        withdrawal.save()
                        print(f'Withdrawal failed: {withdrawal.withdrawal_id} - Reason: {Result_desc}')

        except Exception as e:
            print(f'Error processing B2C callback for {originator_conversation_id}: {e}')
        
        return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})
    
    return JsonResponse({"Error": "Invalid request method"}, status=400)

@csrf_exempt
def mpesa_timeout_handler(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            print(f'Error decoding B2C timeout JSON: {e}')
            return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})

        originator_conversation_id = data.get('Result', {}).get('OriginatorConversationID', 'unknown')
        b2c_timeout_json_path = os.path.join(settings.BASE_DIR, 'mpesa_logs', 'b2c_timeout.json')
        with open(b2c_timeout_json_path, 'w') as f:
            json.dump(data, f, indent=4)
        timeout_details = data.get('Result', {})
        transaction_id = timeout_details.get('TransactionID')
        result_desc = timeout_details.get('ResultDesc')
        withdrawals = Withdrawal.objects.filter(originator_conversation_id=originator_conversation_id)
        if not withdrawals.exists():
            print(f'Timeout callback transaction does not exist: {originator_conversation_id}')
        else:
            for withdrawal in withdrawals:
                withdrawal.status = 'failed'
                withdrawal.reason = f'Timeout: {result_desc}'
                withdrawal.Transaction_id = transaction_id
                withdrawal.save()
                print(f'Withdrawal timed out: {withdrawal.withdrawal_id} - Reason: {result_desc}')
    

        return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})
    
    return JsonResponse({"Error": "Invalid request method"}, status=400)


