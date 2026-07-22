"""HTTP client for Cheqi API communication."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from uuid import UUID

import httpx

from cheqi.config import CheqiSDKConfig
from cheqi.exceptions import CheqiApiError, ErrorCodes
from cheqi.http.endpoints import Endpoints
from cheqi.http.retry import RetryHandler
from cheqi.models.company import (
    CreateStoreRequest,
    ProvisionCompanyRequest,
    ProvisionCompanyResponse,
    Store,
)
from cheqi.models.credit_note import (
    CreditNoteCreatedResponse,
    CreditNoteTemplateGenerationRequest,
    CreditNoteTemplateResponse,
    EncryptedCreditNote,
    EncryptedCreditNotesRequest,
)
from cheqi.models.download import ClientReceiptDownloadRequest, ClientReceiptDownloadResponse
from cheqi.models.encryption import EncryptedReceiptRequestDto, EncryptedReceiptsRequest
from cheqi.models.enums import ReceiptFormat
from cheqi.models.envelopes import ReceiptCreatedResponse
from cheqi.models.matching import IdentificationDetails, RecipientResolutionResponse
from cheqi.models.receipt import ReceiptTemplateRequest, ReceiptTemplateResponse

logger = logging.getLogger("cheqi.http")

_USER_AGENT = "CheqiSDK-Python/0.2.1"


@runtime_checkable
class CheqiApiClient(Protocol):
    """Protocol defining the Cheqi API client interface."""

    def generate_receipt_template(
        self,
        request: ReceiptTemplateRequest,
        receipt_formats: List[ReceiptFormat],
        access_token: Optional[str] = None,
    ) -> ReceiptTemplateResponse: ...

    def generate_credit_note_template(
        self,
        request: CreditNoteTemplateGenerationRequest,
        access_token: Optional[str] = None,
    ) -> CreditNoteTemplateResponse: ...

    def match_customer(
        self,
        request: IdentificationDetails,
        access_token: Optional[str] = None,
    ) -> RecipientResolutionResponse: ...

    def send_encrypted_receipts(
        self,
        match_id: str,
        encrypted_receipts: List[EncryptedReceiptRequestDto],
        template_hash: str,
        access_token: Optional[str] = None,
    ) -> ReceiptCreatedResponse: ...

    def upload_client_encrypted_receipt(
        self,
        request: ClientReceiptDownloadRequest,
        access_token: Optional[str] = None,
    ) -> ClientReceiptDownloadResponse: ...

    def send_encrypted_credit_notes(
        self,
        match_id: str,
        parent_cheqi_receipt_id: str,
        encrypted_credit_notes: List[EncryptedCreditNote],
        template_hash: str,
        access_token: Optional[str] = None,
    ) -> CreditNoteCreatedResponse: ...

    def send_receipt_via_email(
        self,
        customer_email: str,
        receipt_json: str,
        access_token: Optional[str] = None,
    ) -> None: ...

    def provision_company(
        self, request: ProvisionCompanyRequest
    ) -> ProvisionCompanyResponse: ...

    def create_store(
        self,
        company_id: UUID,
        request: CreateStoreRequest,
        access_token: Optional[str] = None,
    ) -> Store: ...

    def get_stores(
        self,
        company_id: UUID,
        active_only: Optional[bool] = None,
        access_token: Optional[str] = None,
    ) -> List[Store]: ...

    def get_store(
        self,
        company_id: UUID,
        store_id: UUID,
        access_token: Optional[str] = None,
    ) -> Store: ...

    def update_store(
        self,
        company_id: UUID,
        store_id: UUID,
        request: CreateStoreRequest,
        access_token: Optional[str] = None,
    ) -> Store: ...

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
    """Default HTTP implementation of the Cheqi API client using httpx."""

    def __init__(self, config: CheqiSDKConfig) -> None:
        self._config = config
        self._retry_handler = RetryHandler(config.max_retries)
        self._client = httpx.Client(
            base_url=config.api_endpoint,
            timeout=config.timeout_seconds,
            headers={"User-Agent": _USER_AGENT},
        )

    def _auth_headers(self, access_token: Optional[str] = None) -> Dict[str, str]:
        """Build authentication headers."""
        token = access_token or self._config.api_key
        if not token:
            raise CheqiApiError(
                "No authentication token available",
                error_code=ErrorCodes.AUTHENTICATION_FAILED,
                http_status_code=401,
            )
        return {"Authorization": f"Bearer {token}"}

    def _handle_response(self, response: httpx.Response, operation: str) -> Any:
        """Handle API response, raising on errors."""
        if response.status_code >= 400:
            body = response.text
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
                f"{operation} failed with status {response.status_code}: {body}",
                error_code=error_code,
                http_status_code=response.status_code,
                correlation_id=correlation_id,
            )

        if response.status_code == 204 or not response.content:
            return None

        return response.json()

    def _post(
        self,
        path: str,
        body: Any,
        operation: str,
        access_token: Optional[str] = None,
    ) -> Any:
        """Execute a POST request with retry."""
        headers = self._auth_headers(access_token)
        headers["Content-Type"] = "application/json"

        if isinstance(body, str):
            json_body = body
        else:
            json_body = body

        def do_request() -> httpx.Response:
            if isinstance(json_body, str):
                return self._client.post(path, content=json_body, headers=headers)
            return self._client.post(path, json=json_body, headers=headers)

        response = self._retry_handler.execute_with_retry(do_request, operation)
        return self._handle_response(response, operation)

    def _get(
        self,
        path: str,
        operation: str,
        params: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
    ) -> Any:
        """Execute a GET request with retry."""
        headers = self._auth_headers(access_token)

        def do_request() -> httpx.Response:
            return self._client.get(path, headers=headers, params=params)

        response = self._retry_handler.execute_with_retry(do_request, operation)
        return self._handle_response(response, operation)

    def _put(
        self,
        path: str,
        body: Any,
        operation: str,
        access_token: Optional[str] = None,
    ) -> Any:
        """Execute a PUT request with retry."""
        headers = self._auth_headers(access_token)
        headers["Content-Type"] = "application/json"

        def do_request() -> httpx.Response:
            if isinstance(body, str):
                return self._client.put(path, content=body, headers=headers)
            return self._client.put(path, json=body, headers=headers)

        response = self._retry_handler.execute_with_retry(do_request, operation)
        return self._handle_response(response, operation)

    def _delete(
        self,
        path: str,
        operation: str,
        access_token: Optional[str] = None,
    ) -> Any:
        """Execute a DELETE request with retry."""
        headers = self._auth_headers(access_token)

        def do_request() -> httpx.Response:
            return self._client.delete(path, headers=headers)

        response = self._retry_handler.execute_with_retry(do_request, operation)
        return self._handle_response(response, operation)

    # ===== Receipt Operations =====

    def generate_receipt_template(
        self,
        request: ReceiptTemplateRequest,
        receipt_formats: List[ReceiptFormat],
        access_token: Optional[str] = None,
    ) -> ReceiptTemplateResponse:
        body: Dict[str, Any] = {
            "receiptTemplateRequest": request.to_dict(),
            "formats": [f.value for f in receipt_formats],
        }
        # Include VAT metadata if present
        if request.buyer_country_code:
            body["buyerCountryCode"] = request.buyer_country_code
        if request.buyer_type:
            body["buyerType"] = request.buyer_type.value
        if request.taxes_applied is not None:
            body["taxesApplied"] = request.taxes_applied

        data = self._post(Endpoints.TEMPLATE, body, "generateReceiptTemplate", access_token)
        return ReceiptTemplateResponse.model_validate(data)

    def generate_credit_note_template(
        self,
        request: CreditNoteTemplateGenerationRequest,
        access_token: Optional[str] = None,
    ) -> CreditNoteTemplateResponse:
        data = self._post(
            Endpoints.CREDIT_NOTE_TEMPLATE,
            request.to_dict(),
            "generateCreditNoteTemplate",
            access_token,
        )
        return CreditNoteTemplateResponse.model_validate(data)

    def match_customer(
        self,
        request: IdentificationDetails,
        access_token: Optional[str] = None,
    ) -> RecipientResolutionResponse:
        data = self._post(
            Endpoints.CUSTOMER_MATCH,
            request.to_dict(),
            "matchCustomer",
            access_token,
        )
        return RecipientResolutionResponse.model_validate(data)

    def send_encrypted_receipts(
        self,
        match_id: str,
        encrypted_receipts: List[EncryptedReceiptRequestDto],
        template_hash: str,
        access_token: Optional[str] = None,
    ) -> ReceiptCreatedResponse:
        body = EncryptedReceiptsRequest(
            match_id=match_id,
            encrypted_receipts=encrypted_receipts,
            template_hash=template_hash,
        ).to_dict()
        data = self._post(
            Endpoints.ENCRYPTED_RECEIPT,
            body,
            "sendEncryptedReceipts",
            access_token,
        )
        return ReceiptCreatedResponse.model_validate(data)

    def upload_client_encrypted_receipt(
        self,
        request: ClientReceiptDownloadRequest,
        access_token: Optional[str] = None,
    ) -> ClientReceiptDownloadResponse:
        data = self._post(
            Endpoints.CLIENT_RECEIPT_DOWNLOAD,
            request.to_dict(),
            "uploadClientEncryptedReceipt",
            access_token,
        )
        return ClientReceiptDownloadResponse.model_validate(data)

    def send_encrypted_credit_notes(
        self,
        match_id: str,
        parent_cheqi_receipt_id: str,
        encrypted_credit_notes: List[EncryptedCreditNote],
        template_hash: str,
        access_token: Optional[str] = None,
    ) -> CreditNoteCreatedResponse:
        body = EncryptedCreditNotesRequest(
            match_id=match_id,
            parent_cheqi_receipt_id=parent_cheqi_receipt_id,
            encrypted_credit_notes=encrypted_credit_notes,
            template_hash=template_hash,
        ).to_dict()
        data = self._post(
            Endpoints.ENCRYPTED_CREDIT_NOTE,
            body,
            "sendEncryptedCreditNotes",
            access_token,
        )
        return CreditNoteCreatedResponse.model_validate(data)

    def send_receipt_via_email(
        self,
        customer_email: str,
        receipt_json: str,
        access_token: Optional[str] = None,
    ) -> None:
        body = {
            "customerEmail": customer_email,
            "cheqiReceipt": json.loads(receipt_json) if isinstance(receipt_json, str) else receipt_json,
        }
        self._post(Endpoints.EMAIL_RECEIPT, body, "sendReceiptViaEmail", access_token)

    # ===== Company Operations =====

    def provision_company(
        self, request: ProvisionCompanyRequest
    ) -> ProvisionCompanyResponse:
        data = self._post(
            Endpoints.COMPANY_PROVISION,
            request.to_dict(),
            "provisionCompany",
        )
        return ProvisionCompanyResponse.model_validate(data)

    # ===== Store Operations =====

    def create_store(
        self,
        company_id: UUID,
        request: CreateStoreRequest,
        access_token: Optional[str] = None,
    ) -> Store:
        path = Endpoints.company_stores(str(company_id))
        data = self._post(path, request.to_dict(), "createStore", access_token)
        return Store.model_validate(data)

    def get_stores(
        self,
        company_id: UUID,
        active_only: Optional[bool] = None,
        access_token: Optional[str] = None,
    ) -> List[Store]:
        path = Endpoints.company_stores(str(company_id))
        params: Dict[str, Any] = {}
        if active_only is not None:
            params["activeOnly"] = active_only
        data = self._get(path, "getStores", params=params, access_token=access_token)
        return [Store.model_validate(s) for s in data]

    def get_store(
        self,
        company_id: UUID,
        store_id: UUID,
        access_token: Optional[str] = None,
    ) -> Store:
        path = Endpoints.company_store(str(company_id), str(store_id))
        data = self._get(path, "getStore", access_token=access_token)
        return Store.model_validate(data)

    def update_store(
        self,
        company_id: UUID,
        store_id: UUID,
        request: CreateStoreRequest,
        access_token: Optional[str] = None,
    ) -> Store:
        path = Endpoints.company_store(str(company_id), str(store_id))
        data = self._put(path, request.to_dict(), "updateStore", access_token)
        return Store.model_validate(data)

    def delete_store(
        self,
        company_id: UUID,
        store_id: UUID,
        access_token: Optional[str] = None,
    ) -> None:
        path = Endpoints.company_store(str(company_id), str(store_id))
        self._delete(path, "deleteStore", access_token)

    def activate_store(
        self,
        company_id: UUID,
        store_id: UUID,
        access_token: Optional[str] = None,
    ) -> None:
        path = Endpoints.company_store_activate(str(company_id), str(store_id))
        self._post(path, {}, "activateStore", access_token)

    def deactivate_store(
        self,
        company_id: UUID,
        store_id: UUID,
        access_token: Optional[str] = None,
    ) -> None:
        path = Endpoints.company_store_deactivate(str(company_id), str(store_id))
        self._post(path, {}, "deactivateStore", access_token)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()
