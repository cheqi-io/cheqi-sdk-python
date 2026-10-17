"""Company membership operations."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from cheqi.http.client import CheqiApiClient
from cheqi.http.request_options import RequestOptions
from cheqi.models.generated.destination_response import DestinationResponse
from cheqi.models.generated.invite_employees_response import InviteEmployeesResponse
from cheqi.models.generated.register_request import RegisterRequest
from cheqi.models.generated.register_response import RegisterResponse
from cheqi.models.generated.webhook_receipt_envelope import WebhookReceiptEnvelope


class CompanyService:
    def __init__(self, api_client: CheqiApiClient) -> None:
        self._api_client = api_client

    def invite_users(
        self, company_id: UUID, emails: List[str], resend_pending: Optional[bool] = None,
        *, options: Optional[RequestOptions] = None,
    ) -> InviteEmployeesResponse:
        """Send employee invitations and return their outcomes."""
        if not emails:
            raise ValueError("At least one email is required")
        return self._api_client.invite_users(company_id, emails, resend_pending, options=options)

    def list_receipt_destinations(self, *, options: Optional[RequestOptions] = None) -> List[DestinationResponse]:
        return self._api_client.list_receipt_destinations(options=options)

    def register_receipt_destination(
        self, request: RegisterRequest, *, options: Optional[RequestOptions] = None,
    ) -> RegisterResponse:
        return self._api_client.register_receipt_destination(request, options=options)

    def get_pending_receipts(
        self, destination_id: UUID, *, options: Optional[RequestOptions] = None,
    ) -> List[WebhookReceiptEnvelope]:
        return self._api_client.get_pending_receipts(destination_id, options=options)

    def acknowledge_receipts(
        self, destination_id: UUID, receipt_ids: List[str], *, options: Optional[RequestOptions] = None,
    ) -> None:
        self._api_client.acknowledge_receipts(destination_id, receipt_ids, options=options)

    def deactivate_receipt_destination(
        self, destination_id: UUID, *, options: Optional[RequestOptions] = None,
    ) -> None:
        self._api_client.deactivate_receipt_destination(destination_id, options=options)
