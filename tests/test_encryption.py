"""Tests for encryption/decryption round-trips and interop."""

from __future__ import annotations

import json

from cheqi.models.enums import ReceiverType
from cheqi.models.matching import Recipient
from cheqi.services.decryption import DecryptionService
from cheqi.services.encryption import EncryptionService


class TestEncryptionRoundTrip:
    """Test that encryption followed by decryption produces the original data."""

    def test_encrypt_decrypt_receipt(self, rsa_key_pair: tuple[str, str]) -> None:
        private_key_b64, public_key_b64 = rsa_key_pair

        receipt_json = json.dumps({
            "documentNumber": "INV-001",
            "currency": "EUR",
            "totalAmount": 121.00,
            "products": [{"name": "Laptop", "unitPrice": 100.00}],
        })

        recipient = Recipient(
            id="device-123",
            receiver_type=ReceiverType.DEVICE,
            public_key=public_key_b64,
        )

        # Encrypt
        encryption_service = EncryptionService()
        encrypted = encryption_service.encrypt_receipt_for_recipient(receipt_json, recipient)

        assert encrypted.recipient_id == "device-123"
        assert encrypted.encrypted_receipt is not None
        assert encrypted.encrypted_symmetric_key is not None

        # Build EncryptedReceipt for decryption
        from cheqi.models.encryption import EncryptedReceipt

        encrypted_receipt = EncryptedReceipt(
            recipient_id=encrypted.recipient_id,
            encrypted_receipt=encrypted.encrypted_receipt,
            encrypted_symmetric_key=encrypted.encrypted_symmetric_key,
        )

        # Decrypt
        decryption_service = DecryptionService()
        decrypted = decryption_service.decrypt_receipt(encrypted_receipt, private_key_b64)

        assert json.loads(decrypted.receipt_content) == json.loads(receipt_json)

    def test_encrypt_decrypt_credit_note(self, rsa_key_pair: tuple[str, str]) -> None:
        private_key_b64, public_key_b64 = rsa_key_pair

        credit_note_json = json.dumps({
            "documentNumber": "CN-001",
            "originatorDocumentReference": "INV-001",
            "totalAmount": -50.00,
        })

        recipient = Recipient(
            id="device-456",
            receiver_type=ReceiverType.DEVICE,
            public_key=public_key_b64,
        )

        # Encrypt
        encryption_service = EncryptionService()
        encrypted = encryption_service.encrypt_credit_note_for_recipient(
            credit_note_json, recipient
        )

        assert encrypted.recipient_id == "device-456"
        assert encrypted.encrypted_credit_note is not None
        assert encrypted.encrypted_symmetric_key is not None

        # Build for decryption
        from cheqi.models.credit_note import EncryptedCreditNoteInitiationRequest

        encrypted_cn = EncryptedCreditNoteInitiationRequest(
            cheqi_receipt_id="CHQ-123",
            public_key=public_key_b64,
            encrypted_credit_note_initiation_request=encrypted.encrypted_credit_note,
            encrypted_symmetric_key=encrypted.encrypted_symmetric_key,
        )

        decryption_service = DecryptionService()
        decrypted = decryption_service.decrypt_credit_note(encrypted_cn, private_key_b64)

        assert json.loads(decrypted.content) == json.loads(credit_note_json)

    def test_different_recipients_get_different_encrypted_data(
        self, rsa_key_pair: tuple[str, str]
    ) -> None:
        _, public_key_b64 = rsa_key_pair

        receipt_json = '{"test": "data"}'

        recipient1 = Recipient(id="dev-1", public_key=public_key_b64)
        recipient2 = Recipient(id="dev-2", public_key=public_key_b64)

        encryption_service = EncryptionService()
        enc1 = encryption_service.encrypt_receipt_for_recipient(receipt_json, recipient1)
        enc2 = encryption_service.encrypt_receipt_for_recipient(receipt_json, recipient2)

        # Different AES keys → different encrypted data
        assert enc1.encrypted_receipt != enc2.encrypted_receipt
        assert enc1.encrypted_symmetric_key != enc2.encrypted_symmetric_key

    def test_large_receipt_encryption(self, rsa_key_pair: tuple[str, str]) -> None:
        private_key_b64, public_key_b64 = rsa_key_pair

        # Create a large receipt with many products
        products = [
            {"name": f"Product {i}", "unitPrice": f"{i * 10}.99", "quantity": i}
            for i in range(100)
        ]
        large_receipt = json.dumps({
            "documentNumber": "LARGE-001",
            "products": products,
            "totalAmount": 99999.99,
        })

        recipient = Recipient(id="dev-1", public_key=public_key_b64)

        encryption_service = EncryptionService()
        encrypted = encryption_service.encrypt_receipt_for_recipient(large_receipt, recipient)

        from cheqi.models.encryption import EncryptedReceipt

        encrypted_receipt = EncryptedReceipt(
            recipient_id=encrypted.recipient_id,
            encrypted_receipt=encrypted.encrypted_receipt,
            encrypted_symmetric_key=encrypted.encrypted_symmetric_key,
        )

        decryption_service = DecryptionService()
        decrypted = decryption_service.decrypt_receipt(encrypted_receipt, private_key_b64)

        assert json.loads(decrypted.receipt_content) == json.loads(large_receipt)
