"""Hybrid encryption for definitive receipt and credit-note payloads."""

from __future__ import annotations

import base64
import logging
import os

from cryptography.hazmat.primitives.asymmetric.padding import MGF1, OAEP
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256

from cheqi.exceptions import EncryptionError
from cheqi.models.generated.encrypted_receipt_payload import EncryptedReceiptPayload
from cheqi.models.generated.matched_recipient import MatchedRecipient
from cheqi.utils.pem import parse_public_key

logger = logging.getLogger("cheqi.encryption")

_AES_KEY_LENGTH = 32
_GCM_IV_LENGTH = 12


class EncryptionService:
    """Encrypt exact JSON independently for one temporary device recipient."""

    def encrypt_for_device(
        self,
        plaintext_json: str,
        recipient: MatchedRecipient,
    ) -> EncryptedReceiptPayload:
        if recipient is None:
            raise ValueError("recipient cannot be None")
        if not recipient.id or not recipient.id.strip():
            raise ValueError("recipient.id cannot be empty")
        if not recipient.public_key or not recipient.public_key.strip():
            raise ValueError("recipient.public_key cannot be empty")
        if not plaintext_json or not plaintext_json.strip():
            raise ValueError("plaintext_json cannot be empty")

        try:
            aes_key = os.urandom(_AES_KEY_LENGTH)
            iv = os.urandom(_GCM_IV_LENGTH)
            ciphertext_and_tag = AESGCM(aes_key).encrypt(iv, plaintext_json.encode("utf-8"), None)
            encrypted_key = parse_public_key(recipient.public_key).encrypt(
                aes_key,
                OAEP(mgf=MGF1(algorithm=SHA256()), algorithm=SHA256(), label=None),
            )
            return EncryptedReceiptPayload(
                device_recipient_id=recipient.id,
                encrypted_content=base64.b64encode(iv + ciphertext_and_tag).decode("ascii"),
                encrypted_aes_key=base64.b64encode(encrypted_key).decode("ascii"),
            )
        except Exception as exc:
            logger.error("Failed to encrypt payload for temporary recipient %s", recipient.id)
            raise EncryptionError(f"Failed to encrypt payload for temporary recipient {recipient.id}") from exc

    def encrypt_receipt_for_recipient(
        self,
        receipt_payload_json: str,
        recipient: MatchedRecipient,
    ) -> EncryptedReceiptPayload:
        """Receipt-specific compatibility alias."""
        return self.encrypt_for_device(receipt_payload_json, recipient)

    def encrypt_credit_note_for_recipient(
        self,
        credit_note_payload_json: str,
        recipient: MatchedRecipient,
    ) -> EncryptedReceiptPayload:
        """Credit-note-specific compatibility alias."""
        return self.encrypt_for_device(credit_note_payload_json, recipient)
