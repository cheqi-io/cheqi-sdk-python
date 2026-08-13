"""Issue definitive receipt payloads through encrypted device processing."""

from __future__ import annotations

import json
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel

from cheqi.exceptions import CheqiSDKError, ErrorCodes, ReceiptProcessingError
from cheqi.http.client import CheqiApiClient
from cheqi.models.download import DownloadLink
from cheqi.models.generated.client_receipt_download_request import ClientReceiptDownloadRequest
from cheqi.models.generated.encrypted_receipt_envelope import EncryptedReceiptEnvelope
from cheqi.models.generated.identification_details import IdentificationDetails
from cheqi.models.generated.receipt_envelope import ReceiptEnvelope
from cheqi.models.generated.receipt_envelope_document import ReceiptEnvelopeDocument
from cheqi.models.generated.receipt_payload import ReceiptPayload as GeneratedReceiptPayload
from cheqi.models.generated.receipt_submission_response import ReceiptSubmissionResponse
from cheqi.models.generated.recipient_resolution_response import RecipientResolutionResponse
from cheqi.models.receipt import DeliveryRouteType, ReceiptResult
from cheqi.services.download import DownloadService
from cheqi.services.encryption import EncryptionService
from cheqi.services.matching import MatchingService
from cheqi.services.verification import VerificationService

_PAYLOAD_DOCUMENT_VERSION = "receipt-payload-v1"


def _model_dict(model: BaseModel) -> dict[str, object]:
    return model.model_dump(by_alias=True, exclude_none=True, mode="json")


def _model_json(model: BaseModel) -> str:
    return model.model_dump_json(by_alias=True, exclude_none=True)


