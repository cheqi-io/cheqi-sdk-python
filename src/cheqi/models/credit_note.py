"""Credit note models."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import AliasChoices, Field

from cheqi.models.base import CheqiBaseModel, CheqiDecimal
from cheqi.models.enums import ReceiptFormat, RefundPreference, ReturnCondition
from cheqi.models.envelopes import CreditNoteContextEnvelope
from cheqi.models.receipt import (
    Barcode,
    Charge,
    Discount,
    Identifier,
    Period,
    Product,
    ReceivingParty,
    SellingParty,
    Tax,
    VatMetadata,
)


class ReturnLineItem(CheqiBaseModel):
    """Line item being returned."""

    line_item_id: Optional[str] = None
    quantity_returned: Optional[float] = None
    condition: Optional[ReturnCondition] = None
    condition_notes: Optional[str] = None


class RefundBankAccount(CheqiBaseModel):
    """Bank account for refund payments."""

    iban: Optional[str] = None
    bic: Optional[str] = None
    account_holder: Optional[str] = None


class CreditNoteInitiationRequest(CheqiBaseModel):
    """Parsed credit note request from a customer."""

    cheqi_receipt_id: Optional[str] = None
    receipt_id: Optional[str] = None
    return_reason: Optional[str] = None
    return_reason_description: Optional[str] = None
    line_items: Optional[List[ReturnLineItem]] = None
    refund_preference: Optional[RefundPreference] = None
    refund_bank_account: Optional[RefundBankAccount] = None


class CreditNoteTemplateRequest(CheqiBaseModel):
    """Request for generating credit note templates."""

    child_company_id: Optional[UUID] = None
    document_number: Optional[str] = None
    originator_document_reference: Optional[str] = None
    identifiers: Optional[List[Identifier]] = None
    issue_date: Optional[datetime] = None
    currency: Optional[str] = None
    credit_note_subtotal: Optional[CheqiDecimal] = Field(
        default=None,
        validation_alias=AliasChoices(
            "creditNoteSubtotal", "credit_note_subtotal", "receiptSubtotal", "receipt_subtotal"
        ),
        serialization_alias="creditNoteSubtotal",
    )
    total_before_tax: Optional[CheqiDecimal] = None
    total_tax_amount: Optional[CheqiDecimal] = None
    total_amount: Optional[CheqiDecimal] = None
    products: Optional[List[Product]] = None
    discounts: Optional[List[Discount]] = None
    charges: Optional[List[Charge]] = None
    taxes: Optional[List[Tax]] = None
    transaction_date: Optional[datetime] = None
    purchase_date: Optional[datetime] = None
    period: Optional[Period] = None
    barcodes: Optional[List[Barcode]] = None
    note: Optional[str] = None
    buyer_country_code: Optional[str] = None

    @property
    def receipt_subtotal(self) -> Optional[CheqiDecimal]:
        """Backward-compatible alias for ``credit_note_subtotal``."""
        return self.credit_note_subtotal

    def to_dict(self) -> dict[str, object]:
        data = super().to_dict()
        data.pop("buyerCountryCode", None)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), ensure_ascii=False)

    def add_product(self, product: Product) -> CreditNoteTemplateRequest:
        existing = list(self.products) if self.products else []
        existing.append(product)
        return self.model_copy(update={"products": existing})

    def add_tax(self, tax: Tax) -> CreditNoteTemplateRequest:
        existing = list(self.taxes) if self.taxes else []
        existing.append(tax)
        return self.model_copy(update={"taxes": existing})

    def add_discount(self, discount: Discount) -> CreditNoteTemplateRequest:
        existing = list(self.discounts) if self.discounts else []
        existing.append(discount)
        return self.model_copy(update={"discounts": existing})

    def add_charge(self, charge: Charge) -> CreditNoteTemplateRequest:
        existing = list(self.charges) if self.charges else []
        existing.append(charge)
        return self.model_copy(update={"charges": existing})


class CreditNoteTemplateGenerationRequest(CheqiBaseModel):
    """Wrapper for credit note template request with format info."""

    credit_note_template_request: Optional[CreditNoteTemplateRequest] = None
    formats: Optional[List[ReceiptFormat]] = Field(
        default=None,
        validation_alias=AliasChoices("formats", "receiptFormats", "receipt_formats"),
        serialization_alias="formats",
    )
    buyer_country_code: Optional[str] = None
    buyer_type: Optional[str] = None
    taxes_applied: Optional[bool] = None

    @property
    def receipt_formats(self) -> Optional[List[ReceiptFormat]]:
        """Backward-compatible alias for ``formats``."""
        return self.formats


class CheqiCreditNote(CheqiBaseModel):
    """Full credit note model returned by the backend."""

    cheqi_credit_note_id: Optional[str] = None
    document_number: Optional[str] = None
    originator_document_reference: Optional[str] = None
    identifiers: Optional[List[Identifier]] = None
    issue_date: Optional[datetime] = None
    currency: Optional[str] = None
    credit_note_subtotal: Optional[CheqiDecimal] = Field(
        default=None,
        validation_alias=AliasChoices(
            "creditNoteSubtotal", "credit_note_subtotal", "receiptSubtotal", "receipt_subtotal"
        ),
        serialization_alias="creditNoteSubtotal",
    )
    total_before_tax: Optional[CheqiDecimal] = None
    total_tax_amount: Optional[CheqiDecimal] = None
    total_amount: Optional[CheqiDecimal] = None
    products: Optional[List[Product]] = None
    discounts: Optional[List[Discount]] = None
    charges: Optional[List[Charge]] = None
    taxes: Optional[List[Tax]] = None
    period: Optional[Period] = None
    note: Optional[str] = None
    barcodes: Optional[List[Barcode]] = None
    selling_party: Optional[SellingParty] = None
    receiving_party: Optional[ReceivingParty] = None
    receipt_uuid: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("receiptUuid", "receipt_uuid", "verificationNonce", "verification_nonce"),
        serialization_alias="receiptUuid",
    )

    @property
    def receipt_subtotal(self) -> Optional[CheqiDecimal]:
        return self.credit_note_subtotal

    @property
    def verification_nonce(self) -> Optional[str]:
        return self.receipt_uuid


class CreditNoteTemplateResponse(CheqiBaseModel):
    """Response from credit note template generation."""

    ubl_credit_note: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("ublCreditNote", "ubl_credit_note", "ubl"),
        serialization_alias="ublCreditNote",
    )
    cheqi: Optional[CheqiCreditNote] = None
    vat_metadata: Optional[VatMetadata] = None

    @property
    def ubl(self) -> Optional[str]:
        """Backward-compatible alias for ``ubl_credit_note``."""
        return self.ubl_credit_note


class CreditNoteEnvelope(CheqiBaseModel):
    """Envelope containing credit note format representations."""

    cheqi_credit_note: Optional[CheqiCreditNote] = None
    ubl_credit_note: Optional[str] = None
    vat_metadata: Optional[VatMetadata] = None


class EncryptedCreditNote(CheqiBaseModel):
    """Encrypted credit note ready for delivery."""

    recipient_id: Optional[str] = None
    credit_note_id: Optional[str] = None
    original_receipt_id: Optional[str] = None
    encrypted_credit_note: Optional[str] = None
    encrypted_symmetric_key: Optional[str] = None
    encrypted_customer_details: Optional[str] = None
    encrypted_customer_aes_key: Optional[str] = None
    final_hash: Optional[str] = None
    public_key: Optional[str] = None


class EncryptedCreditNotesRequest(CheqiBaseModel):
    """Wrapper for sending encrypted credit notes."""

    match_id: Optional[str] = None
    parent_cheqi_receipt_id: Optional[str] = None
    encrypted_credit_notes: Optional[List[EncryptedCreditNote]] = None
    template_hash: Optional[str] = None


class EncryptedCreditNoteInitiationRequest(CheqiBaseModel):
    """Customer-initiated encrypted credit note request (for decryption)."""

    cheqi_receipt_id: Optional[str] = None
    public_key: Optional[str] = None
    encrypted_credit_note_initiation_request: Optional[str] = None
    encrypted_symmetric_key: Optional[str] = None


class CreditNoteCreatedResponse(CheqiBaseModel):
    """Response after sending encrypted credit notes."""

    cheqi_receipt_id: Optional[str] = None
    parent_cheqi_receipt_id: Optional[str] = None
    created_at: Optional[datetime] = None
    template_hash: Optional[str] = None


class DecryptedDeliveredCreditNote(CheqiBaseModel):
    """Decrypted delivered credit note plus optional credit note context envelope."""

    credit_note_envelope: CreditNoteEnvelope
    credit_note_context_envelope: Optional[CreditNoteContextEnvelope] = None
    raw_json: str
    raw_credit_note_context_json: Optional[str] = None


class CreditNoteDeliveryStatus(str, Enum):
    """Delivery status for credit note processing results."""

    DELIVERED_DIGITAL = "DELIVERED_DIGITAL"
    DELIVERED_TO_APP = "DELIVERED_DIGITAL"
    DELIVERED_EMAIL = "DELIVERED_EMAIL"
    DELIVERED_VIA_EMAIL = "DELIVERED_EMAIL"
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    FAILED = "FAILED"


class CreditNoteResult(CheqiBaseModel):
    """Result of a credit note processing operation."""

    success: bool = False
    delivery_status: Optional[CreditNoteDeliveryStatus] = None
    cheqi_receipt_id: Optional[str] = None
    parent_cheqi_receipt_id: Optional[str] = None
    created_at: Optional[datetime] = None
    template_hash: Optional[str] = None
    canonical_json: Optional[str] = None
    email_address: Optional[str] = None
    message: Optional[str] = None

    @classmethod
    def delivered_to_app(
        cls, response: CreditNoteCreatedResponse, canonical_json: Optional[str] = None
    ) -> CreditNoteResult:
        return cls(
            success=True,
            delivery_status=CreditNoteDeliveryStatus.DELIVERED_DIGITAL,
            cheqi_receipt_id=response.cheqi_receipt_id,
            parent_cheqi_receipt_id=response.parent_cheqi_receipt_id,
            created_at=response.created_at,
            template_hash=response.template_hash,
            canonical_json=canonical_json,
            message="Receipt delivered to customer's Cheqi app",
        )

    @classmethod
    def customer_not_found(cls) -> CreditNoteResult:
        return cls(
            success=False,
            delivery_status=CreditNoteDeliveryStatus.CUSTOMER_NOT_FOUND,
            message="Customer not found with provided payment details",
        )
