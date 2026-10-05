"""Company membership operations."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from cheqi.http.client import CheqiApiClient


class CompanyService:
    def __init__(self, api_client: CheqiApiClient) -> None:
        self._api_client = api_client

    def invite_users(
        self, company_id: UUID, emails: List[str], access_token: Optional[str] = None
    ) -> None:
        """Send employee invitations. The successful API response has no body."""
        if not emails:
            raise ValueError("At least one email is required")
        self._api_client.invite_users(company_id, emails, access_token)
