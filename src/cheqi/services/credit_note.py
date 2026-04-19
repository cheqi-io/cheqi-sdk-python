"""Credit note service for end-to-end credit note processing."""

from __future__ import annotations

import logging
from typing import List, Optional

from cheqi.exceptions import CheqiSDKError, CreditNoteProcessingError, ErrorCodes
from cheqi.http.client import CheqiApiClient
from cheqi.models.credit_note import (
    CreditNoteCreatedResponse,
    DecryptedDeliveredCreditNote,
    CreditNoteEnvelope,
    CreditNoteResult,
    CreditNoteTemplateGenerationRequest,
    CreditNoteTemplateRequest,
    CreditNoteTemplateResponse,
    EncryptedCreditNote,
    EncryptedCreditNoteInitiationRequest,
)
from cheqi.models.generated.encrypted_credit_note_dto import EncryptedCreditNoteDto
from cheqi.models.enums import ReceiptFormat
from cheqi.models.matching import (
    IdentificationDetails,
    Recipient,
    RecipientResolutionResponse,
)
from cheqi.services.decryption import DecryptedCreditNote, DecryptionService
from cheqi.services.encryption import EncryptionService
from cheqi.services.matching import MatchingService
from cheqi.utils.hash import sha256_hex

logger = logging.getLogger("cheqi.credit_note")


