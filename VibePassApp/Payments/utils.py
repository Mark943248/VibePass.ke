import base64
import json
import os
import requests
import logging
import uuid
from datetime import datetime
from pathlib import Path
from decouple import config
from .models import Payment, Withdrawal
from django.db.models import Sum
from decimal import Decimal
from django.conf import settings
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

logger = logging.getLogger(__name__)


# generate timestamp for mpesa
def generate_timestamp():
    """Generate a timestamp in the format YYYYMMDDHHMMSS for M-Pesa transactions."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return timestamp


# generate access token for mpesa
def generate_access_token():
    """
    Generate an access token for M-Pesa API authentication using consumer key and secret.
    This function retrieves the consumer key and secret from environment variables,
    makes a request to the M-Pesa OAuth endpoint, and returns the access token if successful.
    Raises an exception if the token generation fails.
    """
    consumer_key = os.getenv("MPESA_CONSUMER_KEY")
    consumer_secret = os.getenv("MPESA_CONSUMER_SECRET")
    if not consumer_key or not consumer_secret:
        raise Exception(
            "M-Pesa consumer key or secret not set in environment variables"
        )
    api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(api_url, auth=(consumer_key, consumer_secret))
    if response.status_code == 200:
        access_token = response.json().get("access_token")
        return access_token
    else:
        raise Exception("Failed to generate access token")


# format phone number to international format for MPESA
def format_phone_number(phone_number):
    """Format a phone number to the international format required by M-Pesa API."""
    # Remove any non-digit characters
    cleaned = "".join(filter(str.isdigit, phone_number))
    if cleaned.startswith("0"):
        return "254" + cleaned[1:]
    elif cleaned.startswith("254"):
        return cleaned
    elif cleaned.startswith("+254"):
        return cleaned[1:]
    else:
        return cleaned


def calculate_user_account_balance(user):
    """Calculate the organizer's current withdrawable balance from completed payments minus completed withdrawals."""
    total_revenue = Payment.objects.filter(
        event__Event_organiser=user, payment_status="Completed"
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    total_withdrawn = Withdrawal.objects.filter(
        organiser=user, status="completed"
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    balance = total_revenue - total_withdrawn
    user.account_balance = balance
    user.save(update_fields=["account_balance"])
    return balance


# calculates 10% for the platform
def calculate_net_earnings(amount):
    """Calculates the net amount remaining after deducting a platform fee."""

    if amount < 0:
        raise ValueError("Amount can't be 0!")

    fee_amount = (10.0 / 100) * amount
    net_amount = amount - fee_amount

    return round(net_amount, 2)


# mpesa security credential generation
def generate_mpesa_security_credential():
    """Generate the M-Pesa security credential by encrypting the initiator password using the public key from the certificate.
    This function reads the public key from the specified certificate file, encrypts the initiator password, and returns the base64-encoded security credential.
    """
    initiator_password = os.getenv("MPESA_INITIATOR_PASSWORD")
    cert_path = os.path.join(settings.BASE_DIR, "Certs", "SandboxCertificate.cer")
    with open(cert_path, "rb") as f:
        cert_data = f.read()
    public_key = RSA.importKey(cert_data)
    cipher = PKCS1_v1_5.new(public_key)
    encrypted_password = cipher.encrypt(initiator_password.encode())
    security_credential = base64.b64encode(encrypted_password).decode()
    print(
        "Generated MPESA Security Credential:", security_credential
    )  # Debugging statement
    return security_credential
