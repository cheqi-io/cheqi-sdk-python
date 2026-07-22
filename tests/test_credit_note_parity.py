"""End-to-end credit-note parity tests against the Java SDK contract."""

from __future__ import annotations

from unittest.mock import MagicMock

from cheqi.models.credit_note import (
    CreditNoteCreatedResponse,
    CreditNoteInitiationRequest,
    CreditNoteTemplateRequest,
    CreditNoteTemplateResponse,
    EncryptedCreditNoteInitiationRequest,
)
from cheqi.models.enums import ReceiptFormat
from cheqi.models.matching import IdentificationDetails, Recipient, RecipientResolutionResponse
from cheqi.services.credit_note import CreditNoteService
from cheqi.services.encryption import EncryptionService


def _service(api_client: MagicMock, matching_service: MagicMock) -> CreditNoteService:
    return CreditNoteService(api_client, EncryptionService(), matching_service)


def test_complete_credit_note_is_generated_encrypted_and_sent(
    rsa_key_pair: tuple[str, str],
) -> None:
    private_key, public_key = rsa_key_pair
    api = MagicMock()
    matching = MagicMock()
    matching.match_customer.return_value = RecipientResolutionResponse(
        route_found=True,
        match_id="credit-match",
        recipients=[
            Recipient(
                id="recipient-1",
                public_key=public_key,
                accepted_formats=[ReceiptFormat.UBL_CREDIT_NOTE],
            )
        ],
    )
    api.generate_credit_note_template.return_value = CreditNoteTemplateResponse(
        ubl_credit_note="<CreditNote><cbc:ID>CN-1</cbc:ID></CreditNote>"
    )
    api.send_encrypted_credit_notes.return_value = CreditNoteCreatedResponse(
        cheqi_receipt_id="credit-note-1",
        parent_cheqi_receipt_id="receipt-1",
    )
    service = _service(api, matching)

    result = service.process_complete_credit_note(
        IdentificationDetails(cheqi_receipt_id="receipt-1"),
        CreditNoteTemplateRequest(document_number="CN-1"),
    )

    generation_request = api.generate_credit_note_template.call_args.args[0]
    assert generation_request.formats == [ReceiptFormat.UBL_CREDIT_NOTE]
    assert generation_request.to_dict()["formats"] == ["UBL_CREDIT_NOTE"]

    send_args = api.send_encrypted_credit_notes.call_args.args
    assert send_args[0] == "credit-match"
    assert send_args[1] == "receipt-1"
    encrypted = send_args[2][0]
    decrypted = service.decrypt_delivered_credit_note(encrypted, private_key)
    assert decrypted.credit_note_envelope.cheqi_credit_note is None
    assert decrypted.credit_note_envelope.ubl_credit_note == (
        "<CreditNote><cbc:ID>CN-1</cbc:ID></CreditNote>"
    )
    assert result.success
    assert result.cheqi_receipt_id == "credit-note-1"
    assert result.parent_cheqi_receipt_id == "receipt-1"


def test_credit_note_initiation_is_decrypted_and_parsed(
    rsa_key_pair: tuple[str, str],
) -> None:
    private_key, public_key = rsa_key_pair
    service = _service(MagicMock(), MagicMock())
    encrypted = EncryptionService().encrypt_credit_note_for_recipient(
        CreditNoteInitiationRequest(
            cheqi_receipt_id="receipt-2",
            return_reason="DAMAGED",
        ).to_json(),
        Recipient(id="merchant", public_key=public_key),
    )
    request = EncryptedCreditNoteInitiationRequest(
        cheqi_receipt_id="receipt-2",
        encrypted_credit_note_initiation_request=encrypted.encrypted_credit_note,
        encrypted_symmetric_key=encrypted.encrypted_symmetric_key,
    )

    decrypted = service.decrypt_credit_note_request(request, private_key)

    assert decrypted.cheqi_receipt_id == "receipt-2"
    assert decrypted.return_reason == "DAMAGED"