class CreditNoteService:
    """Service for handling credit note operations."""

    def __init__(
        self,
        api_client: CheqiApiClient,
        encryption_service: EncryptionService,
        matching_service: MatchingService,
    ) -> None:
        self._api_client = api_client
        self._encryption_service = encryption_service
        self._matching_service = matching_service

    def process_complete_credit_note(
        self,
        identification_details: IdentificationDetails,
        credit_note_request: CreditNoteTemplateRequest,
        parent_cheqi_receipt_id: str,
        access_token: Optional[str] = None,
    ) -> CreditNoteResult:
        """Complete credit note processing workflow.

        1. Match customer
        2. Generate credit note template
        3. Encrypt for all recipients
        4. Send to backend
        """
        try:
            match_response = self._matching_service.match_customer(
                identification_details, access_token
            )

            if not match_response.customer_found:
                return CreditNoteResult.customer_not_found()

            # Determine formats
            determined_formats: List[ReceiptFormat] = []
            if match_response.recipients:
                seen: set[ReceiptFormat] = set()
                for r in match_response.recipients:
                    if r.accepted_formats:
                        for fmt in r.accepted_formats:
                            if fmt not in seen:
                                seen.add(fmt)
                                determined_formats.append(fmt)

            # Generate template
            gen_request = CreditNoteTemplateGenerationRequest(
                credit_note_template_request=credit_note_request,
                receipt_formats=determined_formats,
            )
            template_response = self._api_client.generate_credit_note_template(
                gen_request, access_token
            )

            # Build encrypted credit notes
            encrypted_notes = self._build_encrypted_credit_notes(
                match_response, template_response
            )

            # Compute hash
            template_content = (
                template_response.cheqi.to_json()
                if template_response.cheqi
                else template_response.ubl or ""
            )
            template_hash = sha256_hex(template_content)

            # Send
            created_response = self._api_client.send_encrypted_credit_notes(
                match_response.match_id or "",
                parent_cheqi_receipt_id,
                encrypted_notes,
                template_hash,
                access_token,
            )

            return CreditNoteResult.delivered_to_app(created_response, template_content)

        except CheqiSDKError:
            raise
        except Exception as e:
            logger.error("Credit note processing failed: %s", e)
            raise CreditNoteProcessingError(f"Credit note processing failed: {e}") from e

    def generate_credit_note_template(
        self,
        request: CreditNoteTemplateRequest,
        receipt_formats: List[ReceiptFormat],
        access_token: Optional[str] = None,
    ) -> CreditNoteTemplateResponse:
        """Generate a credit note template from transaction data."""
        gen_request = CreditNoteTemplateGenerationRequest(
            credit_note_template_request=request,
            receipt_formats=receipt_formats,
        )
        return self._api_client.generate_credit_note_template(gen_request, access_token)

    def decrypt_credit_note_request(
        self,
        encrypted_request: EncryptedCreditNoteInitiationRequest,
        private_key_b64: str,
    ) -> DecryptedCreditNote:
        """Decrypt an encrypted credit note initiation request."""
        decryption_service = DecryptionService()
        return decryption_service.decrypt_credit_note(encrypted_request, private_key_b64)

    def decrypt_delivered_credit_note(
        self,
        encrypted_credit_note: EncryptedCreditNoteDto,
        private_key_b64: str,
    ) -> DecryptedDeliveredCreditNote:
        """Decrypt and merge a delivered encrypted credit note."""
        decryption_service = DecryptionService()
        decrypted = decryption_service.decrypt_credit_note_payload(
            encrypted_credit_note, private_key_b64
        )
        return self._merge_credit_note_context(decrypted)

    def _build_encrypted_credit_notes(
        self,
        match_response: RecipientResolutionResponse,
        template_response: CreditNoteTemplateResponse,
    ) -> List[EncryptedCreditNote]:
        """Build encrypted credit notes for all recipients."""
        encrypted_notes: List[EncryptedCreditNote] = []

        for recipient in match_response.recipients or []:
            envelope = self._build_envelope_for_recipient(recipient, template_response)
            envelope_json = envelope.to_json()

            encrypted = self._encryption_service.encrypt_credit_note_for_recipient(
                envelope_json, recipient
            )

            encrypted_with_formats = EncryptedCreditNote(
                recipient_id=encrypted.recipient_id,
                receiver_type=encrypted.receiver_type,
                public_key=encrypted.public_key,
                encrypted_credit_note=encrypted.encrypted_credit_note,
                encrypted_symmetric_key=encrypted.encrypted_symmetric_key,
                receipt_formats=recipient.accepted_formats,
            )
            encrypted_notes.append(encrypted_with_formats)

        return encrypted_notes

    def _build_envelope_for_recipient(
        self,
        recipient: Recipient,
        template_response: CreditNoteTemplateResponse,
    ) -> CreditNoteEnvelope:
        """Build a credit note envelope with formats accepted by the recipient."""
        cheqi_credit_note = None
        ubl_credit_note = None

        accepted = recipient.accepted_formats or []

        if ReceiptFormat.CHEQI in accepted and template_response.cheqi:
            cheqi_credit_note = template_response.cheqi
        if ReceiptFormat.UBL_XML in accepted and template_response.ubl:
            ubl_credit_note = template_response.ubl

        return CreditNoteEnvelope(
            cheqi_credit_note=cheqi_credit_note,
            ubl_credit_note=ubl_credit_note,
            vat_metadata=template_response.vat_metadata,
        )

    def _merge_credit_note_context(
        self, decrypted: DecryptedDeliveredCreditNote
    ) -> DecryptedDeliveredCreditNote:
        context = decrypted.credit_note_context_envelope
        if context is None:
            return decrypted

        envelope = decrypted.credit_note_envelope.model_copy(deep=True)

        xml_receiving_party = None
        receiving_party = None
        xml_payment_means = None
        if context.receiving_party is not None:
            xml_receiving_party = context.receiving_party.xml_receiving_party
            receiving_party = context.receiving_party.receiving_party
        if context.payment_means is not None:
            xml_payment_means = context.payment_means.xml_payment_means

        if envelope.ubl_credit_note and xml_receiving_party:
            envelope.ubl_credit_note = envelope.ubl_credit_note.replace(
                "<cac:AccountingCustomerParty/>", xml_receiving_party
            )

        if envelope.ubl_credit_note and xml_payment_means:
            if "</cac:AccountingCustomerParty>" in envelope.ubl_credit_note:
                envelope.ubl_credit_note = envelope.ubl_credit_note.replace(
                    "</cac:AccountingCustomerParty>",
                    "</cac:AccountingCustomerParty>" + xml_payment_means,
                )
            elif "<cac:AccountingCustomerParty/>" in envelope.ubl_credit_note:
                envelope.ubl_credit_note = envelope.ubl_credit_note.replace(
                    "<cac:AccountingCustomerParty/>",
                    "<cac:AccountingCustomerParty/>" + xml_payment_means,
                )

        if envelope.cheqi_credit_note and receiving_party:
            envelope.cheqi_credit_note = envelope.cheqi_credit_note.model_copy(
                update={"receiving_party": receiving_party}
            )

        return DecryptedDeliveredCreditNote(
            credit_note_envelope=envelope,
            credit_note_context_envelope=context,
            raw_json=decrypted.raw_json,
            raw_credit_note_context_json=decrypted.raw_credit_note_context_json,
        )
