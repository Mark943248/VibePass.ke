import base64
import requests
from datetime import datetime
from decouple import config
from django.conf import settings
import os


# generate timestamp for mpesa
def generate_timestamp():
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return timestamp

# generate access token for mpesa
def generate_access_token():
    consumer_key = os.getenv('MPESA_CONSUMER_KEY')
    consumer_secret = os.getenv('MPESA_CONSUMER_SECRET')
    api_url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    response = requests.get(api_url, auth=(consumer_key, consumer_secret))
    if response.status_code == 200:
        access_token = response.json().get('access_token')
        return access_token
    else:
        raise Exception('Failed to generate access token')
    
# format phone number to international format for MPESA
def format_phone_number(phone_number):
    # Remove any non-digit characters
    cleaned = ''.join(filter(str.isdigit, phone_number))
    if cleaned.startswith('0'):
        return '254' + cleaned[1:]
    elif cleaned.startswith('254'):
        return cleaned
    elif cleaned.startswith('+254'):
        return cleaned[1:]
    else:
        return cleaned
    
# mpesa stk_push request
def mpesa_stk_push(phone_number, amount, Event_title, payment_id):
   # Format phone number to international format
   formatted_phone = format_phone_number(phone_number)
   access_token = generate_access_token()
   if not access_token:
         raise Exception('Failed to obtain access token')
   timestamp = generate_timestamp()
   short_code = os.getenv('MPESA_SHORT_CODE')
   passkey = os.getenv('MPESA_PASSKEY')
   data_to_encode = f"{short_code}{passkey}{timestamp}"
   # password for mpesa is a base64 encoded string of the short code, passkey and timestamp
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
       "Amount": int(amount),
       "PartyA": formatted_phone,
       "PartyB": short_code,
       "PhoneNumber": formatted_phone,
       "CallBackURL": callback_url,
       "AccountReference": f"Purchase of {Event_title} ticket - {payment_id}",
       "TransactionDesc": "Event Ticket Purchase"
   }
   headers = {"Authorization": f"Bearer {access_token}"}
   stk_push_url = 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
   response = requests.post(stk_push_url, json=payload, headers=headers)
    
   return response.json()

   
