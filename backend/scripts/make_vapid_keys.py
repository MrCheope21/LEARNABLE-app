"""Prints a new key pair for push notifications, as lines for the server's .env file.

    python scripts/make_vapid_keys.py

Keep the private key secret. Changing the keys later unsubscribes every browser.
"""

import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


vapid = Vapid02()
vapid.generate_keys()
private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
public = vapid.public_key.public_bytes(
    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
)
print(f"PUSH_VAPID_PUBLIC_KEY={_b64(public)}")
print(f"PUSH_VAPID_PRIVATE_KEY={_b64(private)}")
print("PUSH_CONTACT=mailto:you@example.com   # your address, for the push services")
