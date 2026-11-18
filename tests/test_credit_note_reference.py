import json
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from cheqi.exceptions import CheqiSDKError
from cheqi.models.generated.client_receipt_download_response import ClientReceiptDownloadResponse
from cheqi.models.generated.credit_note_reference_resolution import CreditNoteReferenceResolution
from cheqi.models.generated.matched_recipient import MatchedRecipient
from cheqi.models.generated.prepared_credit_note import PreparedCreditNote
from cheqi.models.generated.receipt_envelope import ReceiptEnvelope
from cheqi.models.generated.recipient_resolution_response import RecipientResolutionResponse
from cheqi.services.credit_note import CreditNoteService
from cheqi.services.decryption import DecryptionService
from cheqi.services.document_reference import add_download_recipient, document_reference_hash
from cheqi.services.download import DownloadService
from cheqi.services.encryption import EncryptionService

PAYLOAD = {
    "documentNumber": "CN-123",
    "originatorDocumentReference": "INV-123",
    "taxesApplied": True,
    "totalAmount": Decimal("12.123456789012345678"),
}


def test_exact_document_hash():
    expected = "7d4b8ece79c805d20d5451ad72f019580fe0dc893f7aa16eedd94992dbaebd32"
    assert document_reference_hash("INV-123") == expected
    assert document_reference_hash(" INV-123") != expected
    assert document_reference_hash("inv-123") != expected


def test_download_reference_encrypts_keys_and_replays_identical_submission():
    api, matching = MagicMock(), MagicMock()
    envelope = ReceiptEnvelope(
        documents={},
        cheqi_receipt_id="original",
        envelope_version=2,
        receipt_generator_version="test",
        receipt_uuid="b77cdb90-b38f-491c-b460-a9469ca58a5c",
    )
    public = add_download_recipient(envelope)
    private = json.loads(envelope.documents["DOWNLOAD_RECIPIENT_KEY"].content)["privateKey"]
    api.resolve_credit_note_reference.return_value = CreditNoteReferenceResolution(
        delivery_route="DOWNLOAD", parent_cheqi_receipt_id="original", credit_note_public_key=public
    )
    api.upload_encrypted_download_receipt.return_value = ClientReceiptDownloadResponse(cheqi_receipt_id="credit")
    service = CreditNoteService(api, EncryptionService(), matching)
    prepared = service.prepare_credit_note({
        "taxesApplied": True,
        "creditNoteTemplateRequest": {k: v for k, v in PAYLOAD.items() if k != "taxesApplied"},
    })
    saved = prepared.model_dump_json(by_alias=True, exclude_none=True)
    for value in ["INV-123", "CN-123", "contentKey", "privateKey"]:
        assert value not in saved
    restored = PreparedCreditNote.model_validate_json(saved)
    request = restored.download_submission
    link = json.loads(
        DecryptionService()._decrypt_payload(
            request.encrypted_parent_link, request.encrypted_parent_link_key, private, "credit-note link"
        )
    )
    assert link["parentCheqiReceiptId"] == "original"
    assert link["downloadId"] == request.download_id
    note = DownloadService().decrypt_download_envelope(request.ciphertext, link["contentKey"])
    content = json.loads(note.documents["CREDIT_NOTE_PAYLOAD"].content)
    assert content == {**PAYLOAD, "totalAmount": str(PAYLOAD["totalAmount"])}
    assert service.submit_prepared_credit_note(restored).is_accepted
    service.submit_prepared_credit_note(restored)
    assert api.resolve_credit_note_reference.call_count == 1
    assert api.resolve_credit_note_reference.call_args.args[0].document_reference_hash == document_reference_hash(
        "INV-123"
    )
    assert (
        api.upload_encrypted_download_receipt.call_args_list[0]
        == api.upload_encrypted_download_receipt.call_args_list[1]
    )
    matching.match_customer.assert_not_called()
    restored.parent_cheqi_receipt_id = "other"
    with pytest.raises(CheqiSDKError, match="parent mismatch"):
        service.submit_prepared_credit_note(restored)


def test_digital_reference_uses_original_store_and_preserves_decimal(rsa_key_pair):
    private, public = rsa_key_pair
    api, matching = MagicMock(), MagicMock()
    store = "b77cdb90-b38f-491c-b460-a9469ca58a5c"
    api.resolve_credit_note_reference.return_value = CreditNoteReferenceResolution(
        delivery_route="DIGITAL", parent_cheqi_receipt_id="original", store_id=store
    )
    matching.match_customer.return_value = RecipientResolutionResponse(
        route_found=True,
        delivery_route_type="DIGITAL",
        match_id="match",
        recipients=[MatchedRecipient(id="device", public_key=public)],
    )
    service = CreditNoteService(api, EncryptionService(), matching)
    prepared = service.prepare_credit_note(PAYLOAD)
    device = prepared.device_submission.device_deliveries[0]
    plaintext = json.loads(
        DecryptionService()._decrypt_payload(device.encrypted_content, device.encrypted_aes_key, private, "test")
    )
    assert plaintext["taxesApplied"] is True
    assert plaintext["creditNoteTemplateRequest"]["totalAmount"] == str(PAYLOAD["totalAmount"])
    assert prepared.device_submission.store_id == store
    assert matching.match_customer.call_args.args[0].cheqi_receipt_id == "original"


@pytest.mark.parametrize("status", [404, 409])
def test_reference_failure_never_falls_back(status):
    api, matching = MagicMock(), MagicMock()
    api.resolve_credit_note_reference.side_effect = CheqiSDKError("Unavailable", http_status_code=status)
    service = CreditNoteService(api, EncryptionService(), matching)
    with pytest.raises(CheqiSDKError) as error:
        service.prepare_credit_note(PAYLOAD)
    assert error.value.http_status_code == status
    api.upload_encrypted_download_receipt.assert_not_called()
    matching.match_customer.assert_not_called()
