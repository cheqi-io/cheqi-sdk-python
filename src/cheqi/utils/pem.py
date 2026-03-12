"""PEM and key parsing utilities."""

from __future__ import annotations

import base64
import re

from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_der_private_key,
    load_der_public_key,
    load_pem_private_key,
    load_pem_public_key,
)
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey


_PEM_HEADER_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]+-----\s*|-----END [A-Z0-9 ]+-----\s*"
)


def decode_key_bytes(key_data: str) -> bytes:
    """Decode a key from PEM or raw Base64 format to DER bytes.

    Strips PEM headers/footers if present and Base64-decodes the content.
    """
    # Strip PEM headers/footers
    stripped = _PEM_HEADER_RE.sub("", key_data).strip()
    # Remove any whitespace/newlines
    stripped = re.sub(r"\s+", "", stripped)
    return base64.b64decode(stripped)


def parse_public_key(key_data: str) -> RSAPublicKey:
    """Parse an RSA public key from PEM or Base64-encoded DER format."""
    if "-----BEGIN" in key_data:
        key = load_pem_public_key(key_data.encode("utf-8"))
    else:
        der_bytes = decode_key_bytes(key_data)
        key = load_der_public_key(der_bytes)

    if not isinstance(key, RSAPublicKey):
        raise ValueError("Expected RSA public key")
    return key


def parse_private_key(key_data: str) -> RSAPrivateKey:
    """Parse an RSA private key from PEM or Base64-encoded PKCS#8 format."""
    if "-----BEGIN" in key_data:
        key = load_pem_private_key(key_data.encode("utf-8"), password=None)
    else:
        der_bytes = decode_key_bytes(key_data)
        key = load_der_private_key(der_bytes, password=None)

    if not isinstance(key, RSAPrivateKey):
        raise ValueError("Expected RSA private key")
    return key
