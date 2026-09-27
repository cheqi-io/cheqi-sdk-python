from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from cheqi.config import CheqiSDKConfig, Environment
from cheqi.http.client import DefaultCheqiApiClient
from cheqi.models import (
    ClientReceiptDownloadRequest,
    EncryptedCreditNoteEnvelope,
    EncryptedReceiptEnvelope,
    EncryptedReceiptPayload,
    IdentificationDetails,
)


def _client() -> DefaultCheqiApiClient:
    return DefaultCheqiApiClient(CheqiSDKConfig(environment=Environment.SANDBOX, api_key="example_api_key"))


def _delivery() -> EncryptedReceiptPayload:
    return EncryptedReceiptPayload(
        device_recipient_id="device-1",
        encrypted_content="ciphertext",
        encrypted_aes_key="key",
    )


def test_match_customer_posts_generated_contract(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://sandbox.api.cheqi.io/recipient/resolve",
        json={"routeFound": True, "deliveryRouteType": "DIGITAL", "matchId": "match-1"},
    )
    client = _client()

    response = client.match_customer(IdentificationDetails(pairing_code="12345678"))

    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Authorization"] == "Bearer example_api_key"
    assert json.loads(request.content) == {"pairingCode": "12345678"}
    assert response.match_id == "match-1"
    client.close()


def test_receipt_and_credit_note_use_distinct_envelopes(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://sandbox.api.cheqi.io/receipt/encrypted",
        json={"cheqiReceiptId": "receipt-1", "matchId": "match-1", "status": "PENDING"},
    )
    httpx_mock.add_response(
        method="POST",
        url="https://sandbox.api.cheqi.io/credit-note/encrypted",
        json={"cheqiReceiptId": "credit-1", "matchId": "match-1", "status": "PENDING"},
    )
    client = _client()

    client.submit_encrypted_receipt(EncryptedReceiptEnvelope(match_id="match-1", device_deliveries=[_delivery()]))
    client.submit_encrypted_credit_note(
        EncryptedCreditNoteEnvelope(
            match_id="match-1",
            parent_cheqi_receipt_id="receipt-1",
            device_deliveries=[_delivery()],
        )
    )

    requests = httpx_mock.get_requests()
    assert json.loads(requests[0].content)["deviceDeliveries"][0]["deviceRecipientId"] == "device-1"
    assert json.loads(requests[1].content)["parentCheqiReceiptId"] == "receipt-1"
    client.close()


def test_upload_encrypted_download_receipt(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://sandbox.api.cheqi.io/receipt/download",
        json={"cheqiReceiptId": "receipt-1"},
    )
    client = _client()

    client.upload_encrypted_download_receipt(
        ClientReceiptDownloadRequest(
            download_id="A" * 22,
            ciphertext="ciphertext",
            template_hash="hash",
        ),
        "oauth-token",
    )

    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Authorization"] == "Bearer oauth-token"
    assert json.loads(request.content)["templateHash"] == "hash"
    client.close()


def test_get_match_uses_authenticated_get_and_generated_state(httpx_mock: HTTPXMock) -> None:
    from cheqi.models import MatchState

    httpx_mock.add_response(method="GET", url="https://sandbox.api.cheqi.io/recipient/matches/match-1",
                            json={"state": "MATCHED", "matchId": "match-1", "route": "DIGITAL"})
    client = _client()
    response = client.get_match("match-1", "rotated-key")
    assert response.state is MatchState.MATCHED
    request = httpx_mock.get_request()
    assert request.headers["Authorization"] == "Bearer rotated-key"
    assert request.content == b""
    client.close()


@pytest.mark.parametrize("body", ["", "{", "null", "{}", "[]"])
def test_malformed_submission_is_typed_ambiguous_error(httpx_mock: HTTPXMock, body: str) -> None:
    from cheqi.exceptions import CheqiApiError, ErrorCodes

    httpx_mock.add_response(method="POST", url="https://sandbox.api.cheqi.io/receipt/encrypted",
                            status_code=202, text=body)
    client = _client()
    with pytest.raises(CheqiApiError) as caught:
        client.submit_encrypted_receipt(EncryptedReceiptEnvelope(match_id="match-1", device_deliveries=[_delivery()]))
    assert caught.value.error_code == ErrorCodes.INVALID_RESPONSE
    assert caught.value.http_status_code == 202
    client.close()


def test_low_level_in_progress_preserves_retry_delay(httpx_mock: HTTPXMock) -> None:
    from cheqi.exceptions import SubmissionInProgressError

    httpx_mock.add_response(method="POST", url="https://sandbox.api.cheqi.io/receipt/encrypted",
                            status_code=202, json={"state": "IN_PROGRESS", "matchId": "match-1",
                                                  "retryAfterSeconds": 7})
    client = _client()
    with pytest.raises(SubmissionInProgressError) as caught:
        client.submit_encrypted_receipt(EncryptedReceiptEnvelope(match_id="match-1", device_deliveries=[_delivery()]))
    assert caught.value.http_status_code == 202
    assert caught.value.error_code == "SUBMISSION_IN_PROGRESS"
    assert caught.value.retry_after_seconds == 7
    client.close()
