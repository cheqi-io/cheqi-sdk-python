"""Decryption service for hybrid RSA+AES decryption.

Compatible with content encrypted by the Java SDK EncryptionService.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.padding import MGF1, OAEP
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256

from cheqi.exceptions import DecryptionError
from cheqi.models.credit_note import EncryptedCreditNoteInitiationRequest
from cheqi.models.credit_note import CreditNoteEnvelope, DecryptedDeliveredCreditNote
from cheqi.models.generated.credit_note_context_envelope import CreditNoteContextEnvelope
from cheqi.models.generated.encrypted_credit_note_dto import EncryptedCreditNoteDto
from cheqi.models.encryption import EncryptedReceipt
from cheqi.utils.pem import parse_private_key

logger = logging.getLogger("cheqi.decryption")

_GCM_IV_LENGTH = 12
_GCM_TAG_LENGTH = 16
_AES_KEY_LENGTH = 32


@dataclass(frozen=True)
class DecryptedReceipt:
    """Result of decrypting a receipt."""

    receipt_content: str
    customer_details: Optional[str] = None


@dataclass(frozen=True)
class DecryptedCreditNote:
    """Result of decrypting a credit note."""

    content: str


class DecryptionService:
    """Decryption service for Cheqi hybrid-encrypted content."""

    def decrypt_receipt(
        self, encrypted_receipt: EncryptedReceipt, private_key_b64: str
    ) -> DecryptedReceipt:
        """Decrypt a hybrid-encrypted receipt using the client's private key.

        Steps:
        1. Decrypt AES key with RSA-OAEP
        2. Decrypt receipt content with AES-256-GCM
        3. Decrypt customer details if present
        """
        try:
            # Step 1: Decrypt receipt AES key
            receipt_aes_key = self._rsa_decrypt_key(
                encrypted_receipt.encrypted_symmetric_key or "", private_key_b64
            )

            # Step 2: Decrypt receipt content
            receipt_content = self._aes_decrypt(
                encrypted_receipt.encrypted_receipt or "", receipt_aes_key
            )

            # Step 3: Decrypt customer details if present
            customer_details = None
            if (
                encrypted_receipt.encrypted_customer_details
                and encrypted_receipt.encrypted_customer_details.strip()
                and encrypted_receipt.encrypted_customer_aes_key
            ):
                customer_aes_key = self._rsa_decrypt_key(
                    encrypted_receipt.encrypted_customer_aes_key, private_key_b64
                )
                customer_details = self._aes_decrypt(
                    encrypted_receipt.encrypted_customer_details, customer_aes_key
                )

            return DecryptedReceipt(
                receipt_content=receipt_content,
                customer_details=customer_details,
            )
        except DecryptionError:
            raise
        except Exception as e:
            logger.error(
                "Failed to decrypt receipt for recipient %s: %s",
                encrypted_receipt.recipient_id,
                e,
            )
            raise DecryptionError(f"Failed to decrypt receipt: {e}") from e

    def decrypt_credit_note(
        self,
        encrypted_credit_note: EncryptedCreditNoteInitiationRequest,
        private_key_b64: str,
    ) -> DecryptedCreditNote:
        """Decrypt a hybrid-encrypted credit note request using the issuer's private key."""
        try:
            # Step 1: Decrypt AES key
            aes_key = self._rsa_decrypt_key(
                encrypted_credit_note.encrypted_symmetric_key or "", private_key_b64
            )

            # Step 2: Decrypt credit note content
            content = self._aes_decrypt(
                encrypted_credit_note.encrypted_credit_note_initiation_request or "",
                aes_key,
            )

            return DecryptedCreditNote(content=content)
        except DecryptionError:
            raise
        except Exception as e:
            logger.error(
                "Failed to decrypt credit note for receipt %s: %s",
                encrypted_credit_note.cheqi_receipt_id,
                e,
            )
            raise DecryptionError(f"Failed to decrypt credit note: {e}") from e

    def decrypt_credit_note_payload(
        self,
        encrypted_credit_note: EncryptedCreditNoteDto,
        private_key_b64: str,
    ) -> DecryptedDeliveredCreditNote:
        """Decrypt a delivered encrypted credit note and optional context payload."""
        try:
            aes_key = self._rsa_decrypt_key(
                encrypted_credit_note.encrypted_symmetric_key, private_key_b64
            )
            credit_note_content = self._aes_decrypt(
                encrypted_credit_note.encrypted_credit_note, aes_key
            )

            context_json = None
            context = None
            if (
                encrypted_credit_note.encrypted_customer_details
                and encrypted_credit_note.encrypted_customer_aes_key
            ):
                context_key = self._rsa_decrypt_key(
                    encrypted_credit_note.encrypted_customer_aes_key,
                    private_key_b64,
                )
                context_json = self._aes_decrypt(
                    encrypted_credit_note.encrypted_customer_details,
                    context_key,
                )
                context = CreditNoteContextEnvelope.from_dict(json.loads(context_json))

            return DecryptedDeliveredCreditNote(
                credit_note_envelope=CreditNoteEnvelope.model_validate_json(
                    credit_note_content
                ),
                credit_note_context_envelope=context,
                raw_json=credit_note_content,
                raw_credit_note_context_json=context_json,
            )
        except DecryptionError:
            raise
        except Exception as e:
            raise DecryptionError(f"Failed to decrypt delivered credit note: {e}") from e

    def _rsa_decrypt_key(self, encrypted_key_b64: str, private_key_b64: str) -> bytes:
        """Decrypt an AES key encrypted with RSA-OAEP."""
        try:
            encrypted_key_bytes = base64.b64decode(encrypted_key_b64)
            private_key = parse_private_key(private_key_b64)

            decrypted_key = private_key.decrypt(
                encrypted_key_bytes,
                OAEP(
                    mgf=MGF1(algorithm=SHA256()),
                    algorithm=SHA256(),
                    label=None,
                ),
            )

            if len(decrypted_key) != _AES_KEY_LENGTH:
                raise DecryptionError(
                    f"Decrypted AES key is not {_AES_KEY_LENGTH} bytes: {len(decrypted_key)}"
                )

            return decrypted_key
        except DecryptionError:
            raise
        except Exception as e:
            raise DecryptionError(f"Failed to decrypt AES key with RSA: {e}") from e

    def _aes_decrypt(self, encrypted_data_b64: str, aes_key: bytes) -> str:
        """Decrypt AES-GCM encrypted content.

        Expected format: Base64(IV (12 bytes) + ciphertext + tag (16 bytes))
        """
        try:
            combined = base64.b64decode(encrypted_data_b64)

            # Extract components
            iv = combined[:_GCM_IV_LENGTH]
            ciphertext = combined[_GCM_IV_LENGTH:-_GCM_TAG_LENGTH]
            tag = combined[-_GCM_TAG_LENGTH:]

            # AESGCM.decrypt expects ciphertext + tag
            ciphertext_with_tag = ciphertext + tag

            aesgcm = AESGCM(aes_key)
            plaintext = aesgcm.decrypt(iv, ciphertext_with_tag, None)

            return plaintext.decode("utf-8")
        except DecryptionError:
            raise
        except Exception as e:
            raise DecryptionError(f"AES decryption failed: {e}") from e
