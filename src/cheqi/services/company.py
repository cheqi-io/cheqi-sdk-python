"""Company membership operations."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from cheqi.http.client import CheqiApiClient
from cheqi.models.generated.destination_response import DestinationResponse
from cheqi.models.generated.invite_employees_response import InviteEmployeesResponse
from cheqi.models.generated.register_request import RegisterRequest
from cheqi.models.generated.register_response import RegisterResponse
from cheqi.models.generated.webhook_receipt_envelope import WebhookReceiptEnvelope


class CompanyService:
    def __init__(self, api_client: CheqiApiClient) -> None:
        self._api_client = api_client

    def invite_users(
        self, company_id: UUID, emails: List[str], access_token: Optional[str] = None,
        resend_pending: Optional[bool] = None,
    ) -> InviteEmployeesResponse:
        """Send employee invitations and return their outcomes."""
        if not emails:
            raise ValueError("At least one email is required")
        return self._api_client.invite_users(company_id, emails, access_token, resend_pending)

    def list_receipt_destinations(self, access_token: Optional[str] = None) -> List[DestinationResponse]:
        return self._api_client.list_receipt_destinations(access_token)

    def register_receipt_destination(
        self, request: RegisterRequest, access_token: Optional[str] = None,
    ) -> RegisterResponse:
        return self._api_client.register_receipt_destination(request, access_token)

    def get_pending_receipts(
        self, destination_id: UUID, access_token: Optional[str] = None,
    ) -> List[WebhookReceiptEnvelope]:
        return self._api_client.get_pending_receipts(destination_id, access_token)

    def acknowledge_receipts(
        self, destination_id: UUID, receipt_ids: List[str], access_token: Optional[str] = None,
    ) -> None:
        self._api_client.acknowledge_receipts(destination_id, receipt_ids, access_token)

    def deactivate_receipt_destination(
        self, destination_id: UUID, access_token: Optional[str] = None,
    ) -> None:
        self._api_client.deactivate_receipt_destination(destination_id, access_token)
