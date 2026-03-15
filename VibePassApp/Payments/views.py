from django.shortcuts import render, redirect, get_object_or_404
from Tickets.views import create_ticket
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from Events.models import Event
from django.contrib import messages
from django.http import JsonResponse
from .utilis import mpesa_stk_push
from .models import Payment
import json

# Create your views here.
@login_required
def initiate_payment(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number')
        amount = request.POST.get('amount')
    # create a payment record in the database
        payment = Payment.objects.create(
            user=request.user,
            event=event,
            amount=amount,
            mpesa_number=phone_number,
            payment_status='Pending'
        )
        # initiate mpesa stk push
        response = mpesa_stk_push(phone_number, amount, event.Event_title, payment.payment_id)
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
            print(f'MPESA STK Push failed for payment ID {payment.payment_id}: {error_msg}')
            return redirect('Eventdetails')
    return render(request, 'Payments/initiate_payment.html', {'event': event})


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
                return create_ticket(payment.id)
            else:
                payment.payment_status = 'Failed'
                payment.save()
                print(f'Payment failed for payment ID {payment.payment_id}: {result_desc}')
        except Payment.DoesNotExist:
            print(f'Payment record not found for the given checkout request ID: {checkout_request_id}')
        # informing safaricom of success
        return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})
    
    return JsonResponse({"Error": "Invalid request method"}, status=400)
            


            

