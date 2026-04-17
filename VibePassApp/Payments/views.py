from django.shortcuts import render, redirect, get_object_or_404
from .signals import payment_successful
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from Events.models import Event
from django.http import JsonResponse
from .utils import mpesa_stk_push, format_phone_number
from .models import Payment
import json

# Create your views here.
@login_required
def initiate_payment(request, slug):
    event = get_object_or_404(Event, slug=slug)
    amount = event.Event_ticket_price
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number')
        formatted_phone = format_phone_number(phone_number)
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
            # handle the response from mpesa
            if response.get('ResponseCode') == '0':
                payment.checkout_request_id = response.get('CheckoutRequestID')
                payment.save()
                print(f'MPESA STK Push initiated successfully for payment ID {payment.payment_id}')
                return render(request, 'Payments/payment_waiting.html', {'event': event})
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


# mpesa callback view
@csrf_exempt
def mpesa_callback(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        mpesa_info = data['Body']['stkCallback']
        checkout_request_id = mpesa_info['CheckoutRequestID']
        result_code = mpesa_info['ResultCode']
        result_desc = mpesa_info['ResultDesc']
        try:
            payment = Payment.objects.get(checkout_request_id=checkout_request_id)
            if result_code == 0:
                payment.payment_status = 'Completed'
                items = mpesa_info['CallbackMetadata']['item']
                for item in items:
                    if item['Name'] == "MpesaReceiptNumber":
                        payment.mpesa_receipt_number = item['Value']
                payment.save()
                print(f'Payment succesful payment_id : {payment.id}')
                payment_successful.send(sender=Payment, payment=payment)  # send signal when payment is successful
            else:
                payment.payment_status = 'Failed'
                payment.save()
                print(f'Payment failed for payment ID {payment.payment_id}: {result_desc}')
        except Payment.DoesNotExist:
            print(f'Payment record not found for the given checkout request ID: {checkout_request_id}')
        # informing safaricom of success
        return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})
    
    return JsonResponse({"Error": "Invalid request method"}, status=400)