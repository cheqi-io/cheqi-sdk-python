from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from cheqi.exceptions import CheqiSDKError, ErrorCodes
from cheqi.http.request_options import RequestOptions
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
                brand_name="Cheqi Coffee",
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
        options=RequestOptions.with_access_token("oauth-token"),
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
    api.submit_encrypted_receipt.assert_called_once_with(
        envelope, options=RequestOptions.with_access_token("oauth-token"),
    )


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
    assert envelope.envelope_version == 2
    assert json.loads(envelope.documents["IDENTIFICATION_DETAILS"].content)["paymentType"] == "CASH"


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


def _digital_service():
    return _service(RecipientResolutionResponse(
        route_found=True, delivery_route_type="DIGITAL", match_id="match-1",
        recipients=[MatchedRecipient(id="device-1", public_key="key-1")],
    ))


def test_public_envelope_generation_accepts_both_generated_match_models() -> None:
    from uuid import uuid4

    from cheqi.models import MatchState, MatchStatusResponse

    service, api, encryption, _ = _digital_service()
    store_id = uuid4()
    recipients = [MatchedRecipient(id="device-1", public_key="key-1")]
    for match in [
        RecipientResolutionResponse(route_found=True, delivery_route_type="DIGITAL",
                                    match_id="match-1", recipients=recipients),
        MatchStatusResponse(state=MatchState.MATCHED, route="DIGITAL",
                            match_id="match-1", recipients=recipients),
    ]:
        envelope = service.generate_encrypted_receipt_envelope(match, _payload(), store_id=store_id)
        assert envelope.match_id == "match-1"
        assert envelope.store_id == str(store_id)
        assert envelope.device_deliveries[0].encrypted_content == "ciphertext"
    assert encryption.encrypt_receipt_for_recipient.call_count == 2
    api.submit_encrypted_receipt.assert_not_called()
    service._matching_service.match_customer.assert_not_called()


@pytest.mark.parametrize("status", [0, 202, 503, 408, 429])
def test_ambiguous_submission_preserves_match_and_prepares_qr(status: int) -> None:
    from cheqi.exceptions import CheqiApiError
    from cheqi.models import ReceiptIssueState

    service, api, _, download = _digital_service()
    api.submit_encrypted_receipt.side_effect = CheqiApiError(
        "Uncertain", ErrorCodes.INVALID_RESPONSE if status in (0, 202) else ErrorCodes.SERVER_ERROR, status,
    )
    result = service.issue_receipt(IdentificationDetails(pairing_code="12345678"), _payload())
    assert result.state is ReceiptIssueState.DIGITAL_PENDING
    assert result.match_id == "match-1"
    assert result.retryable and not result.is_accepted
    assert result.download_url and result.prepared_download
    document = download.encrypt_download_envelope.call_args.args[0].documents["RECEIPT_PAYLOAD"].content
    assert "identificationDetails" not in document
    assert "12345678" not in document
    api.upload_encrypted_download_receipt.assert_not_called()


def test_network_before_matching_returns_download_without_match() -> None:
    from cheqi.exceptions import CheqiApiError
    from cheqi.models import ReceiptIssueState

    service, api, _, _ = _digital_service()
    service._matching_service.match_customer.side_effect = CheqiApiError("Offline", ErrorCodes.NETWORK_ERROR)
    result = service.issue_receipt(IdentificationDetails(pairing_code="12345678"), _payload())
    assert result.state is ReceiptIssueState.DOWNLOAD_FALLBACK
    assert result.match_id is None and result.prepared_download
    api.submit_encrypted_receipt.assert_not_called()


def test_resume_submitted_recovers_without_matching_or_encrypting() -> None:
    from cheqi.models import MatchState, MatchStatusResponse, ReceiptIssueState

    service, api, encryption, _ = _digital_service()
    submission = ReceiptSubmissionResponse(cheqi_receipt_id="original", match_id="match-1", status="PENDING")
    api.get_match.return_value = MatchStatusResponse(
        state=MatchState.SUBMITTED, match_id="match-1", submission=submission,
    )
    result = service.resume_receipt("match-1", _payload(), options=RequestOptions.with_access_token("rotated-key"))
    assert result.state is ReceiptIssueState.DIGITAL_SUBMITTED
    assert result.submission == submission and not result.retryable
    api.get_match.assert_called_once_with("match-1", options=RequestOptions.with_access_token("rotated-key"))
    encryption.encrypt_receipt_for_recipient.assert_not_called()
    service._matching_service.match_customer.assert_not_called()
    api.submit_encrypted_receipt.assert_not_called()


def test_resume_matched_regenerates_using_only_match_id_and_payload() -> None:
    from cheqi.models import MatchState, MatchStatusResponse, ReceiptIssueState

    service, api, encryption, _ = _digital_service()
    api.get_match.return_value = MatchStatusResponse(
        state=MatchState.MATCHED, route="DIGITAL", match_id="match-1",
        recipients=[MatchedRecipient(id="device-1", public_key="key-1")],
    )
    result = service.resume_receipt("match-1", _payload())
    assert result.state is ReceiptIssueState.DIGITAL_SUBMITTED
    assert api.submit_encrypted_receipt.call_args.args[0].match_id == "match-1"
    assert "identificationDetails" not in encryption.encrypt_receipt_for_recipient.call_args.args[0]
    service._matching_service.match_customer.assert_not_called()


