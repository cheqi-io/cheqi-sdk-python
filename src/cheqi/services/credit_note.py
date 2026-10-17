"""Issue definitive credit-note payloads through encrypted device processing."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel

from cheqi.exceptions import CheqiSDKError, CreditNoteProcessingError, ErrorCodes
from cheqi.http.client import CheqiApiClient
from cheqi.http.request_options import RequestOptions
from cheqi.models.credit_note import CreditNoteResult
from cheqi.models.generated.encrypted_credit_note_envelope import EncryptedCreditNoteEnvelope
from cheqi.models.generated.identification_details import IdentificationDetails
from cheqi.models.generated.receipt_submission_response import ReceiptSubmissionResponse
from cheqi.models.generated.recipient_resolution_response import RecipientResolutionResponse
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
    def _validation_error(message: str) -> None:
        raise CheqiSDKError(
            message,
            error_code=ErrorCodes.VALIDATION_ERROR,
            http_status_code=400,
        )
