import base64
import requests
from datetime import datetime
from decouple import config
from django.conf import settings


# generate timestamp for mpesa
def generate_timestamp():
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return timestamp

# generate access token for mpesa
def generate_access_token():
    consumer_key = config('MPESA_CONSUMER_KEY')
    consumer_secret = config('MPESA_CONSUMER_SECRET')
    api_url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    response = requests.get(api_url, auth=(consumer_key, consumer_secret))
    if response.status_code == 200:
        access_token = response.json().get('access_token')
        return access_token
    else:
        raise Exception('Failed to generate access token')
    
# mpesa stk_push request
def mpesa_stk_push(phone_number, amount, payment_reference):
   access_token = generate_access_token()
   if not access_token:
         raise Exception('Failed to obtain access token')
   timestamp = generate_timestamp()
   short_code = config('MPESA_SHORT_CODE')
   passkey = config('MPESA_PASSKEY')
   data_to_encode = f"{short_code}{passkey}{timestamp}"
   # password for mpesa is a base64 encoded string of the short code, passkey and timestamp
   online_password = base64.b64encode(data_to_encode.encode()).decode()
   payload = {
       "BusinessShortCode": short_code,
        "Password": online_password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone_number,
        "PartyB": short_code,
        "PhoneNumber": phone_number,
        "CallBackURL": config('MPESA_CALLBACK_URL'), # Your 'Back Door' URL
        "AccountReference": f"REF-{payment_reference}",
        "TransactionDesc": "Event Ticket Purchase"
   }
   headers = {"Authorization": f"Bearer {access_token}"}
   stk_push_url = 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
   response = requests.post(stk_push_url, json=payload, headers=headers)
    
   return response.json()

   
