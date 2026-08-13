"""Decrypt complete recipient envelopes and customer return requests."""

from __future__ import annotations

import base64
from typing import Union

from cryptography.hazmat.primitives.asymmetric.padding import MGF1, OAEP
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256

from cheqi.exceptions import DecryptionError
from cheqi.models.credit_note import CreditNoteInitiationRequest
from cheqi.models.generated.encrypted_credit_note_initiation_request import (
    EncryptedCreditNoteInitiationRequest,
)
from cheqi.models.generated.encrypted_credit_note_initiation_request_response import (
    EncryptedCreditNoteInitiationRequestResponse,
)
from cheqi.models.generated.encrypted_receipt_delivery_response import EncryptedReceiptDeliveryResponse
from cheqi.models.generated.receipt_envelope import ReceiptEnvelope
from cheqi.models.generated.webhook_credit_note_initiation_request import (
    WebhookCreditNoteInitiationRequest,
)
from cheqi.models.generated.webhook_receipt_envelope import WebhookReceiptEnvelope
from cheqi.utils.pem import parse_private_key

_AES_KEY_LENGTH = 32
_GCM_IV_LENGTH = 12
_GCM_TAG_LENGTH = 16

ReceiptDelivery = Union[EncryptedReceiptDeliveryResponse, WebhookReceiptEnvelope]
CreditNoteInitiationDelivery = Union[
    EncryptedCreditNoteInitiationRequest,
    EncryptedCreditNoteInitiationRequestResponse,
    WebhookCreditNoteInitiationRequest,
]


class DecryptionService:
    """Decrypt AES-256-GCM content keys wrapped with RSA-OAEP SHA-256."""

    def decrypt_receipt(
        self,
        delivery: ReceiptDelivery,
        private_key_b64: str,
    ) -> ReceiptEnvelope:
        if delivery is None:
            raise ValueError("delivery cannot be None")
        plaintext = self._decrypt_payload(
            delivery.encrypted_envelope,
            delivery.encrypted_envelope_key,
            private_key_b64,
            "receipt envelope",
        )
        try:
            return ReceiptEnvelope.model_validate_json(plaintext)
        except Exception as exc:
            raise DecryptionError("Failed to deserialize receipt envelope") from exc

    def decrypt_credit_note_initiation(
        self,
        delivery: CreditNoteInitiationDelivery,
        private_key_b64: str,
    ) -> str:
        if delivery is None:
            raise ValueError("delivery cannot be None")
        return self._decrypt_payload(
            delivery.encrypted_credit_note_initiation_request,
            delivery.encrypted_symmetric_key,
            private_key_b64,
            "credit-note initiation request",
        )

    def decrypt_credit_note_initiation_request(
        self,
        delivery: CreditNoteInitiationDelivery,
        private_key_b64: str,
    ) -> CreditNoteInitiationRequest:
        """Decrypt, deserialize, and validate a customer return request."""
        plaintext = self.decrypt_credit_note_initiation(delivery, private_key_b64)
        try:
            return CreditNoteInitiationRequest.model_validate_json(plaintext)
        except Exception as exc:
            raise DecryptionError("Failed to deserialize credit-note initiation request") from exc

    def _decrypt_payload(
        self,
        encrypted_content: str | None,
        encrypted_key: str | None,
        private_key_b64: str,
        description: str,
    ) -> str:
        if not encrypted_content or not encrypted_content.strip():
            raise ValueError(f"encrypted {description} cannot be empty")
        if not encrypted_key or not encrypted_key.strip():
            raise ValueError(f"encrypted key for {description} cannot be empty")
        try:
            aes_key = self._rsa_decrypt_key(encrypted_key, private_key_b64)
            return self._aes_decrypt(encrypted_content, aes_key)
        except DecryptionError:
            raise
        except Exception as exc:
            raise DecryptionError(f"Failed to decrypt {description}") from exc

    @staticmethod
    def _rsa_decrypt_key(encrypted_key_b64: str, private_key_b64: str) -> bytes:
        try:
            encrypted_key = base64.b64decode(encrypted_key_b64, validate=True)
            decrypted_key = parse_private_key(private_key_b64).decrypt(
                encrypted_key,
                OAEP(mgf=MGF1(algorithm=SHA256()), algorithm=SHA256(), label=None),
            )
            if len(decrypted_key) != _AES_KEY_LENGTH:
                raise DecryptionError(f"Decrypted AES key is not {_AES_KEY_LENGTH} bytes: {len(decrypted_key)}")
            return decrypted_key
        except DecryptionError:
            raise
        except Exception as exc:
            raise DecryptionError("Failed to decrypt AES key with RSA") from exc

    @staticmethod
    def _aes_decrypt(encrypted_data_b64: str, aes_key: bytes) -> str:
        try:
            combined = base64.b64decode(encrypted_data_b64, validate=True)
            if len(combined) < _GCM_IV_LENGTH + _GCM_TAG_LENGTH:
                raise ValueError("ciphertext is too short")
            plaintext = AESGCM(aes_key).decrypt(
                combined[:_GCM_IV_LENGTH],
                combined[_GCM_IV_LENGTH:],
                None,
            )
            return plaintext.decode("utf-8")
        except Exception as exc:
            raise DecryptionError("AES decryption failed") from exc
