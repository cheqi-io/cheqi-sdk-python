from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from cheqi.exceptions import CheqiSDKError, ErrorCodes
from cheqi.http.request_options import RequestOptions
from cheqi.models import (
    EncryptedReceiptPayload,
    IdentificationDetails,
    MatchedRecipient,
    ReceiptSubmissionResponse,
    RecipientResolutionResponse,
)
from cheqi.services.credit_note import CreditNoteService


def test_issue_credit_note_uses_separate_envelope_and_preserves_payload() -> None:
    api = MagicMock()
    api.submit_encrypted_credit_note.return_value = ReceiptSubmissionResponse(
        cheqi_receipt_id="credit-note-1",
        match_id="match-1",
        status="PENDING",
        created_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    matching = MagicMock()
    matching.match_customer.return_value = RecipientResolutionResponse(
        route_found=True,
        delivery_route_type="DIGITAL",
        match_id="match-1",
        recipients=[MatchedRecipient(id="device-1", public_key="public-key")],
    )
    encryption = MagicMock()
    encryption.encrypt_credit_note_for_recipient.return_value = EncryptedReceiptPayload(
        device_recipient_id="device-1",
        encrypted_content="ciphertext",
        encrypted_aes_key="key",
    )
    service = CreditNoteService(api, encryption, matching)
    payload = {
        "documentNumber": "CN-1",
        "totalAmount": Decimal("4.25"),
        "items": [{"productId": "SKU-1", "quantity": Decimal("0.5")}],
    }

    result = service.issue_credit_note(
        IdentificationDetails(cheqi_receipt_id="parent-1"),
        "parent-1",
        payload,
        options=RequestOptions.with_access_token("oauth-token"),
    )

    assert result.is_accepted
    assert result.parent_cheqi_receipt_id == "parent-1"
    plaintext = encryption.encrypt_credit_note_for_recipient.call_args.args[0]
    assert json.loads(plaintext) == {
        "documentNumber": "CN-1",
        "totalAmount": 4.25,
        "items": [{"productId": "SKU-1", "quantity": 0.5}],
    }
    envelope = api.submit_encrypted_credit_note.call_args.args[0]
    assert envelope.parent_cheqi_receipt_id == "parent-1"
    assert envelope.device_deliveries[0].encrypted_content == "ciphertext"
    api.submit_encrypted_credit_note.assert_called_once_with(
        envelope, options=RequestOptions.with_access_token("oauth-token"),
    )


def test_issue_credit_note_requires_owner_devices() -> None:
    matching = MagicMock()
    matching.match_customer.return_value = RecipientResolutionResponse(
        route_found=True,
        match_id="match-1",
        recipients=[],
    )
    service = CreditNoteService(MagicMock(), MagicMock(), matching)

    with pytest.raises(CheqiSDKError) as error:
        service.issue_credit_note(
            IdentificationDetails(cheqi_receipt_id="parent-1"),
            "parent-1",
            {"documentNumber": "CN-1"},
        )

    assert error.value.error_code == ErrorCodes.VALIDATION_ERROR
