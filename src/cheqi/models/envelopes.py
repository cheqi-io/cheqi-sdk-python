"""Envelope and result models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from cheqi.models.base import CheqiBaseModel
from cheqi.models.receipt import CheqiReceipt, ReceivingParty, VatMetadata


class ReceiptEnvelope(CheqiBaseModel):
    """Envelope containing multiple receipt format representations."""

    cheqi_receipt: Optional[CheqiReceipt] = None
    ubl_purchase_receipt: Optional[str] = None
    vat_metadata: Optional[VatMetadata] = None


class ConsumingPartyEnvelope(CheqiBaseModel):
    """Envelope for customer party details."""

    receiving_party: Optional[ReceivingParty] = None
    xml_party: Optional[str] = None


class ReceiptCreatedResponse(CheqiBaseModel):
    """Response after sending encrypted receipts."""

    cheqi_receipt_id: Optional[str] = None
    created_at: Optional[datetime] = None
    template_hash: Optional[str] = None


class DeliveryStatus(str, Enum):
    """Delivery status for receipt processing results."""

    DELIVERED_TO_APP = "DELIVERED_TO_APP"
    DELIVERED_VIA_EMAIL = "DELIVERED_VIA_EMAIL"
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    FAILED = "FAILED"


class ReceiptResult(CheqiBaseModel):
    """Result of a receipt processing operation."""

    success: bool = False
    delivery_status: Optional[DeliveryStatus] = None
    cheqi_receipt_id: Optional[str] = None
    template_hash: Optional[str] = None
    canonical_json: Optional[str] = None
    email_address: Optional[str] = None

    @classmethod
    def delivered_to_app(cls, response: ReceiptCreatedResponse, canonical_json: Optional[str] = None) -> ReceiptResult:
        return cls(
            success=True,
            delivery_status=DeliveryStatus.DELIVERED_TO_APP,
            cheqi_receipt_id=response.cheqi_receipt_id,
            template_hash=response.template_hash,
            canonical_json=canonical_json,
        )

    @classmethod
    def delivered_via_email(cls, email: str) -> ReceiptResult:
        return cls(
            success=True,
            delivery_status=DeliveryStatus.DELIVERED_VIA_EMAIL,
            email_address=email,
        )

    @classmethod
    def customer_not_found(cls) -> ReceiptResult:
        return cls(
            success=False,
            delivery_status=DeliveryStatus.CUSTOMER_NOT_FOUND,
        )

    @classmethod
    def failed(cls, reason: Optional[str] = None) -> ReceiptResult:
        return cls(
            success=False,
            delivery_status=DeliveryStatus.FAILED,
        )
