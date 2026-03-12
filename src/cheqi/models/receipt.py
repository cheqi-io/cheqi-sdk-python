"""Receipt-related models: Product, Tax, Discount, Charge, CheqiReceipt, ReceiptTemplateRequest."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from cheqi.models.base import CheqiBaseModel, CheqiDecimal
from cheqi.models.enums import BarcodeType, RecipientEntityType, UnitCode

if TYPE_CHECKING:
    pass


class Identifier(CheqiBaseModel):
    """Simple type/value pair for merchant identifiers (order number, POS ticket, etc.)."""

    type: Optional[str] = None
    value: Optional[str] = None


class Period(CheqiBaseModel):
    """Billing or service period."""

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    description: Optional[str] = None


class Barcode(CheqiBaseModel):
    """Barcode or QR code attached to a receipt or product."""

    type: Optional[BarcodeType] = None
    data: Optional[str] = None
    label: Optional[str] = None

    @classmethod
    def qr_code(cls, data: str, label: str) -> Barcode:
        return cls(type=BarcodeType.QR_CODE, data=data, label=label)

    @classmethod
    def of(cls, barcode_type: BarcodeType, data: str, label: str) -> Barcode:
        return cls(type=barcode_type, data=data, label=label)


class Tax(CheqiBaseModel):
    """Tax applied to a product line or receipt."""

    rate: Optional[float] = None
    type: Optional[str] = None
    taxable_amount: Optional[CheqiDecimal] = None
    amount: Optional[CheqiDecimal] = None
    label: Optional[str] = None


class Discount(CheqiBaseModel):
    """Discount applied to a product or receipt."""

    amount: Optional[CheqiDecimal] = None
    percentage: Optional[float] = None
    label: Optional[str] = None

    @classmethod
    def of(cls, amount: Decimal | str, label: str, percentage: Optional[float] = None) -> Discount:
        if isinstance(amount, str):
            amount = Decimal(amount)
        return cls(amount=amount, label=label, percentage=percentage)


class Charge(CheqiBaseModel):
    """Extra charge applied to a product or receipt."""

    amount: Optional[CheqiDecimal] = None
    percentage: Optional[float] = None
    label: Optional[str] = None

    @classmethod
    def of(cls, amount: Decimal | str, label: str, percentage: Optional[float] = None) -> Charge:
        if isinstance(amount, str):
            amount = Decimal(amount)
        return cls(amount=amount, label=label, percentage=percentage)


class ItemClassification(CheqiBaseModel):
    """Product classification (EAN, GTIN, UNSPSC, etc.)."""

    list_id: Optional[str] = None
    value: Optional[str] = None


class Product(CheqiBaseModel):
    """Product line item on a receipt."""

    name: Optional[str] = None
    identifier: Optional[str] = None
    description: Optional[str] = None
    brand_name: Optional[str] = None
    quantity: Optional[float] = None
    base_quantity: Optional[float] = None
    unit_code: Optional[UnitCode] = None
    unit_price: Optional[CheqiDecimal] = None
    discounts: Optional[List[Discount]] = None
    charges: Optional[List[Charge]] = None
    taxes: Optional[List[Tax]] = None
    subtotal: Optional[CheqiDecimal] = None
    total: Optional[CheqiDecimal] = None
    barcodes: Optional[List[Barcode]] = None
    period: Optional[Period] = None

    def add_tax(self, tax: Tax) -> Product:
        """Return a new Product with an additional tax."""
        existing = list(self.taxes) if self.taxes else []
        existing.append(tax)
        return self.model_copy(update={"taxes": existing})

    def add_discount(self, discount: Discount) -> Product:
        """Return a new Product with an additional discount."""
        existing = list(self.discounts) if self.discounts else []
        existing.append(discount)
        return self.model_copy(update={"discounts": existing})

    def add_charge(self, charge: Charge) -> Product:
        """Return a new Product with an additional charge."""
        existing = list(self.charges) if self.charges else []
        existing.append(charge)
        return self.model_copy(update={"charges": existing})

    def add_barcode(self, barcode: Barcode) -> Product:
        """Return a new Product with an additional barcode."""
        existing = list(self.barcodes) if self.barcodes else []
        existing.append(barcode)
        return self.model_copy(update={"barcodes": existing})


class CompanyIdentifier(CheqiBaseModel):
    """Company registration identifier."""

    id: Optional[str] = None
    identifier_type: Optional[str] = None
    registration_scheme: Optional[str] = None
    value: Optional[str] = None
    country_code: Optional[str] = None
    is_verified: Optional[bool] = None


class Address(CheqiBaseModel):
    """Simple address for receipt parties."""

    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None


class SellingParty(CheqiBaseModel):
    """Merchant/seller information."""

    company_name: Optional[str] = None
    company_legal_name: Optional[str] = None
    tax_number: Optional[str] = None
    identifiers: Optional[List[CompanyIdentifier]] = None
    address: Optional[Address] = None


class ReceivingParty(CheqiBaseModel):
    """Customer/receiver information."""

    company_legal_name: Optional[str] = None
    tax_number: Optional[str] = None
    company_identifiers: Optional[List[CompanyIdentifier]] = None
    consumer_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[Address] = None


class PaymentInfo(CheqiBaseModel):
    """Payment information on a receipt."""

    payment_type: Optional[str] = None
    payment_account_reference: Optional[str] = None
    card_issuer: Optional[str] = None
    card_brand: Optional[str] = None
    last_four_digits: Optional[str] = None
    payment_ids: Optional[List[str]] = None


class CheqiReceipt(CheqiBaseModel):
    """Cheqi receipt as returned by the backend after template generation."""

    document_number: Optional[str] = None
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
    payment_info: Optional[PaymentInfo] = None


class VatMetadata(CheqiBaseModel):
    """VAT metadata for cross-border tax determination."""

    supplier_country: Optional[str] = None
    buyer_country: Optional[str] = None
    cross_border: Optional[bool] = None
    recipient_entity_type: Optional[RecipientEntityType] = None
    vat_on_receipt: Optional[bool] = None
    vat_regime: Optional[str] = None
    taxes_applied: Optional[bool] = None


class ReceiptTemplateRequest(CheqiBaseModel):
    """Request DTO for generating receipt templates."""

    child_company_id: Optional[UUID] = None
    document_number: Optional[str] = None
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
    # VAT metadata — not serialized in the inner request JSON, used by API client
    buyer_country_code: Optional[str] = None
    recipient_entity_type: Optional[RecipientEntityType] = None
    taxes_applied: Optional[bool] = None

    def add_product(self, product: Product) -> ReceiptTemplateRequest:
        """Return a new request with an additional product."""
        existing = list(self.products) if self.products else []
        existing.append(product)
        return self.model_copy(update={"products": existing})

    def add_tax(self, tax: Tax) -> ReceiptTemplateRequest:
        """Return a new request with an additional tax."""
        existing = list(self.taxes) if self.taxes else []
        existing.append(tax)
        return self.model_copy(update={"taxes": existing})

    def add_discount(self, discount: Discount) -> ReceiptTemplateRequest:
        """Return a new request with an additional discount."""
        existing = list(self.discounts) if self.discounts else []
        existing.append(discount)
        return self.model_copy(update={"discounts": existing})

    def add_charge(self, charge: Charge) -> ReceiptTemplateRequest:
        """Return a new request with an additional charge."""
        existing = list(self.charges) if self.charges else []
        existing.append(charge)
        return self.model_copy(update={"charges": existing})

    def add_barcode(self, barcode: Barcode) -> ReceiptTemplateRequest:
        """Return a new request with an additional barcode."""
        existing = list(self.barcodes) if self.barcodes else []
        existing.append(barcode)
        return self.model_copy(update={"barcodes": existing})

    def add_qr_code(self, data: str, label: str) -> ReceiptTemplateRequest:
        """Return a new request with an additional QR code barcode."""
        return self.add_barcode(Barcode.qr_code(data, label))


class ReceiptTemplateResponse(CheqiBaseModel):
    """Response from receipt template generation."""

    ubl: Optional[str] = None
    cheqi: Optional[CheqiReceipt] = None
    vat_metadata: Optional[VatMetadata] = None
