"""Company and Store models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from cheqi.models.base import CheqiBaseModel


class CompanyAddress(CheqiBaseModel):
    """Address for company/store provisioning (richer than receipt Address)."""

    street_name: Optional[str] = None
    additional_street_name: Optional[str] = None
    address_line: Optional[str] = None
    region: Optional[str] = None
    city_name: Optional[str] = None
    postal_zone: Optional[str] = None
    country_iso_code: Optional[str] = None


class Company(CheqiBaseModel):
    """Company details for provisioning."""

    name: Optional[str] = None
    legal_name: Optional[str] = None
    kvk_number: Optional[str] = None
    tax_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[CompanyAddress] = None


class ProvisionCompanyRequest(CheqiBaseModel):
    """Request to provision a new company."""

    company: Optional[Company] = None
    admin_email: Optional[str] = None


class ProvisionCompanyResponse(CheqiBaseModel):
    """Response from company provisioning."""

    company_id: Optional[UUID] = None
    status: Optional[str] = None
    api_key: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


class CreateStoreRequest(CheqiBaseModel):
    """Request to create a store."""

    store_name: Optional[str] = None
    store_code: Optional[str] = None
    address: Optional[CompanyAddress] = None


class Store(CheqiBaseModel):
    """Store details."""

    id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    store_name: Optional[str] = None
    store_code: Optional[str] = None
    address: Optional[CompanyAddress] = None
    is_active: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
