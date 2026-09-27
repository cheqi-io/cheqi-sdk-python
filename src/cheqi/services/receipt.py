"""Issue definitive receipt payloads through encrypted device processing."""

from __future__ import annotations

import json
from typing import NoReturn, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError

from cheqi.exceptions import CheqiApiError, CheqiSDKError, ErrorCodes, ReceiptProcessingError
from cheqi.http.client import CheqiApiClient
from cheqi.models.download import DownloadLink
from cheqi.models.generated.client_receipt_download_request import ClientReceiptDownloadRequest
from cheqi.models.generated.client_receipt_download_response import ClientReceiptDownloadResponse
from cheqi.models.generated.encrypted_receipt_envelope import EncryptedReceiptEnvelope
from cheqi.models.generated.identification_details import IdentificationDetails
from cheqi.models.generated.match_state import MatchState
from cheqi.models.generated.match_status_response import MatchStatusResponse
from cheqi.models.generated.receipt_envelope import ReceiptEnvelope
from cheqi.models.generated.receipt_envelope_document import ReceiptEnvelopeDocument
from cheqi.models.generated.receipt_payload import ReceiptPayload as GeneratedReceiptPayload
from cheqi.models.generated.receipt_submission_response import ReceiptSubmissionResponse
from cheqi.models.generated.recipient_resolution_response import RecipientResolutionResponse
from cheqi.models.receipt import DeliveryRouteType, PreparedReceiptDownload, ReceiptResult
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
        self._validate_payload(receipt_payload)
        self._validate_access_token(access_token)

        try:
            try:
                resolution = self._matching_service.match_customer(identification_details, access_token)
            except CheqiApiError as exc:
                if not self._recoverable(exc):
                    raise
                return ReceiptResult.download_prepared(self._prepare_download(receipt_payload))
            self._validate_resolved_route(resolution)
            assert resolution.match_id is not None
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

            envelope = self.generate_encrypted_receipt_envelope(resolution, receipt_payload, store_id=store_id)
            try:
                response = self._submit_payload(envelope, access_token)
                return ReceiptResult.accepted(response, route)
            except CheqiApiError as exc:
                if exc.http_status_code == 410:
                    return ReceiptResult.digital_expired(resolution.match_id)
                if not self._ambiguous_submission(exc):
                    raise
                return ReceiptResult.digital_pending(
                    resolution.match_id, self._prepare_download(receipt_payload),
                    getattr(exc, "retry_after_seconds", None),
                )
        except CheqiSDKError:
            raise
        except Exception as exc:
            raise ReceiptProcessingError(f"Receipt processing failed: {exc}") from exc


    def get_match(self, match_id: str, access_token: Optional[str] = None) -> MatchStatusResponse:
        """Fetch the original device snapshot or submission using only the opaque match id."""
        self._validate_match_id(match_id)
        self._validate_access_token(access_token)
        return self._api_client.get_match(match_id, access_token)

    def generate_encrypted_receipt_envelope(
        self, match: RecipientResolutionResponse | MatchStatusResponse,
        receipt_payload: GeneratedReceiptPayload, *, store_id: Optional[UUID] = None,
    ) -> EncryptedReceiptEnvelope:
        """Encrypt locally for every original device; performs no HTTP requests."""
        self._validate_payload(receipt_payload)
        if isinstance(match, MatchStatusResponse):
            if match.state != MatchState.MATCHED or match.route != "DIGITAL":
                self._validation_error("Match must be MATCHED with a digital route")
        else:
            self._validate_resolved_route(match)
            if self._resolve_route(match) is not DeliveryRouteType.DIGITAL:
                self._validation_error("Match must contain a digital route")
        self._validate_match_id(match.match_id)
        if not match.recipients:
            self._validation_error("Match must contain owner devices")
        plaintext = _model_json(receipt_payload)
        return EncryptedReceiptEnvelope(
            match_id=match.match_id, store_id=str(store_id) if store_id else None,
            device_deliveries=[
                self._encryption_service.encrypt_receipt_for_recipient(plaintext, recipient)
                for recipient in match.recipients or []
            ],
        )

    def resume_receipt(
        self, match_id: str, receipt_payload: GeneratedReceiptPayload, *,
        store_id: Optional[UUID] = None, access_token: Optional[str] = None,
    ) -> ReceiptResult:
        """Explicit recovery operation; no polling, scheduling, or rematching."""
        self._validate_payload(receipt_payload)
        try:
            match = self.get_match(match_id, access_token)
            if match.match_id != match_id or match.state is None:
                self._validation_error("Invalid match status response")
            if match.state is MatchState.SUBMITTED:
                if (match.submission is None or not match.submission.cheqi_receipt_id
                        or match.submission.match_id != match_id):
                    self._validation_error("Missing original submission")
                assert match.submission is not None
                return ReceiptResult.accepted(match.submission)
            if match.state is MatchState.EXPIRED:
                return ReceiptResult.digital_expired(match_id)
            if match.state is MatchState.IN_PROGRESS:
                return ReceiptResult.digital_pending(match_id, retry_after_seconds=match.retry_after_seconds)
            envelope = self.generate_encrypted_receipt_envelope(match, receipt_payload, store_id=store_id)
            return ReceiptResult.accepted(self._submit_payload(envelope, access_token))
        except CheqiApiError as exc:
            if exc.http_status_code == 410:
                return ReceiptResult.digital_expired(match_id)
            if self._ambiguous_submission(exc):
                return ReceiptResult.digital_pending(
                    match_id, retry_after_seconds=getattr(exc, "retry_after_seconds", None),
                )
            raise

    def upload_prepared_download(
        self, download: PreparedReceiptDownload, access_token: Optional[str] = None,
    ) -> ClientReceiptDownloadResponse:
        """Upload the same persisted ciphertext; the URL fragment key stays local."""
        self._require_not_none(download, "download")
        self._validate_access_token(access_token)
        return self._api_client.upload_encrypted_download_receipt(download.upload_request, access_token)

    def _submit_payload(
        self, envelope: EncryptedReceiptEnvelope, access_token: Optional[str],
    ) -> ReceiptSubmissionResponse:
        response = self.submit_encrypted_receipt(envelope, access_token)
        if response is None or not response.cheqi_receipt_id or response.match_id != envelope.match_id:
            raise CheqiApiError("Invalid submission response", ErrorCodes.INVALID_RESPONSE)
        return response

    @staticmethod
    def _recoverable(exc: CheqiApiError) -> bool:
        return exc.is_retryable or exc.is_network_error

    @staticmethod
    def _ambiguous_submission(exc: CheqiApiError) -> bool:
        return ReceiptService._recoverable(exc) or (
            exc.error_code == ErrorCodes.INVALID_RESPONSE
            and (exc.http_status_code == 0 or 200 <= exc.http_status_code < 300)
        )

    @staticmethod
    def _validate_match_id(match_id: Optional[str]) -> None:
        if not match_id or not match_id.strip():
            ReceiptService._validation_error("match_id is required")

    @staticmethod
    def _validate_payload(payload: GeneratedReceiptPayload) -> None:
        ReceiptService._require_not_none(payload, "receipt_payload")
        # Revalidate even models made using model_construct; invalid input must fail before matching.
        try:
            GeneratedReceiptPayload.model_validate(_model_dict(payload))
        except ValidationError as exc:
            raise CheqiSDKError("Invalid receipt payload", ErrorCodes.VALIDATION_ERROR, 400) from exc
        if not payload.products:
            ReceiptService._validation_error("receipt_payload must contain products")

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
        prepared = self._prepare_download(receipt_payload, identification_details)
        try:
            response = self.upload_prepared_download(prepared, access_token)
            return ReceiptResult.download_accepted(match_id, response, prepared.download_url)
        except CheqiApiError as exc:
            if not self._recoverable(exc):
                raise
            return ReceiptResult.download_prepared(prepared)

    def _prepare_download(
        self, receipt_payload: GeneratedReceiptPayload,
        identification_details: Optional[IdentificationDetails] = None,
    ) -> PreparedReceiptDownload:
        link = self._create_download_link()
        cheqi_document = (
            self.build_download_cheqi_document(receipt_payload, identification_details)
            if identification_details is not None else _model_json(receipt_payload)
        )
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
        return PreparedReceiptDownload(download_url=link.url, upload_request=request)

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
    def _validation_error(message: str) -> NoReturn:
        raise CheqiSDKError(
            message,
            error_code=ErrorCodes.VALIDATION_ERROR,
            http_status_code=400,
        )
