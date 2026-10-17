"""Store management service."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from cheqi.http.client import CheqiApiClient
from cheqi.http.request_options import RequestOptions
from cheqi.models.generated.create_store_request import CreateStoreRequest
from cheqi.models.generated.store_dto import StoreDTO


class StoreService:
    """Service for store CRUD operations."""

    def __init__(self, api_client: CheqiApiClient) -> None:
        self._api_client = api_client

    def create_store(
        self, company_id: UUID, request: CreateStoreRequest, *, options: Optional[RequestOptions] = None
    ) -> StoreDTO:
        return self._api_client.create_store(company_id, request, options=options)

    def get_stores(
        self, company_id: UUID, active_only: Optional[bool] = None, *,
        options: Optional[RequestOptions] = None,
    ) -> List[StoreDTO]:
        return self._api_client.get_stores(company_id, active_only, options=options)

    def get_active_stores(self, company_id: UUID, *, options: Optional[RequestOptions] = None) -> List[StoreDTO]:
        """Return only active stores, matching the Java SDK convenience method."""
        return self._api_client.get_stores(company_id, True, options=options)

    def get_store(self, company_id: UUID, store_id: UUID, *, options: Optional[RequestOptions] = None) -> StoreDTO:
        return self._api_client.get_store(company_id, store_id, options=options)

    def update_store(
        self, company_id: UUID, store_id: UUID, request: CreateStoreRequest, *, options: Optional[RequestOptions] = None
    ) -> StoreDTO:
        return self._api_client.update_store(company_id, store_id, request, options=options)

    def delete_store(self, company_id: UUID, store_id: UUID, *, options: Optional[RequestOptions] = None) -> None:
        self._api_client.delete_store(company_id, store_id, options=options)

    def activate_store(self, company_id: UUID, store_id: UUID, *, options: Optional[RequestOptions] = None) -> None:
        self._api_client.activate_store(company_id, store_id, options=options)

    def deactivate_store(self, company_id: UUID, store_id: UUID, *, options: Optional[RequestOptions] = None) -> None:
        self._api_client.deactivate_store(company_id, store_id, options=options)
