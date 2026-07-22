"""Wire-contract tests for routes added or renamed in the Java SDK."""

from __future__ import annotations

import json

from pytest_httpx import HTTPXMock

from cheqi.config import CheqiSDKConfig
from cheqi.http.client import DefaultCheqiApiClient
from cheqi.models.download import ClientReceiptDownloadRequest
from cheqi.models.enums import ReceiptFormat, ReceiverType
from cheqi.models.matching import Recipient
from cheqi.models.receipt import CheqiReceipt, ReceiptTemplateRequest
from cheqi.services.encryption import EncryptionService


def _client() -> DefaultCheqiApiClient:
    return DefaultCheqiApiClient(
        CheqiSDKConfig(
            custom_api_endpoint="https://api.example.test",
            api_key="sk_test_123",
            max_retries=0,
        )
    )


def test_current_template_and_match_wire_names(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://api.example.test/receipt/template",
        json={"ublPurchaseReceipt": "<PurchaseReceipt/>", "ublInvoice": "<Invoice/>"},
    )
    client = _client()
    response = client.generate_receipt_template(
        ReceiptTemplateRequest(
            document_number="INV-1",
            buyer_country_code="NL",
            buyer_type="CONSUMER",
            taxes_applied=True,
        ),
        [ReceiptFormat.UBL_PURCHASE_RECEIPT, ReceiptFormat.UBL_INVOICE],
    )

    request = httpx_mock.get_request()
    assert request is not None
    body = json.loads(request.content)
    assert body["buyerType"] == "CONSUMER"
    assert "recipientEntityType" not in body
    assert "buyerCountryCode" not in body["receiptTemplateRequest"]
    assert "buyerType" not in body["receiptTemplateRequest"]
    assert "taxesApplied" not in body["receiptTemplateRequest"]
    assert response.ubl_purchase_receipt == "<PurchaseReceipt/>"
    assert response.ubl_invoice == "<Invoice/>"


def test_encrypted_receipt_email_and_download_bodies(
    httpx_mock: HTTPXMock,
    rsa_key_pair: tuple[str, str],
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://api.example.test/receipt/encrypted",
        json={"cheqiReceiptId": "CHQ-1"},
    )
    httpx_mock.add_response(
        method="POST", url="https://api.example.test/receipt/email", status_code=204
    )
    httpx_mock.add_response(
        method="POST",
        url="https://api.example.test/receipt/download",
        status_code=201,
        json={"cheqiReceiptId": "CHQ-2"},
    )
    client = _client()
    _, public_key = rsa_key_pair
    encrypted = EncryptionService().encrypt_receipt_for_recipient(
        '{"cheqi":{"documentNumber":"INV-1"}}',
        Recipient(
            id="recipient-1",
            receiver_type=ReceiverType.DEVICE,
            public_key=public_key,
            accepted_formats=[ReceiptFormat.CHEQI],
        ),
    )

    client.send_encrypted_receipts(
        "match-1",
        [encrypted],
        "hash-1",
    )
    client.send_receipt_via_email(
        "customer@example.com", CheqiReceipt(document_number="INV-1").to_json()
    )
    uploaded = client.upload_client_encrypted_receipt(
        ClientReceiptDownloadRequest(
            download_id="Zk9qYx3vT1KpN8wL2sRd_g",
            ciphertext="AAAA",
            template_hash="hash-1",
        )
    )

    requests = httpx_mock.get_requests()
    encrypted_body = json.loads(requests[0].content)
    email_body = json.loads(requests[1].content)
    download_body = json.loads(requests[2].content)
    assert "encryptedReceiptRequests" in encrypted_body
    assert "encryptedReceipts" not in encrypted_body
    encrypted_item = encrypted_body["encryptedReceiptRequests"][0]
    assert "receiverType" not in encrypted_item
    assert "receiptFormats" not in encrypted_item
    assert email_body == {
        "customerEmail": "customer@example.com",
        "cheqiReceipt": {"documentNumber": "INV-1"},
    }
    assert download_body["downloadId"] == "Zk9qYx3vT1KpN8wL2sRd_g"
    assert uploaded.cheqi_receipt_id == "CHQ-2"
    assert all(request.headers["Authorization"] == "Bearer sk_test_123" for request in requests)
