"""Company provisioning service."""

from __future__ import annotations

from cheqi.http.client import CheqiApiClient
from cheqi.models.company import ProvisionCompanyRequest, ProvisionCompanyResponse


class CompanyService:
    """Service for company provisioning."""

    def __init__(self, api_client: CheqiApiClient) -> None:
        self._api_client = api_client

    def provision_company(self, request: ProvisionCompanyRequest) -> ProvisionCompanyResponse:
        """Provision a new company. Only available for partner-tier API keys."""
        return self._api_client.provision_company(request)
