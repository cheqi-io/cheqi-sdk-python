"""Shared test fixtures."""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


@pytest.fixture
def rsa_key_pair() -> tuple[str, str]:
    """Generate an RSA-2048 key pair and return (private_key_b64, public_key_b64)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Export private key as Base64-encoded PKCS#8 DER
    private_der = private_key.private_bytes(
        encoding=Encoding.DER,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )
    private_b64 = base64.b64encode(private_der).decode("ascii")

    # Export public key as Base64-encoded DER
    public_key = private_key.public_key()
    public_der = public_key.public_bytes(
        encoding=Encoding.DER,
        format=PublicFormat.SubjectPublicKeyInfo,
    )
    public_b64 = base64.b64encode(public_der).decode("ascii")

    return private_b64, public_b64
