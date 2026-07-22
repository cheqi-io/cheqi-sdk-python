"""End-to-end encrypted credit-note processing."""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from cheqi.exceptions import CheqiSDKError, CreditNoteProcessingError, ErrorCodes
from cheqi.http.client import CheqiApiClient
from cheqi.models.credit_note import (
    CreditNoteCreatedResponse,
    CreditNoteEnvelope,
    CreditNoteInitiationRequest,
    CreditNoteResult,
    CreditNoteTemplateGenerationRequest,
    CreditNoteTemplateRequest,
    CreditNoteTemplateResponse,
    DecryptedDeliveredCreditNote,
    EncryptedCreditNote,
    EncryptedCreditNoteInitiationRequest,
)
from cheqi.models.enums import ReceiptFormat
from cheqi.models.matching import IdentificationDetails, Recipient, RecipientResolutionResponse
from cheqi.services.decryption import DecryptionService
from cheqi.services.encryption import EncryptionService
from cheqi.services.matching import MatchingService
from cheqi.utils.hash import sha256_hex

logger = logging.getLogger("cheqi.credit_note")

_PARTY_PLACEHOLDER = "<cac:AccountingCustomerParty/>"
_PARTY_CLOSING_TAG = "</cac:AccountingCustomerParty>"


class CreditNoteService:
    """Match, template, encrypt, deliver, decrypt, and merge credit notes."""

    def __init__(
        self,
        api_client: CheqiApiClient,
        encryption_service: EncryptionService,
        matching_service: MatchingService,
    ) -> None:
        self._api_client = api_client
        self._encryption_service = encryption_service
        self._matching_service = matching_service
        self._decryption_service = DecryptionService()

    def process_complete_credit_note(
        self,
        identification_details: IdentificationDetails,
        credit_note_request: CreditNoteTemplateRequest,
        parent_cheqi_receipt_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> CreditNoteResult:
        """Run recipient resolution through encrypted credit-note delivery."""
        if identification_details is None or credit_note_request is None:
            self._validation_error("Identification details and credit note request are required")
        original_receipt_id = parent_cheqi_receipt_id or identification_details.cheqi_receipt_id
        if not original_receipt_id or not original_receipt_id.strip():
            self._validation_error("Original receipt ID (cheqiReceiptId) cannot be null or empty")
        assert original_receipt_id is not None

        try:
            match_response = self._matching_service.match_customer(identification_details, access_token)
            if not match_response.route_found and not (identification_details.recipient_email or "").strip():
                return CreditNoteResult.customer_not_found()

            formats = self._determine_formats(match_response)
            generation_request = CreditNoteTemplateGenerationRequest(
                credit_note_template_request=credit_note_request,
                formats=formats,
                buyer_country_code=match_response.buyer_country_code,
                buyer_type=match_response.buyer_type.value if match_response.buyer_type else None,
                taxes_applied=True,
            )
            template = self._api_client.generate_credit_note_template(generation_request, access_token)

            if not match_response.route_found:
                return CreditNoteResult.customer_not_found()

            encrypted_notes = self._build_encrypted_credit_notes(match_response, template)
            template_content = template.cheqi.to_json() if template.cheqi else template.ubl_credit_note or ""
            response = self.send_encrypted_credit_notes(
                original_receipt_id,
                encrypted_notes,
                sha256_hex(template_content),
                match_response,
                access_token,
            )
            return CreditNoteResult.delivered_to_app(response, template_content)
        except CheqiSDKError:
            raise
        except Exception as exc:
            logger.error("Credit note processing failed: %s", exc)
            raise CreditNoteProcessingError(f"Credit note processing failed: {exc}") from exc

    def generate_credit_note_template(
        self,
        request: CreditNoteTemplateRequest,
        receipt_formats: List[ReceiptFormat],
        access_token: Optional[str] = None,
    ) -> CreditNoteTemplateResponse:
        generation_request = CreditNoteTemplateGenerationRequest(
            credit_note_template_request=request,
            formats=receipt_formats,
            buyer_country_code=request.buyer_country_code,
            taxes_applied=True,
        )
        return self._api_client.generate_credit_note_template(generation_request, access_token)

    def send_encrypted_credit_notes(
        self,
        parent_cheqi_receipt_id: str,
        encrypted_credit_notes: List[EncryptedCreditNote],
        template_hash: str,
        match_response: RecipientResolutionResponse,
        access_token: Optional[str] = None,
    ) -> CreditNoteCreatedResponse:
        if not encrypted_credit_notes:
            self._validation_error("Encrypted credit notes cannot be empty")
        if not template_hash or not template_hash.strip():
            self._validation_error("Template hash cannot be null or empty")
        if not match_response or not match_response.route_found:
            raise CheqiSDKError(
                "Cannot send credit notes: customer was not found during matching",
                error_code=ErrorCodes.CUSTOMER_NOT_FOUND,
                http_status_code=400,
            )
        return self._api_client.send_encrypted_credit_notes(
            match_response.match_id or "",
            parent_cheqi_receipt_id,
            encrypted_credit_notes,
            template_hash,
            access_token,
        )

    def create_encrypted_credit_note(
        self, credit_note_envelope: str, recipient: Recipient
    ) -> EncryptedCreditNote:
        if not credit_note_envelope or not credit_note_envelope.strip():
            self._validation_error("Credit note envelope cannot be null or empty")
        if recipient is None:
            self._validation_error("Recipient cannot be null")
        return self._encryption_service.encrypt_credit_note_for_recipient(
            credit_note_envelope, recipient
        )

    def decrypt_credit_note_request(
        self,
        encrypted_request: EncryptedCreditNoteInitiationRequest,
        private_key_b64: str,
    ) -> CreditNoteInitiationRequest:
        """Decrypt and parse a customer credit-note initiation request."""
        decrypted = self._decryption_service.decrypt_credit_note(encrypted_request, private_key_b64)
        return CreditNoteInitiationRequest.model_validate(json.loads(decrypted.content))

    def decrypt_delivered_credit_note(
        self,
        encrypted_credit_note: EncryptedCreditNote,
        private_key_b64: str,
    ) -> DecryptedDeliveredCreditNote:
        decrypted = self._decryption_service.decrypt_credit_note_payload(
            encrypted_credit_note, private_key_b64
        )
        return self._merge_credit_note_context(decrypted)

    def _build_encrypted_credit_notes(
        self,
        match_response: RecipientResolutionResponse,
        template_response: CreditNoteTemplateResponse,
    ) -> List[EncryptedCreditNote]:
        return [
            self.create_encrypted_credit_note(
                self._build_envelope_for_recipient(recipient, template_response).to_json(), recipient
            )
            for recipient in match_response.recipients or []
        ]

    @staticmethod
    def _build_envelope_for_recipient(
        recipient: Recipient,
        template_response: CreditNoteTemplateResponse,
    ) -> CreditNoteEnvelope:
        accepted = recipient.accepted_formats or []
        return CreditNoteEnvelope(
            cheqi_credit_note=(
                template_response.cheqi if ReceiptFormat.CHEQI in accepted else None
            ),
            ubl_credit_note=(
                template_response.ubl_credit_note
                if ReceiptFormat.UBL_CREDIT_NOTE in accepted
                else None
            ),
        )

    @staticmethod
    def _determine_formats(match_response: RecipientResolutionResponse) -> List[ReceiptFormat]:
        formats: List[ReceiptFormat] = []
        for recipient in match_response.recipients or []:
            for receipt_format in recipient.accepted_formats or []:
                if receipt_format not in formats:
                    formats.append(receipt_format)
        return formats

    @staticmethod
    def _merge_credit_note_context(
        decrypted: DecryptedDeliveredCreditNote,
    ) -> DecryptedDeliveredCreditNote:
        context = decrypted.credit_note_context_envelope
        if context is None:
            return decrypted
        envelope = decrypted.credit_note_envelope
        party_context = context.receiving_party
        payment_context = context.payment_means
        xml = envelope.ubl_credit_note

        if xml and party_context and party_context.xml_receiving_party:
            xml = xml.replace(_PARTY_PLACEHOLDER, party_context.xml_receiving_party)
        if xml and payment_context and payment_context.xml_payment_means:
            if _PARTY_CLOSING_TAG in xml:
                xml = xml.replace(
                    _PARTY_CLOSING_TAG,
                    _PARTY_CLOSING_TAG + payment_context.xml_payment_means,
                )
            elif _PARTY_PLACEHOLDER in xml:
                xml = xml.replace(
                    _PARTY_PLACEHOLDER,
                    _PARTY_PLACEHOLDER + payment_context.xml_payment_means,
                )

        cheqi = envelope.cheqi_credit_note
        if cheqi and party_context and party_context.receiving_party:
            cheqi = cheqi.model_copy(update={"receiving_party": party_context.receiving_party})
        merged_envelope = envelope.model_copy(
            update={"ubl_credit_note": xml, "cheqi_credit_note": cheqi}
        )
        return decrypted.model_copy(update={"credit_note_envelope": merged_envelope})

    @staticmethod
    def _validation_error(message: str) -> None:
        raise CheqiSDKError(message, error_code=ErrorCodes.VALIDATION_ERROR, http_status_code=400)
