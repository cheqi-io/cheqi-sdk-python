"""Issue definitive credit-note payloads through encrypted device processing."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, NoReturn, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel

from cheqi.exceptions import CheqiSDKError, CreditNoteProcessingError, ErrorCodes
from cheqi.http.client import CheqiApiClient
from cheqi.http.request_options import RequestOptions
from cheqi.models.credit_note import CreditNoteResult
from cheqi.models.generated.client_receipt_download_request import ClientReceiptDownloadRequest
from cheqi.models.generated.credit_note_document_reference import CreditNoteDocumentReference
from cheqi.models.generated.encrypted_credit_note_envelope import EncryptedCreditNoteEnvelope
from cheqi.models.generated.identification_details import IdentificationDetails
from cheqi.models.generated.matched_recipient import MatchedRecipient
from cheqi.models.generated.prepared_credit_note import PreparedCreditNote
from cheqi.models.generated.receipt_envelope import ReceiptEnvelope
from cheqi.models.generated.receipt_envelope_document import ReceiptEnvelopeDocument
from cheqi.models.generated.receipt_submission_response import ReceiptSubmissionResponse
from cheqi.models.generated.recipient_resolution_response import RecipientResolutionResponse
from cheqi.services.document_reference import document_reference_hash
from cheqi.services.download import DownloadService
from cheqi.services.encryption import EncryptionService
from cheqi.services.matching import MatchingService


class CreditNoteService:
    """Match, encrypt, and submit an issuer-supplied credit-note payload."""

    def __init__(
        self,
        api_client: CheqiApiClient,
        encryption_service: EncryptionService,
        matching_service: MatchingService,
    ) -> None:
        self._api_client = api_client
        self._encryption_service = encryption_service
        self._matching_service = matching_service

    def prepare_credit_note(
        self, payload: Any, *, store_id: Optional[UUID] = None, options: Optional[RequestOptions] = None
    ) -> PreparedCreditNote:
        """Resolve originatorDocumentReference and encrypt for the original route."""
        if isinstance(payload, BaseModel):
            node = json.loads(payload.model_dump_json(by_alias=True, exclude_none=True), parse_float=Decimal)
        elif isinstance(payload, str):
            node = json.loads(payload, parse_float=Decimal)
        else:
            node = payload
        body = node.get("creditNoteTemplateRequest", node) if isinstance(node, dict) else None
        if not isinstance(body, dict) or not isinstance(body.get("originatorDocumentReference"), str):
            self._validation_error("originatorDocumentReference must contain the original documentNumber")
        reference = body["originatorDocumentReference"]
        self._require_text(reference, "originatorDocumentReference")
        original = self._api_client.resolve_credit_note_reference(
            CreditNoteDocumentReference(document_reference_hash=document_reference_hash(reference)), options=options
        )
        parent = original.parent_cheqi_receipt_id
        self._require_text(parent, "resolved parentCheqiReceiptId")
        assert parent is not None
        if original.delivery_route == "DIGITAL":
            if not isinstance(node.get("taxesApplied"), bool):
                self._validation_error("taxesApplied must be a boolean for device generation")
            match = self._matching_service.match_customer(
                IdentificationDetails(cheqi_receipt_id=parent), options=options
            )
            self._validate_device_route(match)
            if match.delivery_route_type != "DIGITAL":
                self._validation_error("Original owner-device route is unavailable")
            generation = (
                node
                if "creditNoteTemplateRequest" in node
                else {"taxesApplied": node["taxesApplied"], "creditNoteTemplateRequest": body}
            )
            plaintext = self._reference_json(generation)
            deliveries = [self._encryption_service.encrypt_for_device(plaintext, r) for r in match.recipients or []]
            return PreparedCreditNote(
                parent_cheqi_receipt_id=parent,
                device_submission=EncryptedCreditNoteEnvelope(
                    match_id=match.match_id,
                    parent_cheqi_receipt_id=parent,
                    store_id=str(store_id) if store_id else original.store_id,
                    device_deliveries=deliveries,
                ),
            )
        if original.delivery_route != "DOWNLOAD":
            self._validation_error("Unsupported original document route")
        if store_id is not None:
            self._validation_error("Download delivery does not support store-scoped issuance")
        self._require_text(original.credit_note_public_key, "creditNotePublicKey")
        downloads = DownloadService()
        child = downloads.generate_download_link(DownloadService.PRODUCTION_BASE_URL)
        envelope = ReceiptEnvelope(
            envelope_version=2,
            cheqi_receipt_id=child.download_id,
            receipt_uuid=str(uuid4()),
            receipt_generator_version="credit-note-payload-v1",
            documents={
                "CREDIT_NOTE_PAYLOAD": ReceiptEnvelopeDocument(
                    media_type="application/json", content=self._reference_json(body)
                )
            },
        )
        link = self._encryption_service.encrypt_for_device(
            self._reference_json(
                {
                    "version": 2,
                    "parentCheqiReceiptId": parent,
                    "downloadId": child.download_id,
                    "contentKey": child.content_key,
                }
            ),
            MatchedRecipient(id=parent, public_key=original.credit_note_public_key),
        )
        return PreparedCreditNote(
            parent_cheqi_receipt_id=parent,
            download_submission=ClientReceiptDownloadRequest(
                download_id=child.download_id,
                ciphertext=downloads.encrypt_download_envelope(envelope, child.content_key),
                parent_cheqi_receipt_id=parent,
                encrypted_parent_link=link.encrypted_content,
                encrypted_parent_link_key=link.encrypted_aes_key,
            ),
        )

    def submit_prepared_credit_note(
        self, prepared: PreparedCreditNote, *, options: Optional[RequestOptions] = None
    ) -> CreditNoteResult:
        """Replay the persisted ciphertext without resolving or encrypting again."""
        self._require_text(prepared.parent_cheqi_receipt_id, "parentCheqiReceiptId")
        if (prepared.device_submission is None) == (prepared.download_submission is None):
            self._validation_error("Exactly one prepared submission is required")
        submission = prepared.device_submission or prepared.download_submission
        assert submission is not None
        if submission.parent_cheqi_receipt_id != prepared.parent_cheqi_receipt_id:
            self._validation_error("Credit-note parent mismatch")
        if prepared.device_submission is not None:
            response = self._api_client.submit_encrypted_credit_note(prepared.device_submission, options=options)
            if not response or response.match_id != prepared.device_submission.match_id:
                self._validation_error("Credit-note acceptance is not confirmed")
        else:
            assert prepared.download_submission is not None
            accepted = self._api_client.upload_encrypted_download_receipt(prepared.download_submission, options=options)
            response = ReceiptSubmissionResponse(
                cheqi_receipt_id=accepted.cheqi_receipt_id, created_at=accepted.created_at, status="COMPLETED"
            )
        self._require_text(response.cheqi_receipt_id, "accepted cheqiReceiptId")
        return CreditNoteResult.accepted(prepared.parent_cheqi_receipt_id, response)

    @staticmethod
    def _reference_json(value: Any) -> str:
        # Decimal monetary values use the same lossless decimal strings as receipt payloads.
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
            default=lambda v: str(v) if isinstance(v, Decimal) else CreditNoteService._json_default(v),
        )

    def issue_credit_note(
        self,
        identification_details: IdentificationDetails,
        parent_cheqi_receipt_id: str,
        credit_note_payload: Any,
        *,
        store_id: Optional[UUID] = None,
        options: Optional[RequestOptions] = None,
    ) -> CreditNoteResult:
        self._require_not_none(identification_details, "identification_details")
        self._require_text(parent_cheqi_receipt_id, "parent_cheqi_receipt_id")
        self._require_not_none(credit_note_payload, "credit_note_payload")
        try:
            resolution = self._matching_service.match_customer(identification_details, options=options)
            self._validate_device_route(resolution)
            plaintext_json = self._serialize_payload(credit_note_payload)
            deliveries = [
                self._encryption_service.encrypt_credit_note_for_recipient(
                    plaintext_json,
                    recipient,
                )
                for recipient in resolution.recipients or []
            ]
            envelope = EncryptedCreditNoteEnvelope(
                match_id=resolution.match_id,
                store_id=str(store_id) if store_id else None,
                parent_cheqi_receipt_id=parent_cheqi_receipt_id,
                device_deliveries=deliveries,
            )
            response = self._api_client.submit_encrypted_credit_note(envelope, options=options)
            return CreditNoteResult.accepted(parent_cheqi_receipt_id, response)
        except CheqiSDKError:
            raise
        except Exception as exc:
            raise CreditNoteProcessingError(f"Credit-note processing failed: {exc}") from exc

    def submit_encrypted_credit_note(
        self,
        envelope: EncryptedCreditNoteEnvelope,
        *,
        options: Optional[RequestOptions] = None,
    ) -> ReceiptSubmissionResponse:
        self._require_not_none(envelope, "envelope")
        return self._api_client.submit_encrypted_credit_note(envelope, options=options)

    @staticmethod
    def _serialize_payload(payload: Any) -> str:
        if isinstance(payload, str):
            if not payload.strip():
                CreditNoteService._validation_error("credit_note_payload cannot be empty")
            return payload
        if isinstance(payload, BaseModel):
            return payload.model_dump_json(by_alias=True, exclude_none=True)
        return json.dumps(
            payload,
            default=CreditNoteService._json_default,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @staticmethod
    def _json_default(value: object) -> object:
        if isinstance(value, Decimal):
            normalized = value.normalize()
            return int(normalized) if normalized == normalized.to_integral_value() else float(normalized)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, (Enum, UUID)):
            return value.value if isinstance(value, Enum) else str(value)
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    @staticmethod
    def _validate_device_route(resolution: RecipientResolutionResponse) -> None:
        if resolution is None or not resolution.route_found:
            raise CheqiSDKError(
                "No Cheqi owner-device route was found",
                error_code=ErrorCodes.CUSTOMER_NOT_FOUND,
                http_status_code=404,
            )
        CreditNoteService._require_text(resolution.match_id, "match_id")
        if not resolution.recipients:
            CreditNoteService._validation_error("Recipient resolution did not include owner devices")

    @staticmethod
    def _require_not_none(value: object, name: str) -> None:
        if value is None:
            CreditNoteService._validation_error(f"{name} cannot be None")

    @staticmethod
    def _require_text(value: Optional[str], name: str) -> None:
        if value is None or not value.strip():
            CreditNoteService._validation_error(f"{name} cannot be empty")

    @staticmethod
    def _validation_error(message: str) -> NoReturn:
        raise CheqiSDKError(
            message,
            error_code=ErrorCodes.VALIDATION_ERROR,
            http_status_code=400,
        )
