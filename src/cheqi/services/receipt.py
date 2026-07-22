"""Receipt service for matching, templating, encryption, and fallback delivery."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import List, Optional

from cheqi.exceptions import CheqiApiError, CheqiSDKError, ErrorCodes, ReceiptProcessingError
from cheqi.http.client import CheqiApiClient
from cheqi.models.download import (
    ClientReceiptDownloadRequest,
    ClientReceiptDownloadResponse,
    DownloadLink,
)
from cheqi.models.encryption import EncryptedReceiptRequestDto, NotificationDisplayCode
from cheqi.models.enums import ReceiptFormat
from cheqi.models.envelopes import ReceiptCreatedResponse, ReceiptEnvelope, ReceiptResult
from cheqi.models.matching import (
    DeliveryRouteType,
    IdentificationDetails,
    Recipient,
    RecipientResolutionResponse,
)
from cheqi.models.receipt import CheqiReceipt, ReceiptTemplateRequest, ReceiptTemplateResponse
from cheqi.services.download import DownloadService
from cheqi.services.encryption import EncryptionService
from cheqi.services.matching import MatchingService
from cheqi.utils.hash import sha256_hex

logger = logging.getLogger("cheqi.receipt")


class ReceiptService:
    """End-to-end receipt workflow, including encrypted download fallback."""

    def __init__(
        self,
        api_client: CheqiApiClient,
        encryption_service: EncryptionService,
        matching_service: MatchingService,
        download_service: Optional[DownloadService] = None,
        receipt_download_base_url: Optional[str] = None,
    ) -> None:
        self._api_client = api_client
        self._encryption_service = encryption_service
        self._matching_service = matching_service
        self._download_service = download_service or DownloadService()
        self._receipt_download_base_url = receipt_download_base_url

    def process_complete_receipt(
        self,
        identification_details: IdentificationDetails,
        receipt_request: ReceiptTemplateRequest,
        access_token: Optional[str] = None,
        notification_display_code: Optional[NotificationDisplayCode] = None,
    ) -> ReceiptResult:
        """Match, template, encrypt, and deliver a receipt using the selected route."""
        self._require_not_none(identification_details, "PaymentDetails")
        self._require_not_none(receipt_request, "ReceiptTemplateRequest")
        if access_token is not None and not access_token.strip():
            self._validation_error("Access token cannot be null or empty")

        try:
            try:
                match_response = self._matching_service.match_customer(identification_details, access_token)
            except CheqiSDKError as exc:
                if self._is_deferred_failure(exc):
                    link = self._create_download_link()
                    return ReceiptResult.pending_download_template(link.url, str(exc))
                raise

            if match_response.route_found and match_response.delivery_route_type is None:
                raise ReceiptProcessingError(
                    "Matching response did not include deliveryRouteType; "
                    "refusing legacy fallback-compatible submission"
                )

            if not match_response.route_found and not (identification_details.recipient_email or "").strip():
                logger.info("Customer not found and no email provided - skipping template generation")
                return ReceiptResult.customer_not_found()

            formats = self._determine_formats(match_response)
            enriched_request = receipt_request.model_copy(
                update={
                    "buyer_country_code": receipt_request.buyer_country_code or match_response.buyer_country_code,
                    "buyer_type": receipt_request.buyer_type or match_response.buyer_type,
                    "taxes_applied": self._resolve_taxes_applied(receipt_request),
                }
            )

            try:
                template_response = self.generate_receipt_template(enriched_request, formats, access_token)
            except CheqiSDKError as exc:
                if self._is_deferred_failure(exc):
                    link = self._create_download_link()
                    return ReceiptResult.pending_download_template(link.url, str(exc))
                raise

            if match_response.route_found:
                if match_response.delivery_route_type is DeliveryRouteType.DOWNLOAD_FALLBACK:
                    return self._deliver_client_encrypted_download(
                        self._create_download_link(), template_response, access_token
                    )
                return self._deliver_encrypted_receipts(
                    match_response,
                    template_response,
                    notification_display_code,
                    access_token,
                )

            logger.info("Customer not found, sending receipt via email")
            return self.send_receipt_via_email(
                identification_details.recipient_email or "", template_response.cheqi, access_token
            )
        except CheqiSDKError:
            raise
        except Exception as exc:
            logger.error("Receipt processing failed: %s", exc)
            raise ReceiptProcessingError(f"Receipt processing failed: {exc}") from exc

    def generate_receipt_template(
        self,
        request: ReceiptTemplateRequest,
        receipt_formats: List[ReceiptFormat],
        access_token: Optional[str] = None,
    ) -> ReceiptTemplateResponse:
        self._require_not_none(request, "Receipt template request")
        return self._api_client.generate_receipt_template(request, receipt_formats, access_token)

    def upload_client_encrypted_receipt(
        self,
        request: ClientReceiptDownloadRequest,
        access_token: Optional[str] = None,
    ) -> ClientReceiptDownloadResponse:
        """Upload exact ciphertext for a client-generated receipt link."""
        self._require_not_none(request, "Client receipt download request")
        return self._api_client.upload_client_encrypted_receipt(request, access_token)

    def create_encrypted_receipts(
        self,
        receipt_json: str,
        recipient: Recipient,
        notification_display_code: Optional[NotificationDisplayCode] = None,
    ) -> EncryptedReceiptRequestDto:
        """Encrypt one recipient envelope with a fresh AES-256 key."""
        if not receipt_json or not receipt_json.strip():
            self._validation_error("Purchase receipt cannot be null or empty")
        self._require_not_none(recipient, "Recipient")
        encrypted = self._encryption_service.encrypt_receipt_for_recipient(receipt_json, recipient)
        if notification_display_code is not None:
            encrypted = encrypted.model_copy(update={"notification_display_code": notification_display_code})
        return encrypted

    def send_encrypted_receipts(
        self,
        encrypted_receipts: List[EncryptedReceiptRequestDto],
        template_hash: str,
        match_response: RecipientResolutionResponse,
        access_token: Optional[str] = None,
    ) -> ReceiptCreatedResponse:
        if not encrypted_receipts:
            self._validation_error("Encrypted receipts cannot be null or empty")
        if not template_hash or not template_hash.strip():
            self._validation_error("Template hash cannot be null or empty")
        if not match_response or not match_response.route_found:
            raise CheqiSDKError(
                "Cannot send receipts: customer was not found during matching",
                error_code=ErrorCodes.CUSTOMER_NOT_FOUND,
                http_status_code=400,
            )
        return self._api_client.send_encrypted_receipts(
            match_response.match_id or "", encrypted_receipts, template_hash, access_token
        )

    def send_receipt_via_email(
        self,
        customer_email: str,
        cheqi_receipt: Optional[CheqiReceipt],
        access_token: Optional[str] = None,
    ) -> ReceiptResult:
        if not customer_email or not customer_email.strip() or "@" not in customer_email:
            self._validation_error("Valid customer email is required")
        self._require_not_none(cheqi_receipt, "Purchase receipt")
        assert cheqi_receipt is not None
        self._api_client.send_receipt_via_email(customer_email, cheqi_receipt.to_json(), access_token)
        return ReceiptResult.delivered_via_email(customer_email)

    def _deliver_encrypted_receipts(
        self,
        match_response: RecipientResolutionResponse,
        template_response: ReceiptTemplateResponse,
        notification_display_code: Optional[NotificationDisplayCode],
        access_token: Optional[str],
    ) -> ReceiptResult:
        encrypted_receipts: List[EncryptedReceiptRequestDto] = []
        for recipient in match_response.recipients or []:
            envelope = self._build_envelope_for_recipient(recipient, template_response)
            encrypted_receipts.append(
                self.create_encrypted_receipts(envelope.to_json(), recipient, notification_display_code)
            )

        template_content = self._template_content(template_response)
        response = self.send_encrypted_receipts(
            encrypted_receipts, sha256_hex(template_content), match_response, access_token
        )
        if response.download_url:
            return ReceiptResult.delivered_via_download(response, template_content)
        return ReceiptResult.delivered_to_app(response, template_content)

    def _deliver_client_encrypted_download(
        self,
        link: DownloadLink,
        template_response: ReceiptTemplateResponse,
        access_token: Optional[str],
    ) -> ReceiptResult:
        envelope = self._download_service.build_download_envelope(template_response)
        canonical_json = template_response.cheqi.to_json() if template_response.cheqi else "null"
        template_hash = sha256_hex(canonical_json)
        ciphertext = self._download_service.encrypt_download_envelope(envelope, link.content_key)
        request = ClientReceiptDownloadRequest(
            download_id=link.download_id,
            ciphertext=ciphertext,
            template_hash=template_hash,
        )
        try:
            response = self.upload_client_encrypted_receipt(request, access_token)
            return ReceiptResult.delivered_via_client_download(
                response, template_hash, canonical_json, link.url
            )
        except CheqiSDKError as exc:
            if self._is_deferred_failure(exc):
                return ReceiptResult.pending_download_upload(
                    link.url, ciphertext, template_hash, canonical_json, str(exc)
                )
            raise

    def _create_download_link(self) -> DownloadLink:
        if not self._receipt_download_base_url or not self._receipt_download_base_url.strip():
            raise ReceiptProcessingError(
                "Receipt download base URL is required for automatic encrypted fallback; "
                "configure a standard Environment or receipt_download_base_url"
            )
        return self._download_service.generate_download_link(self._receipt_download_base_url)

    @staticmethod
    def _determine_formats(match_response: RecipientResolutionResponse) -> List[ReceiptFormat]:
        formats: List[ReceiptFormat] = []
        for recipient in match_response.recipients or []:
            for receipt_format in recipient.accepted_formats or []:
                if receipt_format not in formats:
                    formats.append(receipt_format)
        return formats

    @staticmethod
    def _resolve_taxes_applied(request: ReceiptTemplateRequest) -> bool:
        if request.taxes_applied is not None:
            return request.taxes_applied
        if request.total_tax_amount is not None and request.total_tax_amount > Decimal("0"):
            return True
        return bool(request.taxes)

    @staticmethod
    def _template_content(template: ReceiptTemplateResponse) -> str:
        if template.cheqi:
            return template.cheqi.to_json()
        return template.ubl_purchase_receipt or template.ubl_invoice or ""

    @staticmethod
    def _build_envelope_for_recipient(
        recipient: Recipient, template_response: ReceiptTemplateResponse
    ) -> ReceiptEnvelope:
        accepted = recipient.accepted_formats or []
        return ReceiptEnvelope(
            cheqi=template_response.cheqi if ReceiptFormat.CHEQI in accepted else None,
            ubl_purchase_receipt=(
                template_response.ubl_purchase_receipt
                if ReceiptFormat.UBL_PURCHASE_RECEIPT in accepted
                else None
            ),
            ubl_invoice=(
                template_response.ubl_invoice if ReceiptFormat.UBL_INVOICE in accepted else None
            ),
            vat_metadata=template_response.vat_metadata,
        )

    @staticmethod
    def _is_deferred_failure(error: BaseException) -> bool:
        current: Optional[BaseException] = error
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if isinstance(current, CheqiApiError):
                return (
                    current.error_code == ErrorCodes.NETWORK_ERROR
                    or current.http_status_code in (408, 429)
                    or current.http_status_code >= 500
                )
            current = current.__cause__ or current.__context__
        return False

    @staticmethod
    def _require_not_none(value: object, name: str) -> None:
        if value is None:
            ReceiptService._validation_error(f"{name} cannot be null")

    @staticmethod
    def _validation_error(message: str) -> None:
        raise CheqiSDKError(message, error_code=ErrorCodes.VALIDATION_ERROR, http_status_code=400)
