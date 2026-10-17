"""HTTP boundary for the current encrypted receipt-processing API."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from urllib.parse import quote
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError

from cheqi.config import CheqiSDKConfig
from cheqi.exceptions import CheqiApiError, ErrorCodes, SubmissionInProgressError
from cheqi.http.endpoints import Endpoints
from cheqi.http.request_options import DEFAULT_REQUEST_OPTIONS, RequestOptions
from cheqi.http.retry import RetryHandler
from cheqi.models.generated.acknowledge_request import AcknowledgeRequest
from cheqi.models.generated.cheqi_receipt import CheqiReceipt
from cheqi.models.generated.client_credentials_token_request import ClientCredentialsTokenRequest
from cheqi.models.generated.client_receipt_download_request import ClientReceiptDownloadRequest
from cheqi.models.generated.client_receipt_download_response import ClientReceiptDownloadResponse
from cheqi.models.generated.create_store_request import CreateStoreRequest
from cheqi.models.generated.destination_response import DestinationResponse
from cheqi.models.generated.email_receipt_request import EmailReceiptRequest
from cheqi.models.generated.encrypted_credit_note_envelope import EncryptedCreditNoteEnvelope
from cheqi.models.generated.encrypted_receipt_envelope import EncryptedReceiptEnvelope
from cheqi.models.generated.identification_details import IdentificationDetails
from cheqi.models.generated.invite_employee_request import InviteEmployeeRequest
from cheqi.models.generated.invite_employees_response import InviteEmployeesResponse
from cheqi.models.generated.match_status_response import MatchStatusResponse
from cheqi.models.generated.o_auth_token_exchange_response import OAuthTokenExchangeResponse
from cheqi.models.generated.receipt_submission_response import ReceiptSubmissionResponse
from cheqi.models.generated.recipient_resolution_response import RecipientResolutionResponse
from cheqi.models.generated.register_request import RegisterRequest
from cheqi.models.generated.register_response import RegisterResponse
from cheqi.models.generated.store_dto import StoreDTO
from cheqi.models.generated.update_subscription_request import UpdateSubscriptionRequest
from cheqi.models.generated.webhook_dto import WebhookDTO
from cheqi.models.generated.webhook_receipt_envelope import WebhookReceiptEnvelope

logger = logging.getLogger("cheqi.http")

_USER_AGENT = "CheqiSDK-Python/2.0.0"


def _model_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(by_alias=True, exclude_none=True, mode="json")


@runtime_checkable
class CheqiApiClient(Protocol):
    def request_access_token(
        self, request: ClientCredentialsTokenRequest, *, options: Optional[RequestOptions] = None,
    ) -> OAuthTokenExchangeResponse: ...

    def get_match(self, match_id: str, *, options: Optional[RequestOptions] = None) -> MatchStatusResponse: ...

    def match_customer(
        self,
        request: IdentificationDetails,
        *,
        options: Optional[RequestOptions] = None,
    ) -> RecipientResolutionResponse: ...

    def submit_encrypted_receipt(
        self,
        request: EncryptedReceiptEnvelope,
        *,
        options: Optional[RequestOptions] = None,
    ) -> ReceiptSubmissionResponse: ...

    def submit_encrypted_credit_note(
        self,
        request: EncryptedCreditNoteEnvelope,
        *,
        options: Optional[RequestOptions] = None,
    ) -> ReceiptSubmissionResponse: ...

    def upload_encrypted_download_receipt(
        self,
        request: ClientReceiptDownloadRequest,
        *,
        options: Optional[RequestOptions] = None,
    ) -> ClientReceiptDownloadResponse: ...

    def send_receipt_via_email(
        self,
        customer_email: str,
        receipt: CheqiReceipt,
        *,
        options: Optional[RequestOptions] = None,
    ) -> None: ...

    def create_store(
        self,
        company_id: UUID,
        request: CreateStoreRequest,
        *,
        options: Optional[RequestOptions] = None,
    ) -> StoreDTO: ...

    def invite_users(
        self, company_id: UUID, emails: List[str], resend_pending: Optional[bool] = None,
        *, options: Optional[RequestOptions] = None,
    ) -> InviteEmployeesResponse: ...

    def list_receipt_destinations(self, *, options: Optional[RequestOptions] = None) -> List[DestinationResponse]: ...

    def register_receipt_destination(
        self, request: RegisterRequest, *, options: Optional[RequestOptions] = None,
    ) -> RegisterResponse: ...

    def get_pending_receipts(
        self, destination_id: UUID, *, options: Optional[RequestOptions] = None,
    ) -> List[WebhookReceiptEnvelope]: ...

    def acknowledge_receipts(
        self, destination_id: UUID, receipt_ids: List[str], *, options: Optional[RequestOptions] = None,
    ) -> None: ...

    def deactivate_receipt_destination(
        self, destination_id: UUID, *, options: Optional[RequestOptions] = None,
    ) -> None: ...

    def update_webhook_subscription_url(
        self, subscription_id: UUID, notification_url: str, *, options: Optional[RequestOptions] = None,
    ) -> WebhookDTO: ...

    def get_stores(
        self,
        company_id: UUID,
        active_only: Optional[bool] = None,
        *,
        options: Optional[RequestOptions] = None,
    ) -> List[StoreDTO]: ...

    def get_store(
        self,
        company_id: UUID,
        store_id: UUID,
        *,
        options: Optional[RequestOptions] = None,
    ) -> StoreDTO: ...

    def update_store(
        self,
        company_id: UUID,
        store_id: UUID,
        request: CreateStoreRequest,
        *,
        options: Optional[RequestOptions] = None,
    ) -> StoreDTO: ...

    def delete_store(
        self,
        company_id: UUID,
        store_id: UUID,
        *,
        options: Optional[RequestOptions] = None,
    ) -> None: ...

    def activate_store(
        self,
        company_id: UUID,
        store_id: UUID,
        *,
        options: Optional[RequestOptions] = None,
    ) -> None: ...

    def deactivate_store(
        self,
        company_id: UUID,
        store_id: UUID,
        *,
        options: Optional[RequestOptions] = None,
    ) -> None: ...


class DefaultCheqiApiClient:
    """Synchronous ``httpx`` implementation of the Cheqi API boundary."""

    def __init__(
        self,
        config: CheqiSDKConfig,
        *,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self._config = config
        self._retry_handler = RetryHandler(config.max_retries)
        configured_client = http_client or config.http_client
        self._owns_client = configured_client is None
        self._client = configured_client or httpx.Client(
            timeout=config.timeout_seconds,
            headers={"User-Agent": _USER_AGENT},
        )

    def _url(self, path: str) -> str:
        return f"{self._config.api_endpoint.rstrip('/')}/{path.lstrip('/')}"

    def _auth_headers(self, options: RequestOptions) -> Dict[str, str]:
        """Use the per-call access token when present, otherwise the configured API key."""
        token = options.access_token or self._config.api_key
        if not token or not token.strip():
            raise CheqiApiError(
                "No credentials for this call: pass options=RequestOptions(access_token=...) "
                "or configure api_key",
                error_code=ErrorCodes.AUTHENTICATION_FAILED,
                http_status_code=401,
            )
        return {
            "Authorization": f"Bearer {token}",
            "User-Agent": _USER_AGENT,
        }

    def _send(
        self, method: str, path: str, operation: str, options: Optional[RequestOptions], *,
        json: Any = None, params: Optional[Dict[str, Any]] = None, authenticate: bool = True,
    ) -> httpx.Response:
        options = options or DEFAULT_REQUEST_OPTIONS
        headers = self._auth_headers(options) if authenticate else {"User-Agent": _USER_AGENT}
        if json is not None:
            headers["Content-Type"] = "application/json"
        timeout = options.timeout_seconds or self._config.timeout_seconds

        def request() -> httpx.Response:
            return self._client.request(
                method, self._url(path), json=json, params=params, headers=headers, timeout=timeout,
            )

        return self._retry_handler.execute_with_retry(request, operation, options.max_retries)

    def _handle_response(self, response: httpx.Response, operation: str) -> Any:
        if response.status_code >= 400:
            correlation_id = response.headers.get("X-Correlation-Id")
            error_code = ErrorCodes.UNKNOWN_ERROR
            if response.status_code == 401:
                error_code = ErrorCodes.AUTHENTICATION_FAILED
            elif response.status_code == 403:
                error_code = ErrorCodes.AUTHORIZATION_FAILED
            elif response.status_code == 404:
                error_code = ErrorCodes.RECEIPT_NOT_FOUND
            elif response.status_code == 429:
                error_code = ErrorCodes.RATE_LIMITED
            elif response.status_code >= 500:
                error_code = ErrorCodes.SERVER_ERROR
            raise CheqiApiError(
                f"{operation} failed with status {response.status_code}: {response.text}",
                error_code=error_code,
                http_status_code=response.status_code,
                correlation_id=correlation_id,
            )
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise CheqiApiError(
                "Invalid API response", ErrorCodes.INVALID_RESPONSE, response.status_code,
                response.headers.get("X-Correlation-Id"),
            ) from exc

    def _post(
        self, path: str, body: Any, operation: str, options: Optional[RequestOptions] = None,
    ) -> Any:
        return self._handle_response(self._send("POST", path, operation, options, json=body), operation)

    def _get(
        self, path: str, operation: str, params: Optional[Dict[str, Any]] = None,
        options: Optional[RequestOptions] = None,
    ) -> Any:
        return self._handle_response(self._send("GET", path, operation, options, params=params), operation)

    def _put(
        self, path: str, body: Any, operation: str, options: Optional[RequestOptions] = None,
    ) -> Any:
        return self._handle_response(self._send("PUT", path, operation, options, json=body), operation)

    def _delete(self, path: str, operation: str, options: Optional[RequestOptions] = None) -> Any:
        return self._handle_response(self._send("DELETE", path, operation, options), operation)

    def _patch(
        self, path: str, body: Any, operation: str, options: Optional[RequestOptions] = None,
    ) -> Any:
        return self._handle_response(self._send("PATCH", path, operation, options, json=body), operation)

    def request_access_token(
        self, request: ClientCredentialsTokenRequest, *, options: Optional[RequestOptions] = None,
    ) -> OAuthTokenExchangeResponse:
        """Exchange client credentials for a short-lived Company token bound to one Grant."""
        if request is None or not request.client_id or not request.client_secret or not request.grant_id:
            raise CheqiApiError(
                "Token request requires client_id, client_secret and grant_id",
                ErrorCodes.INVALID_REQUEST, 400,
            )
        body = _model_dict(request)
        body.setdefault("grant_type", "client_credentials")
        # Client credentials travel in the body; this call carries no bearer credential.
        response = self._send("POST", Endpoints.OAUTH_TOKEN, "requestAccessToken", options,
                              json=body, authenticate=False)
        data = self._handle_response(response, "requestAccessToken")
        try:
            token = OAuthTokenExchangeResponse.model_validate(data)
        except ValidationError as exc:
            raise CheqiApiError("Invalid token response", ErrorCodes.INVALID_RESPONSE) from exc
        if not token.access_token:
            raise CheqiApiError("Token response did not include an access token", ErrorCodes.INVALID_RESPONSE)
        return token

    def get_match(self, match_id: str, *, options: Optional[RequestOptions] = None) -> MatchStatusResponse:
        if not match_id or not match_id.strip():
            raise CheqiApiError("match_id is required", ErrorCodes.INVALID_REQUEST, 400)
        data = self._get("/recipient/matches/" + quote(match_id, safe=""),
                         "getMatch", options=options)
        try:
            return MatchStatusResponse.model_validate(data)
        except ValidationError as exc:
            raise CheqiApiError("Invalid match response", ErrorCodes.INVALID_RESPONSE) from exc

    @staticmethod
    def _submission(data: Any) -> ReceiptSubmissionResponse:
        if isinstance(data, dict) and data.get("state") == "IN_PROGRESS":
            delay = data.get("retryAfterSeconds", 2)
            raise SubmissionInProgressError(max(1, delay) if isinstance(delay, int) else 2)
        try:
            submitted = ReceiptSubmissionResponse.model_validate(data)
            if not submitted.cheqi_receipt_id or not submitted.match_id:
                raise ValueError("Missing submission identifiers")
            return submitted
        except (ValidationError, ValueError) as exc:
            raise CheqiApiError("Invalid submission response", ErrorCodes.INVALID_RESPONSE) from exc

    def match_customer(
        self,
        request: IdentificationDetails,
        *,
        options: Optional[RequestOptions] = None,
    ) -> RecipientResolutionResponse:
        data = self._post(Endpoints.CUSTOMER_MATCH, _model_dict(request), "matchCustomer", options)
        return RecipientResolutionResponse.model_validate(data)

    def submit_encrypted_receipt(
        self,
        request: EncryptedReceiptEnvelope,
        *,
        options: Optional[RequestOptions] = None,
    ) -> ReceiptSubmissionResponse:
        # Preserve the actual acknowledgement status even when its body is unusable.
        response = self._send("POST", Endpoints.ENCRYPTED_RECEIPT, "submitEncryptedReceipt", options,
                              json=_model_dict(request))
        try:
            return self._submission(self._handle_response(response, "submitEncryptedReceipt"))
        except CheqiApiError as exc:
            if exc.error_code == ErrorCodes.INVALID_RESPONSE and exc.http_status_code == 0:
                raise CheqiApiError(str(exc), exc.error_code, response.status_code,
                                    response.headers.get("X-Correlation-Id")) from exc
            if isinstance(exc, SubmissionInProgressError):
                exc.correlation_id = response.headers.get("X-Correlation-Id")
            raise

    def submit_encrypted_credit_note(
        self,
        request: EncryptedCreditNoteEnvelope,
        *,
        options: Optional[RequestOptions] = None,
    ) -> ReceiptSubmissionResponse:
        data = self._post(
            Endpoints.ENCRYPTED_CREDIT_NOTE,
            _model_dict(request),
            "submitEncryptedCreditNote",
            options,
        )
        return self._submission(data)

    def upload_encrypted_download_receipt(
        self,
        request: ClientReceiptDownloadRequest,
        *,
        options: Optional[RequestOptions] = None,
    ) -> ClientReceiptDownloadResponse:
        data = self._post(
            Endpoints.CLIENT_RECEIPT_DOWNLOAD,
            _model_dict(request),
            "uploadEncryptedDownloadReceipt",
            options,
        )
        return ClientReceiptDownloadResponse.model_validate(data)

    def send_receipt_via_email(
        self,
        customer_email: str,
        receipt: CheqiReceipt,
        *,
        options: Optional[RequestOptions] = None,
    ) -> None:
        request = EmailReceiptRequest(customer_email=customer_email, cheqi_receipt=receipt)
        self._post(Endpoints.EMAIL_RECEIPT, _model_dict(request), "sendReceiptViaEmail", options)

    def create_store(
        self,
        company_id: UUID,
        request: CreateStoreRequest,
        *,
        options: Optional[RequestOptions] = None,
    ) -> StoreDTO:
        data = self._post(
            Endpoints.company_stores(str(company_id)),
            _model_dict(request),
            "createStore",
            options,
        )
        return StoreDTO.model_validate(data)

    def invite_users(
        self, company_id: UUID, emails: List[str], resend_pending: Optional[bool] = None,
        *, options: Optional[RequestOptions] = None,
    ) -> InviteEmployeesResponse:
        data = self._post(
            Endpoints.company_invite_employees(str(company_id)),
            _model_dict(InviteEmployeeRequest(emails=emails, resend_pending=resend_pending)),
            "inviteEmployees",
            options,
        )
        return InviteEmployeesResponse.model_validate(data)

    def list_receipt_destinations(self, *, options: Optional[RequestOptions] = None) -> List[DestinationResponse]:
        data = self._get(Endpoints.RECEIPT_DESTINATIONS, "listReceiptDestinations", options=options)
        return [DestinationResponse.model_validate(item) for item in data]

    def register_receipt_destination(
        self, request: RegisterRequest, *, options: Optional[RequestOptions] = None,
    ) -> RegisterResponse:
        data = self._post(Endpoints.RECEIPT_DESTINATIONS, _model_dict(request),
                          "registerReceiptDestination", options)
        return RegisterResponse.model_validate(data)

    def get_pending_receipts(
        self, destination_id: UUID, *, options: Optional[RequestOptions] = None,
    ) -> List[WebhookReceiptEnvelope]:
        data = self._get(Endpoints.receipt_destination_queue(str(destination_id)),
                         "getPendingReceipts", options=options)
        return [WebhookReceiptEnvelope.model_validate(item) for item in data]

    def acknowledge_receipts(
        self, destination_id: UUID, receipt_ids: List[str], *, options: Optional[RequestOptions] = None,
    ) -> None:
        self._post(Endpoints.receipt_destination_acknowledge(str(destination_id)),
                   _model_dict(AcknowledgeRequest(receipt_ids=receipt_ids)),
                   "acknowledgeReceipts", options)

    def deactivate_receipt_destination(
        self, destination_id: UUID, *, options: Optional[RequestOptions] = None,
    ) -> None:
        self._delete(Endpoints.receipt_destination(str(destination_id)),
                     "deactivateReceiptDestination", options)

    def update_webhook_subscription_url(
        self, subscription_id: UUID, notification_url: str, *, options: Optional[RequestOptions] = None,
    ) -> WebhookDTO:
        data = self._patch(Endpoints.webhook_subscription(str(subscription_id)),
                           _model_dict(UpdateSubscriptionRequest(notification_url=notification_url)),
                           "updateWebhookSubscriptionUrl", options)
        return WebhookDTO.model_validate(data)

    def get_stores(
        self,
        company_id: UUID,
        active_only: Optional[bool] = None,
        *,
        options: Optional[RequestOptions] = None,
    ) -> List[StoreDTO]:
        params = {"activeOnly": active_only} if active_only is not None else None
        data = self._get(
            Endpoints.company_stores(str(company_id)),
            "getStores",
            params,
            options,
        )
        return [StoreDTO.model_validate(item) for item in data]

    def get_store(
        self,
        company_id: UUID,
        store_id: UUID,
        *,
        options: Optional[RequestOptions] = None,
    ) -> StoreDTO:
        data = self._get(
            Endpoints.company_store(str(company_id), str(store_id)),
            "getStore",
            options=options,
        )
        return StoreDTO.model_validate(data)

    def update_store(
        self,
        company_id: UUID,
        store_id: UUID,
        request: CreateStoreRequest,
        *,
        options: Optional[RequestOptions] = None,
    ) -> StoreDTO:
        data = self._put(
            Endpoints.company_store(str(company_id), str(store_id)),
            _model_dict(request),
            "updateStore",
            options,
        )
        return StoreDTO.model_validate(data)

    def delete_store(
        self,
        company_id: UUID,
        store_id: UUID,
        *,
        options: Optional[RequestOptions] = None,
    ) -> None:
        self._delete(
            Endpoints.company_store(str(company_id), str(store_id)),
            "deleteStore",
            options,
        )

    def activate_store(
        self,
        company_id: UUID,
        store_id: UUID,
        *,
        options: Optional[RequestOptions] = None,
    ) -> None:
        self._put(
            Endpoints.company_store_activate(str(company_id), str(store_id)),
            {},
            "activateStore",
            options,
        )

    def deactivate_store(
        self,
        company_id: UUID,
        store_id: UUID,
        *,
        options: Optional[RequestOptions] = None,
    ) -> None:
        self._put(
            Endpoints.company_store_deactivate(str(company_id), str(store_id)),
            {},
            "deactivateStore",
            options,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
