from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from cheqi.exceptions import CheqiSDKError, ErrorCodes
from cheqi.models import (
    ClientReceiptDownloadResponse,
    DeliveryRouteType,
    EncryptedReceiptPayload,
    IdentificationDetails,
    MatchedRecipient,
    PaymentType,
    Product,
    ReceiptPayload,
    ReceiptSubmissionResponse,
    RecipientResolutionResponse,
    UnitCode,
)
from cheqi.models.download import DownloadLink
from cheqi.services.receipt import ReceiptService


def _payload() -> ReceiptPayload:
    return ReceiptPayload(
        document_number="POS-1",
        issue_date=datetime(2026, 8, 12, tzinfo=timezone.utc),
        currency="EUR",
        receipt_subtotal="10.00",
        total_before_tax="10.00",
        total_tax_amount="2.10",
        total_amount="12.10",
        taxes_applied=True,
        products=[
            Product(
                name="Coffee",
                identifier="SKU-1",
                quantity=1,
                unit_code=UnitCode.C62,
                unit_price="10.00",
                subtotal="10.00",
                total="12.10",
            ).add_tax(21, "VAT", "10.00", "2.10")
        ],
    )


def _service(resolution: RecipientResolutionResponse):
    api = MagicMock()
    api.submit_encrypted_receipt.return_value = ReceiptSubmissionResponse(
        cheqi_receipt_id="receipt-1",
        match_id="match-1",
        status="PENDING",
        created_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    matching = MagicMock()
    matching.match_customer.return_value = resolution
    encryption = MagicMock()
    encryption.encrypt_receipt_for_recipient.return_value = EncryptedReceiptPayload(
        device_recipient_id="device-1",
        encrypted_content="ciphertext",
        encrypted_aes_key="key",
    )
    download = MagicMock()
    download.generate_download_link.return_value = DownloadLink(
        download_id="A" * 22,
        content_key="B" * 43,
        url=f"https://receipt.example/{'A' * 22}#{'B' * 43}",
    )
    download.encrypt_download_envelope.return_value = "download-ciphertext"
    service = ReceiptService(
        api,
        encryption,
        matching,
        download,
        "https://receipt.example",
    )
    return service, api, encryption, download


def test_issue_receipt_encrypts_same_definitive_json_for_each_device() -> None:
    recipients = [
        MatchedRecipient(id="device-1", public_key="key-1"),
        MatchedRecipient(id="device-2", public_key="key-2"),
    ]
    service, api, encryption, _ = _service(
        RecipientResolutionResponse(
            route_found=True,
            delivery_route_type="DIGITAL",
            match_id="match-1",
            recipients=recipients,
        )
    )

    result = service.issue_receipt(
        IdentificationDetails(pairing_code="12345678"),
        _payload(),
        access_token="oauth-token",
    )

    assert result.is_accepted
    assert result.delivery_route_type is DeliveryRouteType.DIGITAL
    calls = encryption.encrypt_receipt_for_recipient.call_args_list
    assert len(calls) == 2
    assert calls[0].args[0] == calls[1].args[0]
    assert json.loads(calls[0].args[0])["products"][0]["taxes"][0]["type"] == "VAT"
    envelope = api.submit_encrypted_receipt.call_args.args[0]
    assert envelope.match_id == "match-1"
    assert len(envelope.device_deliveries) == 2
    api.submit_encrypted_receipt.assert_called_once_with(envelope, "oauth-token")


def test_download_fallback_without_payment_context_requests_final_envelope() -> None:
    service, api, _, _ = _service(
        RecipientResolutionResponse(
            route_found=True,
            delivery_route_type="DOWNLOAD_FALLBACK",
            match_id="match-1",
            recipients=[],
        )
    )

    result = service.issue_receipt(IdentificationDetails(pairing_code="12345678"), _payload())

    assert result.download_envelope_required
    assert not result.is_accepted
    api.submit_encrypted_receipt.assert_not_called()


def test_download_fallback_with_payment_context_is_uploaded_client_encrypted() -> None:
    service, api, _, download = _service(
        RecipientResolutionResponse(
            route_found=True,
            delivery_route_type="DOWNLOAD_FALLBACK",
            match_id="match-1",
            recipients=[],
        )
    )
    api.upload_encrypted_download_receipt.return_value = ClientReceiptDownloadResponse(
        cheqi_receipt_id="download-receipt",
    )

    result = service.issue_receipt(
        IdentificationDetails(payment_type=PaymentType.CASH),
        _payload(),
    )

    assert result.is_accepted
    assert result.delivery_route_type is DeliveryRouteType.DOWNLOAD_FALLBACK
    request = api.upload_encrypted_download_receipt.call_args.args[0]
    assert request.ciphertext == "download-ciphertext"
    assert request.template_hash
    envelope = download.encrypt_download_envelope.call_args.args[0]
    cheqi_document = json.loads(envelope.documents["CHEQI"].content)
    assert cheqi_document["identificationDetails"]["paymentType"] == "CASH"


def test_email_route_returns_explicit_required_action() -> None:
    service, api, _, _ = _service(
        RecipientResolutionResponse(
            route_found=True,
            delivery_route_type="EMAIL_FALLBACK",
            match_id="match-1",
            recipients=[],
        )
    )

    result = service.issue_receipt(IdentificationDetails(recipient_email="a@example.com"), _payload())

    assert result.email_receipt_required
    api.submit_encrypted_receipt.assert_not_called()


def test_missing_route_is_reported_as_customer_not_found() -> None:
    service, _, _, _ = _service(RecipientResolutionResponse(route_found=False))

    with pytest.raises(CheqiSDKError) as error:
        service.issue_receipt(IdentificationDetails(pairing_code="12345678"), _payload())

    assert error.value.error_code == ErrorCodes.CUSTOMER_NOT_FOUND
