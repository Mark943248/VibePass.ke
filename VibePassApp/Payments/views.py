from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from Events.models import Event
from django.contrib import messages
from django.http import JsonResponse
from .utilis import mpesa_stk_push
from .models import Payment
import json

# Create your views here.
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
            messages.success(request, 'Please enter your pin on your phone to complete the payment.')
            return render(request, 'Payments/payment_waiting.html', {'event': event})
        else:
            payment.payment_status = 'Failed'
            payment.save()
            error_msg = response.get('ResultDesc', 'Payment initiation failed. Please try again.')
            messages.error(request, f'MPESA Error: {error_msg}, please try again.')
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
                payment.mpesa_receipt_number = mpesa_info['CallbackMetadata']['Item'][2]['Value']  # Assuming the receipt number is at index 1
                payment.save()
                messages.success(request, 'Payment completed successfully.')
            else:
                payment.payment_status = 'Failed'
                payment.save()
                messages.error(request, f'Payment failed: {result_desc}')
        except Payment.DoesNotExist:
            messages.error(request, 'Payment record not found for the given checkout request ID.')
        # informing safaricom of success
        return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})
    
    return JsonResponse({"Error": "Invalid request method"}, status=400)
            


            

