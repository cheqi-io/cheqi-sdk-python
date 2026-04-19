"""Credit note models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID

from cheqi.models.base import CheqiBaseModel, CheqiDecimal
from cheqi.models.generated.credit_note_context_envelope import CreditNoteContextEnvelope
from cheqi.models.enums import ReceiptFormat, ReceiverType, RefundPreference, ReturnCondition
from cheqi.models.receipt import (
    Barcode,
    Charge,
    CheqiReceipt,
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
    receipt_subtotal: Optional[CheqiDecimal] = None
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
    receipt_formats: Optional[List[ReceiptFormat]] = None


class CheqiCreditNote(CheqiBaseModel):
    """Full credit note model returned by the backend."""

    document_number: Optional[str] = None
    originator_document_reference: Optional[str] = None
    identifiers: Optional[List[Identifier]] = None
    issue_date: Optional[datetime] = None
    currency: Optional[str] = None
    receipt_subtotal: Optional[CheqiDecimal] = None
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
    verification_nonce: Optional[str] = None


class CreditNoteTemplateResponse(CheqiBaseModel):
    """Response from credit note template generation."""

    ubl: Optional[str] = None
    cheqi: Optional[CheqiCreditNote] = None
    vat_metadata: Optional[VatMetadata] = None


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
    receiver_type: Optional[ReceiverType] = None
    encrypted_credit_note: Optional[str] = None
    encrypted_symmetric_key: Optional[str] = None
    public_key: Optional[str] = None
    receipt_formats: Optional[List[ReceiptFormat]] = None


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

    DELIVERED_TO_APP = "DELIVERED_TO_APP"
    DELIVERED_VIA_EMAIL = "DELIVERED_VIA_EMAIL"
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    FAILED = "FAILED"


class CreditNoteResult(CheqiBaseModel):
    """Result of a credit note processing operation."""

    success: bool = False
    delivery_status: Optional[CreditNoteDeliveryStatus] = None
    cheqi_receipt_id: Optional[str] = None
    parent_cheqi_receipt_id: Optional[str] = None
    template_hash: Optional[str] = None
    canonical_json: Optional[str] = None

    @classmethod
    def delivered_to_app(
        cls, response: CreditNoteCreatedResponse, canonical_json: Optional[str] = None
    ) -> CreditNoteResult:
        return cls(
            success=True,
            delivery_status=CreditNoteDeliveryStatus.DELIVERED_TO_APP,
            cheqi_receipt_id=response.cheqi_receipt_id,
            parent_cheqi_receipt_id=response.parent_cheqi_receipt_id,
            template_hash=response.template_hash,
            canonical_json=canonical_json,
        )

    @classmethod
    def customer_not_found(cls) -> CreditNoteResult:
        return cls(success=False, delivery_status=CreditNoteDeliveryStatus.CUSTOMER_NOT_FOUND)