class ReceiptService:
    """Match, route, encrypt, and submit issuer-supplied receipt values."""

    def __init__(
        self,
        api_client: CheqiApiClient,
        encryption_service: EncryptionService,
        matching_service: MatchingService,
        download_service: Optional[DownloadService] = None,
        receipt_download_base_url: Optional[str] = DownloadService.PRODUCTION_BASE_URL,
    ) -> None:
        self._api_client = api_client
        self._encryption_service = encryption_service
        self._matching_service = matching_service
        self._download_service = download_service or DownloadService()
        self._verification_service = VerificationService()
        self._receipt_download_base_url = receipt_download_base_url

    def issue_receipt(
        self,
        identification_details: IdentificationDetails,
        receipt_payload: GeneratedReceiptPayload,
        *,
        store_id: Optional[UUID] = None,
        access_token: Optional[str] = None,
    ) -> ReceiptResult:
        """Resolve a route and submit the exact payload without enrichment."""
        self._require_not_none(identification_details, "identification_details")
        self._require_not_none(receipt_payload, "receipt_payload")
        self._validate_access_token(access_token)

        try:
            resolution = self._matching_service.match_customer(identification_details, access_token)
            self._validate_resolved_route(resolution)
            route = self._resolve_route(resolution)

            if route is DeliveryRouteType.DOWNLOAD_FALLBACK:
                if identification_details.payment_type is None:
                    return ReceiptResult.download_required(resolution)
                return self._deliver_client_encrypted_download(
                    resolution.match_id,
                    identification_details,
                    receipt_payload,
                    access_token,
                )
            if route is DeliveryRouteType.EMAIL_FALLBACK:
                return ReceiptResult.email_required(resolution)

            recipients = resolution.recipients or []
            if not recipients:
                self._validation_error("Recipient resolution did not include owner devices")
            plaintext_json = _model_json(receipt_payload)
            deliveries = [
                self._encryption_service.encrypt_receipt_for_recipient(plaintext_json, recipient)
                for recipient in recipients
            ]
            envelope = EncryptedReceiptEnvelope(
                match_id=resolution.match_id,
                store_id=str(store_id) if store_id else None,
                device_deliveries=deliveries,
            )
            response = self._api_client.submit_encrypted_receipt(envelope, access_token)
            return ReceiptResult.accepted(response, route)
        except CheqiSDKError:
            raise
        except Exception as exc:
            raise ReceiptProcessingError(f"Receipt processing failed: {exc}") from exc

    def issue_download_receipt(
        self,
        identification_details: IdentificationDetails,
        receipt_payload: GeneratedReceiptPayload,
        *,
        access_token: Optional[str] = None,
    ) -> ReceiptResult:
        """Create an encrypted download without recipient matching."""
        self._require_not_none(identification_details, "identification_details")
        self._require_not_none(receipt_payload, "receipt_payload")
        if identification_details.payment_type is None:
            self._validation_error("identification_details.payment_type is required")
        self._validate_access_token(access_token)
        try:
            return self._deliver_client_encrypted_download(
                None,
                identification_details,
                receipt_payload,
                access_token,
            )
        except CheqiSDKError:
            raise
        except Exception as exc:
            raise ReceiptProcessingError(f"Download receipt processing failed: {exc}") from exc

    def submit_encrypted_receipt(
        self,
        envelope: EncryptedReceiptEnvelope,
        access_token: Optional[str] = None,
    ) -> ReceiptSubmissionResponse:
        """Submit a caller-assembled encrypted envelope."""
        self._require_not_none(envelope, "envelope")
        self._validate_access_token(access_token)
        return self._api_client.submit_encrypted_receipt(envelope, access_token)

    def complete_download_fallback(
        self,
        fallback_result: ReceiptResult,
        receipt_envelope: ReceiptEnvelope,
        *,
        template_hash: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> ReceiptResult:
        """Encrypt and upload a caller-generated fallback envelope."""
        self._require_not_none(fallback_result, "fallback_result")
        self._require_not_none(receipt_envelope, "receipt_envelope")
        if (
            not fallback_result.download_envelope_required
            or fallback_result.delivery_route_type is not DeliveryRouteType.DOWNLOAD_FALLBACK
        ):
            self._validation_error("fallback_result does not require a download receipt envelope")
        self._validate_access_token(access_token)
        link = self._create_download_link()
        ciphertext = self._download_service.encrypt_download_envelope(
            receipt_envelope,
            link.content_key,
        )
        request = ClientReceiptDownloadRequest(
            download_id=link.download_id,
            ciphertext=ciphertext,
            template_hash=template_hash,
        )
        response = self._api_client.upload_encrypted_download_receipt(request, access_token)
        return ReceiptResult.download_accepted(fallback_result.match_id, response, link.url)

    def build_download_cheqi_document(
        self,
        receipt_payload: GeneratedReceiptPayload,
        identification_details: IdentificationDetails,
    ) -> str:
        """Build the CHEQI JSON used only by the browser download route."""
        document = _model_dict(receipt_payload)
        document["identificationDetails"] = _model_dict(identification_details)
        return json.dumps(document, separators=(",", ":"), ensure_ascii=False)

    def _deliver_client_encrypted_download(
        self,
        match_id: Optional[str],
        identification_details: IdentificationDetails,
        receipt_payload: GeneratedReceiptPayload,
        access_token: Optional[str],
    ) -> ReceiptResult:
        link = self._create_download_link()
        cheqi_document = self.build_download_cheqi_document(receipt_payload, identification_details)
        envelope = ReceiptEnvelope(
            cheqi_receipt_id=link.download_id,
            documents={
                "CHEQI": ReceiptEnvelopeDocument(
                    media_type="application/json",
                    content=cheqi_document,
                )
            },
            envelope_version=1,
            receipt_generator_version=_PAYLOAD_DOCUMENT_VERSION,
            receipt_uuid=str(uuid4()),
        )
        ciphertext = self._download_service.encrypt_download_envelope(envelope, link.content_key)
        template_hash = self._verification_service.calculate_cheqi_receipt_hash(cheqi_document)
        request = ClientReceiptDownloadRequest(
            download_id=link.download_id,
            ciphertext=ciphertext,
            template_hash=template_hash,
        )
        response = self._api_client.upload_encrypted_download_receipt(request, access_token)
        return ReceiptResult.download_accepted(match_id, response, link.url)

    def _create_download_link(self) -> DownloadLink:
        if not self._receipt_download_base_url or not self._receipt_download_base_url.strip():
            self._validation_error("A receipt download base URL is required to complete download fallback")
        assert self._receipt_download_base_url is not None
        return self._download_service.generate_download_link(self._receipt_download_base_url)

    @staticmethod
    def _validate_resolved_route(resolution: RecipientResolutionResponse) -> None:
        if resolution is None or not resolution.route_found:
            raise CheqiSDKError(
                "No Cheqi owner-device route was found",
                error_code=ErrorCodes.CUSTOMER_NOT_FOUND,
                http_status_code=404,
            )
        if not resolution.match_id or not resolution.match_id.strip():
            ReceiptService._validation_error("Recipient resolution did not include match_id")

    @staticmethod
    def _resolve_route(resolution: RecipientResolutionResponse) -> DeliveryRouteType:
        if resolution.delivery_route_type:
            try:
                return DeliveryRouteType(resolution.delivery_route_type)
            except ValueError as exc:
                ReceiptService._validation_error(f"Unsupported delivery route: {resolution.delivery_route_type}")
                raise AssertionError from exc
        if resolution.recipients:
            return DeliveryRouteType.DIGITAL
        ReceiptService._validation_error("Recipient resolution did not include delivery_route_type")
        raise AssertionError

    @staticmethod
    def _validate_access_token(access_token: Optional[str]) -> None:
        if access_token is not None and not access_token.strip():
            ReceiptService._validation_error("access_token cannot be empty")

    @staticmethod
    def _require_not_none(value: object, name: str) -> None:
        if value is None:
            ReceiptService._validation_error(f"{name} cannot be None")

    @staticmethod
    def _validation_error(message: str) -> None:
        raise CheqiSDKError(
            message,
            error_code=ErrorCodes.VALIDATION_ERROR,
            http_status_code=400,
        )
