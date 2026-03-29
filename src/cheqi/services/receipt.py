"""Receipt service for end-to-end receipt processing."""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from cheqi.exceptions import CheqiSDKError, ErrorCodes, ReceiptProcessingError
from cheqi.http.client import CheqiApiClient
from cheqi.models.encryption import EncryptedReceiptRequestDto, NotificationDisplayCode
from cheqi.models.enums import ReceiptFormat
from cheqi.models.envelopes import ReceiptCreatedResponse, ReceiptEnvelope, ReceiptResult
from cheqi.models.matching import (
    IdentificationDetails,
    Recipient,
    RecipientResolutionResponse,
)
from cheqi.models.receipt import CheqiReceipt, ReceiptTemplateRequest, ReceiptTemplateResponse
from cheqi.services.encryption import EncryptionService
from cheqi.services.matching import MatchingService
from cheqi.utils.hash import sha256_hex

logger = logging.getLogger("cheqi.receipt")


class ReceiptService:
    """Service for handling receipt operations.

    Provides:
    - Complete receipt processing (match -> template -> encrypt -> send)
    - Receipt template generation
    - Encrypted receipt creation
    - Receipt delivery (app or email)
    """

    def __init__(
        self,
        api_client: CheqiApiClient,
        encryption_service: EncryptionService,
        matching_service: MatchingService,
    ) -> None:
        self._api_client = api_client
        self._encryption_service = encryption_service
        self._matching_service = matching_service

    def process_complete_receipt(
        self,
        identification_details: IdentificationDetails,
        receipt_request: ReceiptTemplateRequest,
        access_token: Optional[str] = None,
        notification_display_code: Optional[NotificationDisplayCode] = None,
    ) -> ReceiptResult:
        """Complete receipt processing workflow.

        1. Match customer using payment details
        2. Generate receipt template (only if deliverable)
        3. If customer found: encrypt and send to backend
        4. If not found but email provided: send via email
        """
        if identification_details is None:
            raise CheqiSDKError(
                "PaymentDetails cannot be null",
                error_code=ErrorCodes.VALIDATION_ERROR,
                http_status_code=400,
            )
        if receipt_request is None:
            raise CheqiSDKError(
                "ReceiptTemplateRequest cannot be null",
                error_code=ErrorCodes.VALIDATION_ERROR,
                http_status_code=400,
            )

        try:
            # Step 1: Match customer
            match_response = self._matching_service.match_customer(
                identification_details, access_token
            )

            # Early exit if no match and no email
            if not match_response.customer_found and not identification_details.recipient_email:
                logger.info("Customer not found and no email provided - skipping template generation")
                return ReceiptResult.customer_not_found()

            # Determine receipt formats from recipients
            determined_formats: List[ReceiptFormat] = []
            if match_response.recipients:
                seen: set[ReceiptFormat] = set()
                for r in match_response.recipients:
                    if r.accepted_formats:
                        for fmt in r.accepted_formats:
                            if fmt not in seen:
                                seen.add(fmt)
                                determined_formats.append(fmt)

            # Enrich request with VAT context from match response
            enriched_request = receipt_request.model_copy(
                update={
                    "buyer_country_code": receipt_request.buyer_country_code
                    or match_response.buyer_country_code,
                    "recipient_entity_type": receipt_request.recipient_entity_type
                    or match_response.recipient_entity_type,
                }
            )

            # Step 2: Generate receipt template
            template_response = self.generate_receipt_template(
                enriched_request, determined_formats, access_token
            )

            if match_response.customer_found:
                # Step 3: Build encrypted receipts
                encrypted_receipts = self._build_encrypted_receipts(
                    match_response,
                    template_response,
                    notification_display_code,
                )

                # Compute template hash
                template_content = (
                    template_response.cheqi.to_json()
                    if template_response.cheqi
                    else template_response.ubl_purchase_receipt or ""
                )
                template_hash = sha256_hex(template_content)

                # Step 4: Send encrypted receipts
                created_response = self.send_encrypted_receipts(
                    encrypted_receipts,
                    template_hash,
                    match_response,
                    access_token,
                )

                return ReceiptResult.delivered_to_app(created_response, template_content)

            # Customer not found, send via email
            logger.info("Customer not found, sending receipt via email")
            return self.send_receipt_via_email(
                identification_details.recipient_email or "",
                template_response.cheqi,
                access_token,
            )

        except CheqiSDKError:
            raise
        except Exception as e:
            logger.error("Receipt processing failed: %s", e)
            raise ReceiptProcessingError(f"Receipt processing failed: {e}") from e

    def generate_receipt_template(
        self,
        request: ReceiptTemplateRequest,
        receipt_formats: List[ReceiptFormat],
        access_token: Optional[str] = None,
    ) -> ReceiptTemplateResponse:
        """Generate a receipt template from transaction data."""
        if request is None:
            raise CheqiSDKError(
                "Receipt template request cannot be null",
                error_code=ErrorCodes.VALIDATION_ERROR,
                http_status_code=400,
            )
        return self._api_client.generate_receipt_template(request, receipt_formats, access_token)

    def create_encrypted_receipts(
        self,
        receipt_json: str,
        recipient: Recipient,
        notification_display_code: Optional[NotificationDisplayCode] = None,
    ) -> EncryptedReceiptRequestDto:
        """Encrypt a receipt for a single recipient."""
        if not receipt_json or not receipt_json.strip():
            raise CheqiSDKError(
                "Purchase receipt cannot be null or empty",
                error_code=ErrorCodes.VALIDATION_ERROR,
                http_status_code=400,
            )
        if recipient is None:
            raise CheqiSDKError(
                "Recipient cannot be null",
                error_code=ErrorCodes.VALIDATION_ERROR,
                http_status_code=400,
            )
        encrypted_receipt = self._encryption_service.encrypt_receipt_for_recipient(receipt_json, recipient)
        if notification_display_code is None:
            return encrypted_receipt
        return encrypted_receipt.model_copy(
            update={"notification_display_code": notification_display_code}
        )

    def send_encrypted_receipts(
        self,
        encrypted_receipts: List[EncryptedReceiptRequestDto],
        template_hash: str,
        match_response: RecipientResolutionResponse,
        access_token: Optional[str] = None,
    ) -> ReceiptCreatedResponse:
        """Send encrypted receipts to the backend for delivery."""
        if not encrypted_receipts:
            raise CheqiSDKError(
                "Encrypted receipts cannot be null or empty",
                error_code=ErrorCodes.VALIDATION_ERROR,
                http_status_code=400,
            )
        if not template_hash or not template_hash.strip():
            raise CheqiSDKError(
                "Template hash cannot be null or empty",
                error_code=ErrorCodes.VALIDATION_ERROR,
                http_status_code=400,
            )
        if not match_response or not match_response.customer_found:
            raise CheqiSDKError(
                "Cannot send receipts: customer was not found during matching",
                error_code=ErrorCodes.CUSTOMER_NOT_FOUND,
                http_status_code=400,
            )

        return self._api_client.send_encrypted_receipts(
            match_response.match_id or "",
            encrypted_receipts,
            template_hash,
            access_token,
        )

    def send_receipt_via_email(
        self,
        customer_email: str,
        cheqi_receipt: Optional[CheqiReceipt],
        access_token: Optional[str] = None,
    ) -> ReceiptResult:
        """Send a receipt via email as fallback delivery."""
        if not customer_email or not customer_email.strip() or "@" not in customer_email:
            raise CheqiSDKError(
                "Valid customer email is required",
                error_code=ErrorCodes.VALIDATION_ERROR,
                http_status_code=400,
            )
        if cheqi_receipt is None:
            raise CheqiSDKError(
                "Purchase receipt cannot be null",
                error_code=ErrorCodes.VALIDATION_ERROR,
                http_status_code=400,
            )

        receipt_json = cheqi_receipt.to_json()
        self._api_client.send_receipt_via_email(customer_email, receipt_json, access_token)
        return ReceiptResult.delivered_via_email(customer_email)

    def _build_encrypted_receipts(
        self,
        match_response: RecipientResolutionResponse,
        template_response: ReceiptTemplateResponse,
        notification_display_code: Optional[NotificationDisplayCode] = None,
    ) -> List[EncryptedReceiptRequestDto]:
        """Build encrypted receipts for all matched recipients."""
        encrypted_receipts: List[EncryptedReceiptRequestDto] = []

        for recipient in match_response.recipients or []:
            envelope = self._build_envelope_for_recipient(recipient, template_response)
            envelope_json = envelope.to_json()

            encrypted = self._encryption_service.encrypt_receipt_for_recipient(
                envelope_json, recipient
            )

            # Add accepted formats to the encrypted receipt
            encrypted_with_formats = EncryptedReceiptRequestDto(
                recipient_id=encrypted.recipient_id,
                receiver_type=encrypted.receiver_type,
                receipt_formats=recipient.accepted_formats,
                encrypted_receipt=encrypted.encrypted_receipt,
                encrypted_symmetric_key=encrypted.encrypted_symmetric_key,
                public_key=encrypted.public_key,
                notification_display_code=notification_display_code,
            )
            encrypted_receipts.append(encrypted_with_formats)

        return encrypted_receipts

    def _build_envelope_for_recipient(
        self,
        recipient: Recipient,
        template_response: ReceiptTemplateResponse,
    ) -> ReceiptEnvelope:
        """Build a receipt envelope with only the formats accepted by the recipient."""
        cheqi_receipt = None
        ubl_purchase_receipt = None
        vat_metadata = template_response.vat_metadata

        accepted = recipient.accepted_formats or []

        if ReceiptFormat.CHEQI in accepted and template_response.cheqi:
            cheqi_receipt = template_response.cheqi

        if ReceiptFormat.UBL_PURCHASE_RECEIPT in accepted and template_response.ubl_purchase_receipt:
            ubl_purchase_receipt = template_response.ubl_purchase_receipt

        return ReceiptEnvelope(
            cheqi_receipt=cheqi_receipt,
            ubl_purchase_receipt=ubl_purchase_receipt,
            vat_metadata=vat_metadata,
        )
