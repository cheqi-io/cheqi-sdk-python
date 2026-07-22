"""Store management service."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from cheqi.http.client import CheqiApiClient
from cheqi.models.company import CreateStoreRequest, Store


class StoreService:
    """Service for store CRUD operations."""

    def __init__(self, api_client: CheqiApiClient) -> None:
        self._api_client = api_client

    def create_store(
        self, company_id: UUID, request: CreateStoreRequest, access_token: Optional[str] = None
    ) -> Store:
        return self._api_client.create_store(company_id, request, access_token)

    def get_stores(
        self, company_id: UUID, active_only: Optional[bool] = None, access_token: Optional[str] = None
    ) -> List[Store]:
        return self._api_client.get_stores(company_id, active_only, access_token)

    def get_active_stores(
        self, company_id: UUID, access_token: Optional[str] = None
    ) -> List[Store]:
        """Return only active stores, matching the Java SDK convenience method."""
        return self._api_client.get_stores(company_id, True, access_token)

    def get_store(
        self, company_id: UUID, store_id: UUID, access_token: Optional[str] = None
    ) -> Store:
        return self._api_client.get_store(company_id, store_id, access_token)

    def update_store(
        self, company_id: UUID, store_id: UUID, request: CreateStoreRequest, access_token: Optional[str] = None
    ) -> Store:
        return self._api_client.update_store(company_id, store_id, request, access_token)

    def delete_store(
        self, company_id: UUID, store_id: UUID, access_token: Optional[str] = None
    ) -> None:
        self._api_client.delete_store(company_id, store_id, access_token)

    def activate_store(
        self, company_id: UUID, store_id: UUID, access_token: Optional[str] = None
    ) -> None:
        self._api_client.activate_store(company_id, store_id, access_token)

    def deactivate_store(
        self, company_id: UUID, store_id: UUID, access_token: Optional[str] = None
    ) -> None:
        self._api_client.deactivate_store(company_id, store_id, access_token)
