"""Receipt envelope, customer-context, and processing-result models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import AliasChoices, Field

from cheqi.models.base import CheqiBaseModel
from cheqi.models.receipt import CheqiReceipt, ReceivingParty, VatMetadata


class ReceiptEnvelope(CheqiBaseModel):
    """Recipient plaintext containing only the requested receipt formats."""

    cheqi: Optional[CheqiReceipt] = Field(
        default=None,
        validation_alias=AliasChoices("cheqi", "cheqiReceipt", "cheqi_receipt"),
        serialization_alias="cheqi",
    )
    ubl_purchase_receipt: Optional[str] = None
    ubl_invoice: Optional[str] = None
    vat_metadata: Optional[VatMetadata] = Field(
        default=None,
        validation_alias=AliasChoices("vatMetaData", "vatMetadata", "vat_metadata"),
        serialization_alias="vatMetaData",
    )

    @property
    def cheqi_receipt(self) -> Optional[CheqiReceipt]:
        """Backward-compatible alias for ``cheqi``."""
        return self.cheqi


class ReceivingPartyEnvelope(CheqiBaseModel):
    """Recipient-specific party context in UBL and Cheqi JSON forms."""

    xml_receiving_party: Optional[str] = None
    receiving_party: Optional[ReceivingParty] = None


class PaymentMeansEnvelope(CheqiBaseModel):
    """Recipient-specific payment context and optional UBL fragment."""

    payment_means_code: Optional[str] = None
    description: Optional[str] = None
    card_provider: Optional[str] = None
    card_last_four: Optional[str] = None
    account_identifier: Optional[str] = None
    account_identifier_type: Optional[str] = None
    xml_payment_means: Optional[str] = None


class ReceiptContextEnvelope(CheqiBaseModel):
    """Customer context encrypted separately by Cheqi."""

    receiving_party: Optional[ReceivingPartyEnvelope] = None
    payment_means: Optional[PaymentMeansEnvelope] = None


# Credit-note context has the same wire shape as receipt context.
CreditNoteContextEnvelope = ReceiptContextEnvelope


class ConsumingPartyEnvelope(CheqiBaseModel):
    """Legacy customer party envelope retained for compatibility."""

    receiving_party: Optional[ReceivingParty] = None
    xml_party: Optional[str] = None


class ReceiptCreatedResponse(CheqiBaseModel):
    """Response after sending encrypted receipts."""

    cheqi_receipt_id: Optional[str] = None
    created_at: Optional[datetime] = None
    template_hash: Optional[str] = None
    download_url: Optional[str] = None


class DeliveryStatus(str, Enum):
    """Delivery status aligned with the Java SDK."""

    DELIVERED_DIGITAL = "DELIVERED_DIGITAL"
    DELIVERED_TO_APP = "DELIVERED_DIGITAL"  # compatibility alias
    DELIVERED_EMAIL = "DELIVERED_EMAIL"
    DELIVERED_VIA_EMAIL = "DELIVERED_EMAIL"  # compatibility alias
    DELIVERED_DOWNLOAD = "DELIVERED_DOWNLOAD"
    PENDING_DOWNLOAD_TEMPLATE = "PENDING_DOWNLOAD_TEMPLATE"
    PENDING_DOWNLOAD_UPLOAD = "PENDING_DOWNLOAD_UPLOAD"
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    FAILED = "FAILED"


class ReceiptResult(CheqiBaseModel):
    """Result of receipt delivery, including data needed for safe deferred work."""

    success: bool = False
    delivery_status: Optional[DeliveryStatus] = None
    cheqi_receipt_id: Optional[str] = None
    created_at: Optional[datetime] = None
    template_hash: Optional[str] = None
    canonical_json: Optional[str] = None
    email_address: Optional[str] = None
    download_url: Optional[str] = None
    download_ciphertext: Optional[str] = None
    message: Optional[str] = None

    @property
    def is_customer_not_found(self) -> bool:
        return self.delivery_status is DeliveryStatus.CUSTOMER_NOT_FOUND

    @classmethod
    def delivered_to_app(cls, response: ReceiptCreatedResponse, canonical_json: Optional[str] = None) -> ReceiptResult:
        return cls(
            success=True,
            delivery_status=DeliveryStatus.DELIVERED_DIGITAL,
            cheqi_receipt_id=response.cheqi_receipt_id,
            created_at=response.created_at,
            template_hash=response.template_hash,
            canonical_json=canonical_json,
            message="Receipt delivered to customer's Cheqi app",
        )

    @classmethod
    def delivered_via_download(
        cls, response: ReceiptCreatedResponse, canonical_json: Optional[str] = None
    ) -> ReceiptResult:
        return cls(
            success=True,
            delivery_status=DeliveryStatus.DELIVERED_DOWNLOAD,
            cheqi_receipt_id=response.cheqi_receipt_id,
            created_at=response.created_at,
            template_hash=response.template_hash,
            canonical_json=canonical_json,
            download_url=response.download_url,
            message="Receipt available for self-service download",
        )

    @classmethod
    def delivered_via_client_download(
        cls,
        response: object,
        template_hash: str,
        canonical_json: str,
        download_url: str,
    ) -> ReceiptResult:
        return cls(
            success=True,
            delivery_status=DeliveryStatus.DELIVERED_DOWNLOAD,
            cheqi_receipt_id=getattr(response, "cheqi_receipt_id", None),
            created_at=getattr(response, "created_at", None),
            template_hash=template_hash,
            canonical_json=canonical_json,
            download_url=download_url,
            message="Receipt available through an encrypted download link",
        )

    @classmethod
    def delivered_via_email(cls, email: str) -> ReceiptResult:
        return cls(
            success=True,
            delivery_status=DeliveryStatus.DELIVERED_EMAIL,
            created_at=datetime.now().astimezone(),
            email_address=email,
            message=f"Receipt sent via email to {email}",
        )

    @classmethod
    def pending_download_template(cls, download_url: str, message: str) -> ReceiptResult:
        return cls(
            success=True,
            delivery_status=DeliveryStatus.PENDING_DOWNLOAD_TEMPLATE,
            download_url=download_url,
            message=message,
        )

    @classmethod
    def pending_download_upload(
        cls,
        download_url: str,
        ciphertext: str,
        template_hash: str,
        canonical_json: str,
        message: str,
    ) -> ReceiptResult:
        return cls(
            success=True,
            delivery_status=DeliveryStatus.PENDING_DOWNLOAD_UPLOAD,
            template_hash=template_hash,
            canonical_json=canonical_json,
            download_url=download_url,
            download_ciphertext=ciphertext,
            message=message,
        )

    @classmethod
    def customer_not_found(cls) -> ReceiptResult:
        return cls(
            success=False,
            delivery_status=DeliveryStatus.CUSTOMER_NOT_FOUND,
            message="Customer not found with provided payment details",
        )

    @classmethod
    def failed(cls, reason: Optional[str] = None) -> ReceiptResult:
        return cls(success=False, delivery_status=DeliveryStatus.FAILED, message=reason)
