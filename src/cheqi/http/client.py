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
from cheqi.http.retry import RetryHandler
from cheqi.models.generated.cheqi_receipt import CheqiReceipt
from cheqi.models.generated.client_receipt_download_request import ClientReceiptDownloadRequest
from cheqi.models.generated.client_receipt_download_response import ClientReceiptDownloadResponse
from cheqi.models.generated.create_store_request import CreateStoreRequest
from cheqi.models.generated.email_receipt_request import EmailReceiptRequest
from cheqi.models.generated.encrypted_credit_note_envelope import EncryptedCreditNoteEnvelope
from cheqi.models.generated.encrypted_receipt_envelope import EncryptedReceiptEnvelope
from cheqi.models.generated.identification_details import IdentificationDetails
from cheqi.models.generated.match_status_response import MatchStatusResponse
from cheqi.models.generated.receipt_submission_response import ReceiptSubmissionResponse
from cheqi.models.generated.recipient_resolution_response import RecipientResolutionResponse
from cheqi.models.generated.store_dto import StoreDTO

logger = logging.getLogger("cheqi.http")

_USER_AGENT = "CheqiSDK-Python/1.4.0"


def _model_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(by_alias=True, exclude_none=True, mode="json")


@runtime_checkable
class CheqiApiClient(Protocol):
    def get_match(self, match_id: str, access_token: Optional[str] = None) -> MatchStatusResponse: ...

    def match_customer(
        self,
        request: IdentificationDetails,
        access_token: Optional[str] = None,
    ) -> RecipientResolutionResponse: ...

    def submit_encrypted_receipt(
        self,
        request: EncryptedReceiptEnvelope,
        access_token: Optional[str] = None,
    ) -> ReceiptSubmissionResponse: ...

    def submit_encrypted_credit_note(
        self,
        request: EncryptedCreditNoteEnvelope,
        access_token: Optional[str] = None,
    ) -> ReceiptSubmissionResponse: ...

    def upload_encrypted_download_receipt(
        self,
        request: ClientReceiptDownloadRequest,
        access_token: Optional[str] = None,
    ) -> ClientReceiptDownloadResponse: ...

    def send_receipt_via_email(
        self,
        customer_email: str,
        receipt: CheqiReceipt,
        access_token: Optional[str] = None,
    ) -> None: ...

    def create_store(
        self,
        company_id: UUID,
        request: CreateStoreRequest,
        access_token: Optional[str] = None,
    ) -> StoreDTO: ...

    def invite_users(
        self, company_id: UUID, emails: List[str], access_token: Optional[str] = None
    ) -> None: ...

    def get_stores(
        self,
        company_id: UUID,
        active_only: Optional[bool] = None,
        access_token: Optional[str] = None,
    ) -> List[StoreDTO]: ...

    def get_store(
        self,
        company_id: UUID,
        store_id: UUID,
        access_token: Optional[str] = None,
    ) -> StoreDTO: ...

    def update_store(
        self,
        company_id: UUID,
        store_id: UUID,
        request: CreateStoreRequest,
        access_token: Optional[str] = None,
    ) -> StoreDTO: ...

    def delete_store(
        self,
        company_id: UUID,
        store_id: UUID,
        access_token: Optional[str] = None,
    ) -> None: ...

    def activate_store(
        self,
        company_id: UUID,
        store_id: UUID,
        access_token: Optional[str] = None,
    ) -> None: ...

    def deactivate_store(
        self,
        company_id: UUID,
        store_id: UUID,
        access_token: Optional[str] = None,
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

    def _auth_headers(self, access_token: Optional[str] = None) -> Dict[str, str]:
        token = access_token or self._config.api_key
        if not token or not token.strip():
            raise CheqiApiError(
                "No authentication token available",
                error_code=ErrorCodes.AUTHENTICATION_FAILED,
                http_status_code=401,
            )
        return {
            "Authorization": f"Bearer {token}",
            "User-Agent": _USER_AGENT,
        }

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
        self,
        path: str,
        body: Any,
        operation: str,
        access_token: Optional[str] = None,
    ) -> Any:
        headers = self._auth_headers(access_token)
        headers["Content-Type"] = "application/json"

        def request() -> httpx.Response:
            return self._client.post(self._url(path), json=body, headers=headers)

        return self._handle_response(
            self._retry_handler.execute_with_retry(request, operation),
            operation,
        )

    def _get(
        self,
        path: str,
        operation: str,
        params: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
    ) -> Any:
        headers = self._auth_headers(access_token)

        def request() -> httpx.Response:
            return self._client.get(self._url(path), headers=headers, params=params)

        return self._handle_response(
            self._retry_handler.execute_with_retry(request, operation),
            operation,
        )

    def _put(
        self,
        path: str,
        body: Any,
        operation: str,
        access_token: Optional[str] = None,
    ) -> Any:
        headers = self._auth_headers(access_token)
        headers["Content-Type"] = "application/json"

        def request() -> httpx.Response:
            return self._client.put(self._url(path), json=body, headers=headers)

        return self._handle_response(
            self._retry_handler.execute_with_retry(request, operation),
            operation,
        )

    def _delete(
        self,
        path: str,
        operation: str,
        access_token: Optional[str] = None,
    ) -> Any:
        headers = self._auth_headers(access_token)

        def request() -> httpx.Response:
            return self._client.delete(self._url(path), headers=headers)

        return self._handle_response(
            self._retry_handler.execute_with_retry(request, operation),
            operation,
        )

    def get_match(self, match_id: str, access_token: Optional[str] = None) -> MatchStatusResponse:
        if not match_id or not match_id.strip():
            raise CheqiApiError("match_id is required", ErrorCodes.INVALID_REQUEST, 400)
        data = self._get("/recipient/matches/" + quote(match_id, safe=""),
                         "getMatch", access_token=access_token)
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
        access_token: Optional[str] = None,
    ) -> RecipientResolutionResponse:
        data = self._post(Endpoints.CUSTOMER_MATCH, _model_dict(request), "matchCustomer", access_token)
        return RecipientResolutionResponse.model_validate(data)

    def submit_encrypted_receipt(
        self,
        request: EncryptedReceiptEnvelope,
        access_token: Optional[str] = None,
    ) -> ReceiptSubmissionResponse:
        # Preserve the actual acknowledgement status even when its body is unusable.
        body = _model_dict(request)
        headers = self._auth_headers(access_token)
        headers["Content-Type"] = "application/json"
        response = self._retry_handler.execute_with_retry(
            lambda: self._client.post(self._url(Endpoints.ENCRYPTED_RECEIPT), json=body, headers=headers),
            "submitEncryptedReceipt",
        )
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
        access_token: Optional[str] = None,
    ) -> ReceiptSubmissionResponse:
        data = self._post(
            Endpoints.ENCRYPTED_CREDIT_NOTE,
            _model_dict(request),
            "submitEncryptedCreditNote",
            access_token,
        )
        return self._submission(data)

    def upload_encrypted_download_receipt(
        self,
        request: ClientReceiptDownloadRequest,
        access_token: Optional[str] = None,
    ) -> ClientReceiptDownloadResponse:
        data = self._post(
            Endpoints.CLIENT_RECEIPT_DOWNLOAD,
            _model_dict(request),
            "uploadEncryptedDownloadReceipt",
            access_token,
        )
        return ClientReceiptDownloadResponse.model_validate(data)

    def send_receipt_via_email(
        self,
        customer_email: str,
        receipt: CheqiReceipt,
        access_token: Optional[str] = None,
    ) -> None:
        request = EmailReceiptRequest(customer_email=customer_email, cheqi_receipt=receipt)
        self._post(Endpoints.EMAIL_RECEIPT, _model_dict(request), "sendReceiptViaEmail", access_token)

    def create_store(
        self,
        company_id: UUID,
        request: CreateStoreRequest,
        access_token: Optional[str] = None,
    ) -> StoreDTO:
        data = self._post(
            Endpoints.company_stores(str(company_id)),
            _model_dict(request),
            "createStore",
            access_token,
        )
        return StoreDTO.model_validate(data)

    def invite_users(
        self, company_id: UUID, emails: List[str], access_token: Optional[str] = None
    ) -> None:
        self._post(
            Endpoints.company_invite_employees(str(company_id)),
            {"emails": emails},
            "inviteEmployees",
            access_token,
        )

    def get_stores(
        self,
        company_id: UUID,
        active_only: Optional[bool] = None,
        access_token: Optional[str] = None,
    ) -> List[StoreDTO]:
        params = {"activeOnly": active_only} if active_only is not None else None
        data = self._get(
            Endpoints.company_stores(str(company_id)),
            "getStores",
            params,
            access_token,
        )
        return [StoreDTO.model_validate(item) for item in data]

    def get_store(
        self,
        company_id: UUID,
        store_id: UUID,
        access_token: Optional[str] = None,
    ) -> StoreDTO:
        data = self._get(
            Endpoints.company_store(str(company_id), str(store_id)),
            "getStore",
            access_token=access_token,
        )
        return StoreDTO.model_validate(data)

    def update_store(
        self,
        company_id: UUID,
        store_id: UUID,
        request: CreateStoreRequest,
        access_token: Optional[str] = None,
    ) -> StoreDTO:
        data = self._put(
            Endpoints.company_store(str(company_id), str(store_id)),
            _model_dict(request),
            "updateStore",
            access_token,
        )
        return StoreDTO.model_validate(data)

    def delete_store(
        self,
        company_id: UUID,
        store_id: UUID,
        access_token: Optional[str] = None,
    ) -> None:
        self._delete(
            Endpoints.company_store(str(company_id), str(store_id)),
            "deleteStore",
            access_token,
        )

    def activate_store(
        self,
        company_id: UUID,
        store_id: UUID,
        access_token: Optional[str] = None,
    ) -> None:
        self._put(
            Endpoints.company_store_activate(str(company_id), str(store_id)),
            {},
            "activateStore",
            access_token,
        )

    def deactivate_store(
        self,
        company_id: UUID,
        store_id: UUID,
        access_token: Optional[str] = None,
    ) -> None:
        self._put(
            Endpoints.company_store_deactivate(str(company_id), str(store_id)),
            {},
            "deactivateStore",
            access_token,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
