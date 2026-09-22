from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives.asymmetric.padding import MGF1, OAEP
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256

from cheqi.models import (
    CreditNoteInitiationRequest,
    EncryptedCreditNoteInitiationRequest,
    EncryptedReceiptDeliveryResponse,
    MatchedRecipient,
    ReceiptEnvelope,
    ReceiptEnvelopeDocument,
    RefundPreference,
    ReturnLineItem,
    ReturnReasonCode,
)
from cheqi.services.decryption import DecryptionService
from cheqi.services.encryption import EncryptionService
from cheqi.utils.pem import parse_private_key


def _decrypt_device_payload(ciphertext: str, encrypted_key: str, private_key: str) -> str:
    aes_key = parse_private_key(private_key).decrypt(
        base64.b64decode(encrypted_key),
        OAEP(mgf=MGF1(algorithm=SHA256()), algorithm=SHA256(), label=None),
    )
    framed = base64.b64decode(ciphertext)
    return AESGCM(aes_key).decrypt(framed[:12], framed[12:], None).decode()


def test_device_encryption_preserves_exact_plaintext(rsa_key_pair: tuple[str, str]) -> None:
    private_key, public_key = rsa_key_pair
    recipient = MatchedRecipient(id="device-1", public_key=public_key)
    plaintext = '{"documentNumber":"POS-1","totalAmount":12.1}'

    encrypted = EncryptionService().encrypt_for_device(plaintext, recipient)

    assert encrypted.device_recipient_id == "device-1"
    assert (
        _decrypt_device_payload(
            encrypted.encrypted_content,
            encrypted.encrypted_aes_key,
            private_key,
        )
        == plaintext
    )


def test_complete_receipt_envelope_decryption(rsa_key_pair: tuple[str, str]) -> None:
    private_key, public_key = rsa_key_pair
    envelope = ReceiptEnvelope(
        cheqi_receipt_id="receipt-1",
        documents={
            "CHEQI": ReceiptEnvelopeDocument(
                content='{"documentNumber":"POS-1"}',
                media_type="application/json",
            )
        },
        envelope_version=1,
        receipt_generator_version="1.0.0",
        receipt_uuid="34d267cf-357f-41d6-a62a-d7cb680aa3ba",
    )
    encrypted = EncryptionService().encrypt_for_device(
        envelope.model_dump_json(by_alias=True),
        MatchedRecipient(id="device-1", public_key=public_key),
    )
    delivery = EncryptedReceiptDeliveryResponse(
        encrypted_envelope=encrypted.encrypted_content,
        encrypted_envelope_key=encrypted.encrypted_aes_key,
    )

    decrypted = DecryptionService().decrypt_receipt(delivery, private_key)

    assert decrypted.cheqi_receipt_id == "receipt-1"
    assert json.loads(decrypted.documents["CHEQI"].content)["documentNumber"] == "POS-1"


def test_decrypts_and_validates_credit_note_initiation_request(
    rsa_key_pair: tuple[str, str],
) -> None:
    private_key, public_key = rsa_key_pair
    request = CreditNoteInitiationRequest(
        cheqi_receipt_id="receipt-1",
        receipt_id="POS-1",
        line_items=[
            ReturnLineItem(
                product_id="SKU-1",
                quantity="1.5",
                reason_code=ReturnReasonCode.DAMAGED,
            )
        ],
        refund_preference=RefundPreference.ORIGINAL_PAYMENT_METHOD,
    )
    encrypted = EncryptionService().encrypt_for_device(
        request.to_json(),
        MatchedRecipient(id="issuer", public_key=public_key),
    )
    delivery = EncryptedCreditNoteInitiationRequest(
        cheqi_receipt_id="receipt-1",
        public_key=public_key,
        encrypted_credit_note_initiation_request=encrypted.encrypted_content,
        encrypted_symmetric_key=encrypted.encrypted_aes_key,
    )

    decrypted = DecryptionService().decrypt_credit_note_initiation_request(delivery, private_key)

    assert decrypted.line_items[0].product_id == "SKU-1"
    assert str(decrypted.line_items[0].quantity) == "1.5"
