import os
import json
import base64
import logging
import requests
from celery import shared_task
from decouple import config
from .signals import payment_successful
from django.shortcuts import redirect
from Events.models import Event
from django.conf import settings
from .models import Payment, Withdrawal
from .utils import generate_access_token, generate_timestamp, calculate_user_account_balance
from .consumers import send_payment_status_update, update_dashboard_balance_after_withdraw

logger = logging.getLogger(__name__)

@shared_task()
def initiate_mpesa_stk_push_task(data):
   """Perform an M-Pesa STK Push request and return a JSON-serializable response."""
   event = Event.objects.get(id=data['Event_id'])
   formatted_phone = data['formatted_phone']
   access_token = generate_access_token()
   if not access_token:
      raise Exception('Failed to obtain access token')

   timestamp = generate_timestamp()
   short_code = os.getenv('MPESA_SHORT_CODE')
   passkey = os.getenv('MPESA_PASSKEY')
   data_to_encode = f"{short_code}{passkey}{timestamp}"
   online_password = base64.b64encode(data_to_encode.encode()).decode()
   callback_base = config('MPESA_CALLBACK_URL')
   callback_url = callback_base.rstrip('/')
   if not callback_url.endswith('/payments/mpesa_callback'):
       callback_url = f"{callback_url}/payments/mpesa_callback"

   payload = {
       "BusinessShortCode": short_code,
       "Password": online_password,
       "Timestamp": timestamp,
       "TransactionType": "CustomerPayBillOnline",
       "Amount": int(data['amount']),
       "PartyA": formatted_phone,
       "PartyB": short_code,
       "PhoneNumber": formatted_phone,
       "CallBackURL": callback_url,
       "AccountReference": f"Purchase of {event.Event_title} ticket - {data['Payment_id']}",
       "TransactionDesc": "Event Ticket Purchase"
   }
   headers = {"Authorization": f"Bearer {access_token}"}
   stk_push_url = 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest'

   try:
      response = requests.post(stk_push_url, json=payload, headers=headers, timeout=10)
      response.raise_for_status()
      stk_json_path = os.path.join(settings.BASE_DIR, 'mpesa_logs', 'stk.json')
      with open(stk_json_path, 'w') as f:
          json.dump(response.json(), f, indent=4)
      payment = Payment.objects.get(payment_id=data['Payment_id'])
      if response.json().get('ResponseCode') == '0':
          payment.checkout_request_id = response.json().get('CheckoutRequestID')
          payment.save(update_fields=['checkout_request_id']) 
          logger.info(f"STK Push initiated successfully for payment_id: {payment.payment_id}")
      else:
          payment.payment_status = 'Failed'
          payment.save(update_fields=['payment_status'])
          logger.error(f"STK Push failed for payment_id: {payment.payment_id} - Error: {response.json().get('ResultDesc', 'Error in stk push')}")
   except requests.exceptions.Timeout as exc:
      logger.warning("Timeout error from mpesa stk!", exc_info=exc)
   except requests.exceptions.RequestException as exc:
      logger.error("Error sending mpesa stk push", exc_info=exc)


@shared_task()
def process_mpesa_stk_callbacks(data):
    """
    This view processes M-Pesa STK callbacks via a Celery worker.
    """

    mpesa_info = data.get('Body', {}).get('stkCallback', {})
    checkout_request_id = mpesa_info.get('CheckoutRequestID')
    result_code = mpesa_info.get('ResultCode')
    result_desc = mpesa_info.get('ResultDesc', 'Unknown error')

    if not checkout_request_id:
        logger.error("No checkout_request_id in callback")
        return None

    try:
        payment = Payment.objects.get(checkout_request_id=checkout_request_id)
    except Payment.DoesNotExist:
        logger.error(f"Payment not found with checkout_request_id: {checkout_request_id}")
        return None

    try:
        result_code = int(result_code)
    except (TypeError, ValueError):
        logger.warning(
            f"Unexpected ResultCode type for payment {payment.payment_id}: {result_code}"
        )
        result_code = -1

    if result_code == 0:
        payment.payment_status = 'Completed'
        items = mpesa_info.get('CallbackMetadata', {}).get('Item', [])
        receipt_number = None
        for item in items:
            if item.get('Name') == 'MpesaReceiptNumber':
                receipt_number = item.get('Value')
                break

        if receipt_number:
            payment.mpesa_receipt_number = receipt_number
        payment.save()
        logger.info(f"Payment successful for payment_id: {payment.payment_id}")
        payment_successful.send(sender=Payment, payment=payment)
        send_payment_status_update(payment)
    else:
        payment.payment_status = 'Failed'
        payment.save()
        logger.info(
            f'Payment failed for payment ID {payment.payment_id} (Result Code: {result_code}): {result_desc}'
        )
        send_payment_status_update(payment)




@shared_task()
def process_mpesa_b2c_callbacks(data):
    """
    Processes M-Pesa B2C (Business to Customer) withdrawal callback payloads 
    asynchronously to update transaction status and adjust balance records.
    """

    originator_conversation_id = data.get("Result", {}).get("OriginatorConversationID", "unknown")
    mpesa_details = data.get("Result", {})
    Result_code = mpesa_details.get("ResultCode")
    originator_conversation_id = mpesa_details.get("OriginatorConversationID")
    transaction_id = mpesa_details.get("TransactionID")
    Result_desc = mpesa_details.get("ResultDesc")

    try:
        withdrawal = Withdrawal.objects.get(originator_conversation_id=originator_conversation_id)
        
        if Result_code == 0:
            withdrawal.status = 'completed'
            withdrawal.mpesa_receipt_number = transaction_id
            withdrawal.save()
            logger.info(f'Withdrawal completed successfully: {withdrawal.withdrawal_id}')
            new_balance = calculate_user_account_balance(withdrawal.organiser)
            update_dashboard_balance_after_withdraw(withdrawal)
            logger.info(f"Users account balance after deduction: {new_balance}")
        else:
            withdrawal.status = 'failed'
            withdrawal.reason = Result_desc
            withdrawal.save()
            logger.error(f'Withdrawal failed: {withdrawal.withdrawal_id} - Reason: {Result_desc}')

    except Withdrawal.DoesNotExist:
        logger.error(f'Transaction does not exist: {originator_conversation_id}')
       

