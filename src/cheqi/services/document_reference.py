"""Issuer document routing metadata; private receiving keys stay inside ciphertext."""

import base64
import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from cheqi.models.generated.receipt_envelope import ReceiptEnvelope
from cheqi.models.generated.receipt_envelope_document import ReceiptEnvelopeDocument


def document_reference_hash(document_number: str) -> str:
    if not isinstance(document_number, str) or not document_number.strip():
        raise ValueError("documentNumber is required")
    return hashlib.sha256(("cheqi:issuer-document:v1:" + document_number).encode("utf-8")).hexdigest()


def add_download_recipient(envelope: ReceiptEnvelope) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    envelope.documents["DOWNLOAD_RECIPIENT_KEY"] = ReceiptEnvelopeDocument(
        media_type="application/json",
        content=json.dumps({"algorithm": "RSA-OAEP-256", "privateKey": base64.b64encode(private).decode("ascii")}),
    )
    return base64.b64encode(
        key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    ).decode("ascii")