@pytest.mark.parametrize("state", ["EXPIRED", "IN_PROGRESS"])
def test_resume_returns_expected_typed_states_without_submission(state: str) -> None:
    from cheqi.models import MatchState, MatchStatusResponse, ReceiptIssueState

    service, api, encryption, _ = _digital_service()
    api.get_match.return_value = MatchStatusResponse(
        state=MatchState(state), match_id="match-1", retry_after_seconds=2,
    )
    result = service.resume_receipt("match-1", _payload())
    assert result.state is (ReceiptIssueState.DIGITAL_EXPIRED if state == "EXPIRED"
                            else ReceiptIssueState.DIGITAL_PENDING)
    assert result.retryable == (state == "IN_PROGRESS")
    assert result.download_url is None
    if state == "IN_PROGRESS":
        assert result.retry_after_seconds == 2
    encryption.encrypt_receipt_for_recipient.assert_not_called()
    api.submit_encrypted_receipt.assert_not_called()


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_permanent_submission_errors_preserve_metadata(status: int) -> None:
    from cheqi.exceptions import CheqiApiError

    service, api, _, _ = _digital_service()
    error = CheqiApiError("Permanent", ErrorCodes.INVALID_REQUEST, status, "trace")
    api.submit_encrypted_receipt.side_effect = error
    with pytest.raises(CheqiApiError) as caught:
        service.issue_receipt(IdentificationDetails(pairing_code="12345678"), _payload())
    assert caught.value is error
    assert caught.value.correlation_id == "trace"


def test_expiry_during_submission_is_terminal() -> None:
    from cheqi.exceptions import CheqiApiError
    from cheqi.models import ReceiptIssueState

    service, api, _, _ = _digital_service()
    api.submit_encrypted_receipt.side_effect = CheqiApiError("Expired", http_status_code=410)
    result = service.issue_receipt(IdentificationDetails(pairing_code="12345678"), _payload())
    assert result.state is ReceiptIssueState.DIGITAL_EXPIRED
    assert not result.retryable and result.match_id == "match-1"


def test_prepared_download_round_trip_reuses_generated_upload_request() -> None:
    from cheqi.exceptions import CheqiApiError
    from cheqi.models import PreparedReceiptDownload

    service, api, _, _ = _digital_service()
    api.submit_encrypted_receipt.side_effect = CheqiApiError("Offline", ErrorCodes.NETWORK_ERROR)
    result = service.issue_receipt(IdentificationDetails(pairing_code="12345678"), _payload())
    prepared = result.prepared_download
    assert prepared is not None
    restored = PreparedReceiptDownload.model_validate_json(prepared.model_dump_json())
    assert restored == prepared
    assert "ciphertext" not in repr(restored) and restored.download_url not in repr(restored)
    service.upload_prepared_download(restored)
    service.upload_prepared_download(restored)
    assert api.upload_encrypted_download_receipt.call_args_list[0].args[0] == prepared.upload_request
    assert api.upload_encrypted_download_receipt.call_args_list[1].args[0] == prepared.upload_request

def test_lost_response_recovers_original_submission_after_expiry_without_rematching() -> None:
    import httpx

    from cheqi.config import CheqiSDKConfig
    from cheqi.http.client import DefaultCheqiApiClient
    from cheqi.models import ReceiptIssueState
    from cheqi.services.matching import MatchingService

    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/recipient/resolve":
            return httpx.Response(200, json={
                "routeFound": True, "deliveryRouteType": "DIGITAL", "matchId": "match-1",
                "recipients": [{"id": "device-1", "publicKey": "key-1"}],
            })
        if request.url.path == "/receipt/encrypted":
            # Receipt committed; acknowledgement cannot be decoded.
            return httpx.Response(202, text="{")
        return httpx.Response(200, json={
            "state": "SUBMITTED", "matchId": "match-1", "expiresAt": "2020-01-01T00:00:00Z",
            "submission": {"cheqiReceiptId": "original", "matchId": "match-1", "status": "PENDING"},
        })

    _, _, encryption, download = _digital_service()
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        config = CheqiSDKConfig(custom_api_endpoint="https://api.example", api_key="test-key", max_retries=0)
        api = DefaultCheqiApiClient(config, http_client=transport)
        service = ReceiptService(api, encryption, MatchingService(api), download, "https://receipt.example")
        pending = service.issue_receipt(IdentificationDetails(pairing_code="12345678"), _payload())
        assert pending.state is ReceiptIssueState.DIGITAL_PENDING
        recovered = service.resume_receipt(pending.match_id, _payload())
        assert recovered.state is ReceiptIssueState.DIGITAL_SUBMITTED
        assert recovered.submission.cheqi_receipt_id == "original"
        assert [request.url.path for request in requests] == [
            "/recipient/resolve", "/receipt/encrypted", "/recipient/matches/match-1",
        ]
        assert encryption.encrypt_receipt_for_recipient.call_count == 1


def test_unauthorized_match_returns_original_404_without_rematching() -> None:
    from cheqi.exceptions import CheqiApiError

    service, api, encryption, _ = _digital_service()
    api.get_match.side_effect = CheqiApiError("Not found", "NOT_FOUND", 404, "trace")
    with pytest.raises(CheqiApiError) as caught:
        service.resume_receipt("match-1", _payload())
    assert caught.value.http_status_code == 404
    assert caught.value.correlation_id == "trace"
    service._matching_service.match_customer.assert_not_called()
    encryption.encrypt_receipt_for_recipient.assert_not_called()


def test_invalid_payload_is_rejected_before_matching() -> None:
    service, api, _, _ = _digital_service()
    payload = _payload().model_copy(update={"products": []})
    with pytest.raises(CheqiSDKError):
        service.issue_receipt(IdentificationDetails(pairing_code="12345678"), payload)
    service._matching_service.match_customer.assert_not_called()
    api.submit_encrypted_receipt.assert_not_called()
