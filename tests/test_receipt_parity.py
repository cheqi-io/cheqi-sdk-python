"""High-level route and decryption parity tests against the Java SDK contract."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cheqi.config import Environment
from cheqi.exceptions import CheqiApiError, ErrorCodes, ReceiptProcessingError
from cheqi.models.download import ClientReceiptDownloadResponse
from cheqi.models.encryption import EncryptedReceipt
from cheqi.models.enums import ReceiptFormat
from cheqi.models.envelopes import (
    DeliveryStatus,
    PaymentMeansEnvelope,
    ReceiptContextEnvelope,
    ReceiptEnvelope,
    ReceivingPartyEnvelope,
)
from cheqi.models.matching import (
    DeliveryRouteType,
    IdentificationDetails,
    Recipient,
    RecipientResolutionResponse,
)
from cheqi.models.receipt import CheqiReceipt, ReceiptTemplateRequest, ReceiptTemplateResponse, ReceivingParty
from cheqi.sdk import CheqiSDK
from cheqi.services.download import DownloadService
from cheqi.services.encryption import EncryptionService
from cheqi.services.receipt import ReceiptService


def _service(api_client: MagicMock, matching_service: MagicMock) -> ReceiptService:
    return ReceiptService(
        api_client,
        EncryptionService(),
        matching_service,
        DownloadService(),
        Environment.PRODUCTION.receipt_download_base_url,
    )


def test_download_fallback_uses_client_encrypted_upload() -> None:
    api = MagicMock()
    matching = MagicMock()
    matching.match_customer.return_value = RecipientResolutionResponse(
        route_found=True,
        delivery_route_type=DeliveryRouteType.DOWNLOAD_FALLBACK,
        match_id="match-download",
        recipients=[Recipient(accepted_formats=[ReceiptFormat.CHEQI])],
    )
    api.generate_receipt_template.return_value = ReceiptTemplateResponse(
        cheqi=CheqiReceipt(document_number="INV-1")
    )
    api.upload_client_encrypted_receipt.return_value = ClientReceiptDownloadResponse(
        cheqi_receipt_id="download-1"
    )

    result = _service(api, matching).process_complete_receipt(
        IdentificationDetails(recipient_email="customer@example.com"),
        ReceiptTemplateRequest(document_number="INV-1"),
    )

    assert result.delivery_status is DeliveryStatus.DELIVERED_DOWNLOAD
    assert result.cheqi_receipt_id == "download-1"
    assert result.download_url is not None
    assert result.download_url.startswith("https://receipt.cheqi.io/")
    request = api.upload_client_encrypted_receipt.call_args.args[0]
    link = DownloadService().parse_download_url(result.download_url)
    decrypted = DownloadService().decrypt_download_envelope(request.ciphertext, link.content_key)
    assert decrypted.cheqi is not None
    assert decrypted.cheqi.document_number == "INV-1"
    api.send_encrypted_receipts.assert_not_called()


def test_route_without_explicit_type_is_rejected_before_templating() -> None:
    api = MagicMock()
    matching = MagicMock()
    matching.match_customer.return_value = RecipientResolutionResponse(
        route_found=True,
        recipients=[Recipient(accepted_formats=[ReceiptFormat.CHEQI])],
    )

    with pytest.raises(ReceiptProcessingError, match="deliveryRouteType"):
        _service(api, matching).process_complete_receipt(
            IdentificationDetails(recipient_email="customer@example.com"),
            ReceiptTemplateRequest(document_number="INV-1"),
        )

    api.generate_receipt_template.assert_not_called()


def test_network_failure_during_matching_returns_pending_download_template() -> None:
    api = MagicMock()
    matching = MagicMock()
    matching.match_customer.side_effect = CheqiApiError(
        "offline", error_code=ErrorCodes.NETWORK_ERROR
    )

    result = _service(api, matching).process_complete_receipt(
        IdentificationDetails(recipient_email="customer@example.com"),
        ReceiptTemplateRequest(document_number="INV-1"),
    )

    assert result.delivery_status is DeliveryStatus.PENDING_DOWNLOAD_TEMPLATE
    assert result.download_url is not None
    api.generate_receipt_template.assert_not_called()


def test_network_failure_during_upload_returns_exact_ciphertext_for_retry() -> None:
    api = MagicMock()
    matching = MagicMock()
    matching.match_customer.return_value = RecipientResolutionResponse(
        route_found=True,
        delivery_route_type=DeliveryRouteType.DOWNLOAD_FALLBACK,
        recipients=[Recipient(accepted_formats=[ReceiptFormat.CHEQI])],
    )
    api.generate_receipt_template.return_value = ReceiptTemplateResponse(
        cheqi=CheqiReceipt(document_number="INV-2")
    )
    api.upload_client_encrypted_receipt.side_effect = CheqiApiError(
        "offline", error_code=ErrorCodes.NETWORK_ERROR
    )

    result = _service(api, matching).process_complete_receipt(
        IdentificationDetails(recipient_email="customer@example.com"),
        ReceiptTemplateRequest(document_number="INV-2"),
    )

    request = api.upload_client_encrypted_receipt.call_args.args[0]
    assert result.delivery_status is DeliveryStatus.PENDING_DOWNLOAD_UPLOAD
    assert result.download_ciphertext == request.ciphertext
    assert result.template_hash == request.template_hash


def test_process_encrypted_receipt_decrypts_and_merges_context(
    rsa_key_pair: tuple[str, str],
) -> None:
    private_key, public_key = rsa_key_pair
    encryption = EncryptionService()
    recipient = Recipient(id="recipient-1", public_key=public_key)
    receipt_plaintext = ReceiptEnvelope(
        cheqi=CheqiReceipt(document_number="INV-3"),
        ubl_purchase_receipt="<r><cac:AccountingCustomerParty/></r>",
        ubl_invoice="<i><cac:AccountingCustomerParty/></i>",
    ).to_json()
    context_plaintext = ReceiptContextEnvelope(
        receiving_party=ReceivingPartyEnvelope(
            xml_receiving_party=(
                "<cac:AccountingCustomerParty><cbc:Name>Ada</cbc:Name>"
                "</cac:AccountingCustomerParty>"
            ),
            receiving_party=ReceivingParty(consumer_name="Ada"),
        ),
        payment_means=PaymentMeansEnvelope(xml_payment_means="<cac:PaymentMeans/>")
    ).to_json()
    encrypted_receipt = encryption.encrypt_receipt_for_recipient(receipt_plaintext, recipient)
    encrypted_context = encryption.encrypt_receipt_for_recipient(context_plaintext, recipient)
    payload = EncryptedReceipt(
        encrypted_receipt=encrypted_receipt.encrypted_receipt,
        encrypted_symmetric_key=encrypted_receipt.encrypted_symmetric_key,
        encrypted_customer_details=encrypted_context.encrypted_receipt,
        encrypted_customer_aes_key=encrypted_context.encrypted_symmetric_key,
    )

    with CheqiSDK(environment=Environment.SANDBOX) as sdk:
        decrypted = sdk.process_encrypted_receipt(payload, private_key)

    assert decrypted.receipt_envelope is not None
    assert decrypted.receipt_envelope.cheqi is not None
    assert decrypted.receipt_envelope.cheqi.receiving_party is not None
    assert decrypted.receipt_envelope.cheqi.receiving_party.consumer_name == "Ada"
    assert "<cac:PaymentMeans/>" in (decrypted.receipt_envelope.ubl_purchase_receipt or "")
    assert "<cac:PaymentMeans/>" in (decrypted.receipt_envelope.ubl_invoice or "")
