"""Encryption service for hybrid RSA+AES encryption.

Provides end-to-end encryption compatible with the Java SDK:
- AES-256-GCM for data encryption
- RSA-OAEP (SHA-256, MGF1-SHA-256) for key encryption
- Base64 encoding for all encrypted data
- Combined format: IV (12 bytes) + ciphertext + tag (16 bytes)
"""

from __future__ import annotations

import base64
import logging
import os

from cryptography.hazmat.primitives.asymmetric.padding import MGF1, OAEP
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256

from cheqi.exceptions import EncryptionError
from cheqi.models.credit_note import EncryptedCreditNote
from cheqi.models.encryption import EncryptedReceiptRequestDto
from cheqi.models.matching import Recipient
from cheqi.utils.pem import parse_public_key

logger = logging.getLogger("cheqi.encryption")

_AES_KEY_LENGTH = 32  # 256 bits
_GCM_IV_LENGTH = 12  # 96 bits
_GCM_TAG_LENGTH = 16  # 128 bits


class EncryptionService:
    """Hybrid encryption service using AES-256-GCM + RSA-OAEP.

    Thread-safe and designed for high-throughput receipt encryption.
    """

    def encrypt_receipt_for_recipient(
        self, receipt_json: str, recipient: Recipient
    ) -> EncryptedReceiptRequestDto:
        """Encrypt a receipt for a single recipient.

        Args:
            receipt_json: The receipt content as a JSON string.
            recipient: The recipient with their RSA public key.

        Returns:
            EncryptedReceiptRequestDto with encrypted data.
        """
        try:
            encrypted_data_b64, encrypted_key_b64 = self._hybrid_encrypt(
                receipt_json, recipient.public_key or ""
            )

            return EncryptedReceiptRequestDto(
                recipient_id=recipient.id,
                public_key=recipient.public_key,
                receiver_type=recipient.receiver_type,
                encrypted_receipt=encrypted_data_b64,
                encrypted_symmetric_key=encrypted_key_b64,
            )
        except Exception as e:
            logger.error("Failed to encrypt receipt for recipient %s: %s", recipient.id, e)
            raise EncryptionError(f"Failed to encrypt receipt for recipient: {recipient.id}") from e

    def encrypt_credit_note_for_recipient(
        self, credit_note_json: str, recipient: Recipient
    ) -> EncryptedCreditNote:
        """Encrypt a credit note for a single recipient."""
        try:
            encrypted_data_b64, encrypted_key_b64 = self._hybrid_encrypt(
                credit_note_json, recipient.public_key or ""
            )

            return EncryptedCreditNote(
                recipient_id=recipient.id,
                receiver_type=recipient.receiver_type,
                public_key=recipient.public_key,
                encrypted_credit_note=encrypted_data_b64,
                encrypted_symmetric_key=encrypted_key_b64,
            )
        except Exception as e:
            logger.error("Failed to encrypt credit note for recipient %s: %s", recipient.id, e)
            raise EncryptionError(f"Failed to encrypt credit note for recipient: {recipient.id}") from e

    def _hybrid_encrypt(self, plaintext: str, public_key_b64: str) -> tuple[str, str]:
        """Perform hybrid encryption: AES-GCM data + RSA-OAEP key.

        Returns:
            Tuple of (encrypted_data_base64, encrypted_key_base64).
        """
        # Step 1: Generate random AES-256 key
        aes_key = os.urandom(_AES_KEY_LENGTH)

        # Step 2: Encrypt data with AES-256-GCM
        encrypted_data_b64 = self._aes_encrypt(plaintext, aes_key)

        # Step 3: Encrypt AES key with RSA-OAEP
        encrypted_key_b64 = self._rsa_encrypt_key(aes_key, public_key_b64)

        return encrypted_data_b64, encrypted_key_b64

    def _aes_encrypt(self, plaintext: str, key: bytes) -> str:
        """Encrypt plaintext with AES-256-GCM.

        Returns Base64-encoded: IV (12 bytes) + ciphertext + tag (16 bytes).
        This layout is compatible with the Java SDK and iOS clients.
        """
        iv = os.urandom(_GCM_IV_LENGTH)
        aesgcm = AESGCM(key)

        # AESGCM.encrypt returns ciphertext + tag appended
        ciphertext_with_tag = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)

        # Separate ciphertext and tag
        ciphertext = ciphertext_with_tag[:-_GCM_TAG_LENGTH]
        tag = ciphertext_with_tag[-_GCM_TAG_LENGTH:]

        # Combine: IV + ciphertext + tag (matches Java EncryptedData.toBase64String())
        combined = iv + ciphertext + tag
        return base64.b64encode(combined).decode("ascii")

    def _rsa_encrypt_key(self, aes_key: bytes, public_key_b64: str) -> str:
        """Encrypt an AES key with RSA-OAEP using the recipient's public key."""
        public_key = parse_public_key(public_key_b64)

        encrypted_key = public_key.encrypt(
            aes_key,
            OAEP(
                mgf=MGF1(algorithm=SHA256()),
                algorithm=SHA256(),
                label=None,
            ),
        )
        return base64.b64encode(encrypted_key).decode("ascii")
