#!/usr/bin/env python3
"""
Generate VAPID key pair for Web Push notifications.
Run once and add the output to your .env file.

Usage:
    pip install pywebpush
    python scripts/generate_vapid.py
"""
from py_vapid import Vapid

vapid = Vapid()
vapid.generate_keys()

private_key = vapid.private_key  # type: ignore
public_key = vapid.public_key    # type: ignore

# Serialize
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat
)
import base64

private_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()).decode()
public_der  = public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
public_b64  = base64.urlsafe_b64encode(public_der).rstrip(b"=").decode()

print("=" * 60)
print("Add these to your .env file:")
print("=" * 60)
print(f"\nVAPID_PRIVATE_KEY={private_pem.strip()}")
print(f"VAPID_PUBLIC_KEY={public_b64}")
print("\nAdd to your frontend .env.local:")
print(f"NEXT_PUBLIC_VAPID_PUBLIC_KEY={public_b64}")
print("=" * 60)
