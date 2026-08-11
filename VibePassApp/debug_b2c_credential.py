#!/usr/bin/env python
"""
Debug script to test M-Pesa B2C credential generation and certificate validity
"""

import os
import sys
import base64
import django
from datetime import datetime
from pathlib import Path

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "VibePassApp.settings")
django.setup()

from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from django.conf import settings
from decouple import config


def test_certificate():
    """Test certificate loading and validity"""
    print("=" * 60)
    print("CERTIFICATE VALIDATION")
    print("=" * 60)

    cert_path = os.path.join(settings.BASE_DIR, "Certs", "SandboxCertificate.cer")
    print(f"\n Certificate path: {cert_path}")

    # Check if certificate exists
    if not os.path.exists(cert_path):
        print(" Certificate file NOT FOUND")
        return False

    print(" Certificate file exists")

    try:
        with open(cert_path, "rb") as f:
            cert_data = f.read()

        file_size = len(cert_data)
        print(f" Certificate size: {file_size} bytes")

        # Check certificate format
        if b"-----BEGIN" in cert_data:
            print(" Certificate format: PEM format detected")
        elif b"\x30\x82" in cert_data:
            print(" Certificate format: DER format detected")
        else:
            print(" Certificate format: Unknown format (might still be valid)")

        # Try to load the certificate
        public_key = RSA.importKey(cert_data)
        print(f" Certificate loaded successfully")
        print(f"  - Key size: {public_key.n.bit_length()} bits")
        print(f"  - Has public exponent: {public_key.e is not None}")

        return True

    except Exception as e:
        print(f" Error loading certificate: {str(e)}")
        return False


def test_credential_generation():
    """Test security credential generation"""
    print("\n" + "=" * 60)
    print("SECURITY CREDENTIAL GENERATION TEST")
    print("=" * 60)

    try:
        # Get credentials from environment
        initiator_password = os.getenv("MPESA_INITIATOR_PASSWORD")
        initiator_name = os.getenv("MPESA_INITIATOR_NAME")

        print(f"\n Initiator Name: {initiator_name}")
        print(
            f" Initiator Password: {'*' * len(initiator_password) if initiator_password else 'NOT SET'}"
        )

        if not initiator_password or not initiator_name:
            print(" Missing required credentials in environment")
            return False

        # Load certificate
        cert_path = os.path.join(settings.BASE_DIR, "Certs", "SandboxCertificate.cer")
        with open(cert_path, "rb") as f:
            cert_data = f.read()

        # Generate credential
        public_key = RSA.importKey(cert_data)
        cipher = PKCS1_v1_5.new(public_key)

        print(f"\n Encrypting password with RSA public key...")
        encrypted_password = cipher.encrypt(initiator_password.encode())

        if encrypted_password:
            print(f" Password encrypted successfully ({len(encrypted_password)} bytes)")
        else:
            print(" Encryption returned None or empty result")
            return False

        # Base64 encode
        security_credential = base64.b64encode(encrypted_password).decode()

        print(f"\n Security Credential Generated (base64 encoded)")
        print(f"  - Credential length: {len(security_credential)} characters")
        print(f"  - First 50 chars: {security_credential[:50]}...")
        print(f"  - Last 50 chars: ...{security_credential[-50:]}")

        # Check if it looks valid
        if (
            len(security_credential) > 100
            and security_credential.replace("=", "")
            .replace("/", "")
            .replace("+", "")
            .isalnum()
        ):
            print(f" Credential format looks valid (base64)")
            return True
        else:
            print(f" Credential format might be invalid")
            return False

    except Exception as e:
        print(f" Error generating credential: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


def test_mpesa_credentials():
    """Test M-Pesa API credentials"""
    print("\n" + "=" * 60)
    print("M-PESA API CREDENTIALS CHECK")
    print("=" * 60)

    consumer_key = os.getenv("MPESA_CONSUMER_KEY")
    consumer_secret = os.getenv("MPESA_CONSUMER_SECRET")
    short_code_b2c = os.getenv("MPESA_B2C_SHORT_CODE")

    print(
        f"\n Consumer Key: {consumer_key[:10]}...{consumer_key[-10:] if consumer_key else 'NOT SET'}"
    )
    print(
        f" Consumer Secret: {consumer_secret[:10]}...{consumer_secret[-10:] if consumer_secret else 'NOT SET'}"
    )
    print(f" B2C Short Code: {short_code_b2c}")

    if not all([consumer_key, consumer_secret, short_code_b2c]):
        print("\n Missing required M-Pesa credentials")
        return False

    print("\n All M-Pesa credentials are set")
    return True


def test_access_token():
    """Test access token generation"""
    print("\n" + "=" * 60)
    print("ACCESS TOKEN GENERATION TEST")
    print("=" * 60)

    try:
        import requests
        from Payments.utils import generate_access_token

        print("\nAttempting to generate access token...")
        access_token = generate_access_token()

        if access_token:
            print(f" Access token generated successfully")
            print(f"  - Token length: {len(access_token)} characters")
            print(f"  - Token type: Bearer token")
            return True
        else:
            print(" Failed to generate access token (returned None)")
            return False

    except Exception as e:
        print(f" Error generating access token: {str(e)}")
        return False


def main():
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print("║" + "  M-PESA B2C CREDENTIAL DEBUGGING SCRIPT".center(58) + "║")
    print(
        "║"
        + f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(58)
        + "║"
    )
    print("║" + " " * 58 + "║")
    print("╚" + "=" * 58 + "╝")

    results = {}

    # Run all tests
    results["Certificate"] = test_certificate()
    results["Credentials"] = test_credential_generation()
    results["MPESA_API"] = test_mpesa_credentials()
    results["AccessToken"] = test_access_token()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for test_name, result in results.items():
        status = "PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    total_pass = sum(1 for r in results.values() if r)
    total_tests = len(results)

    print(f"\nTotal: {total_pass}/{total_tests} tests passed")

    if total_pass == total_tests:
        print("\n All checks passed! Your B2C setup looks good.")
    else:
        print("\n Some checks failed. Review the errors above.")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
