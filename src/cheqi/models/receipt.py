"""Idiomatic receipt models layered on the generated wire contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Union

from pydantic import Field, field_validator
from typing_extensions import Self

from cheqi.models.generated.barcode import Barcode as GeneratedBarcode
from cheqi.models.generated.barcode_type import BarcodeType
from cheqi.models.generated.charge import Charge as GeneratedCharge
from cheqi.models.generated.client_receipt_download_response import ClientReceiptDownloadResponse
from cheqi.models.generated.discount import Discount as GeneratedDiscount
from cheqi.models.generated.fiscalization_data import FiscalizationData as GeneratedFiscalizationData
from cheqi.models.generated.fiscalization_status import FiscalizationStatus
from cheqi.models.generated.jurisdiction_field import JurisdictionField as GeneratedJurisdictionField
from cheqi.models.generated.jurisdiction_legal_text import (
    JurisdictionLegalText as GeneratedJurisdictionLegalText,
)
from cheqi.models.generated.jurisdictional_data import JurisdictionalData as GeneratedJurisdictionalData
from cheqi.models.generated.payment_details import PaymentDetails
from cheqi.models.generated.period import Period as GeneratedPeriod
from cheqi.models.generated.product import Product as GeneratedProduct
from cheqi.models.generated.receipt_payload import ReceiptPayload as GeneratedReceiptPayload
from cheqi.models.generated.receipt_submission_response import ReceiptSubmissionResponse
from cheqi.models.generated.recipient_resolution_response import RecipientResolutionResponse
from cheqi.models.generated.tax import Tax as GeneratedTax
from cheqi.models.generated.unit_code import UnitCode

Number = Union[Decimal, str, int, float]


def _coerce_generated_number(value: object) -> Union[int, float]:
    """Accept Python monetary inputs while retaining generated wire field types."""
    if isinstance(value, bool):
        raise TypeError("boolean values are not valid numbers")
    if isinstance(value, (int, float)):
        return value
    decimal = Decimal(str(value))
    return int(decimal) if decimal == decimal.to_integral_value() else float(decimal)


class _GeneratedModelMixin:
    """Use consistent, compact SDK serialization for generated Pydantic models."""

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(by_alias=True, exclude_none=True, mode="json")  # type: ignore[attr-defined,no-any-return]

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True, exclude_none=True)  # type: ignore[attr-defined,no-any-return]


class Barcode(_GeneratedModelMixin, GeneratedBarcode):
    """Barcode with small named constructors."""

    @classmethod
    def qr_code(cls, data: str, label: Optional[str] = None) -> Barcode:
        return cls(type=BarcodeType.QR_CODE, data=data, label=label)

    @classmethod
    def of(cls, barcode_type: BarcodeType, data: str, label: Optional[str] = None) -> Barcode:
        return cls(type=barcode_type, data=data, label=label)


class Discount(_GeneratedModelMixin, GeneratedDiscount):
    """Receipt discount accepting Python ``Decimal`` and decimal strings."""

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, value: object) -> Union[int, float]:
        return _coerce_generated_number(value)

    @classmethod
    def of(
        cls,
        amount: Number,
        label: Optional[str] = None,
        percentage: Optional[float] = None,
    ) -> Discount:
        return cls(amount=amount, label=label, percentage=percentage)


class Charge(_GeneratedModelMixin, GeneratedCharge):
    """Receipt charge accepting Python ``Decimal`` and decimal strings."""

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, value: object) -> Union[int, float]:
        return _coerce_generated_number(value)

    @classmethod
    def of(
        cls,
        amount: Number,
        label: Optional[str] = None,
        percentage: Optional[float] = None,
    ) -> Charge:
        return cls(amount=amount, label=label, percentage=percentage)


class Tax(_GeneratedModelMixin, GeneratedTax):
    """Tax applied to a product line or an entire receipt."""

    @field_validator("amount", "taxable_amount", mode="before")
    @classmethod
    def coerce_amounts(cls, value: object) -> Optional[Union[int, float]]:
        if value is None:
            return None
        return _coerce_generated_number(value)


class Period(_GeneratedModelMixin, GeneratedPeriod):
    """Billing or service period from the generated receipt contract."""


class JurisdictionField(_GeneratedModelMixin, GeneratedJurisdictionField):
    """Country-specific extension field."""

    @classmethod
    def of(cls, code: str, value: str, label: Optional[str] = None) -> JurisdictionField:
        return cls(code=code, value=value, label=label)


class JurisdictionLegalText(_GeneratedModelMixin, GeneratedJurisdictionLegalText):
    """Exact issuer-supplied legal receipt text."""

    @classmethod
    def of(
        cls,
        code: str,
        text: str,
        language_code: Optional[str] = None,
    ) -> JurisdictionLegalText:
        return cls(code=code, text=text, language_code=language_code)


class FiscalizationData(_GeneratedModelMixin, GeneratedFiscalizationData):
    """Issuer-supplied fiscalization data with an extension-field helper."""

    def add_field(self, code: str, value: str, label: Optional[str] = None) -> Self:
        fields = list(self.additional_fields or [])
        fields.append(JurisdictionField.of(code, value, label))
        self.additional_fields = fields
        return self


class JurisdictionalData(_GeneratedModelMixin, GeneratedJurisdictionalData):
    """Issuer-supplied country-specific receipt data."""

    def add_legal_text(
        self,
        code: str,
        text: str,
        language_code: Optional[str] = None,
    ) -> Self:
        values = list(self.legal_texts or [])
        values.append(JurisdictionLegalText.of(code, text, language_code))
        self.legal_texts = values
        return self

    def add_field(self, code: str, value: str, label: Optional[str] = None) -> Self:
        values = list(self.additional_fields or [])
        values.append(JurisdictionField.of(code, value, label))
        self.additional_fields = values
        return self


class Product(_GeneratedModelMixin, GeneratedProduct):
    """A definitive product line with convenient add methods.

    Construct the line directly with keyword arguments, then optionally add taxes,
    discounts, charges, or barcodes. The SDK never calculates monetary values.
    """

    taxes: List[GeneratedTax] = Field(default_factory=list)

    @field_validator("unit_price", "subtotal", "total", mode="before")
    @classmethod
    def coerce_amounts(cls, value: object) -> Union[int, float]:
        return _coerce_generated_number(value)

    def add_tax(
        self,
        tax_or_rate: Union[GeneratedTax, float, int],
        tax_type: Optional[str] = None,
        taxable_amount: Optional[Number] = None,
        amount: Optional[Number] = None,
        *,
        label: Optional[str] = None,
    ) -> Self:
        """Add either a ``Tax`` object or a compact tax definition."""
        if isinstance(tax_or_rate, GeneratedTax):
            tax = tax_or_rate
        else:
            if tax_type is None or taxable_amount is None:
                raise ValueError("tax_type and taxable_amount are required when adding a tax by rate")
            tax = Tax(
                rate=tax_or_rate,
                type=tax_type,
                taxable_amount=taxable_amount,
                amount=amount,
                label=label,
            )
        self.taxes = [*self.taxes, tax]
        return self

    def add_discount(
        self,
        discount_or_amount: Union[GeneratedDiscount, Number],
        label: Optional[str] = None,
        *,
        percentage: Optional[float] = None,
    ) -> Self:
        discount = (
            discount_or_amount
            if isinstance(discount_or_amount, GeneratedDiscount)
            else Discount.of(discount_or_amount, label, percentage)
        )
        self.discounts = [*(self.discounts or []), discount]
        return self

    def add_charge(
        self,
        charge_or_amount: Union[GeneratedCharge, Number],
        label: Optional[str] = None,
        *,
        percentage: Optional[float] = None,
    ) -> Self:
        charge = (
            charge_or_amount
            if isinstance(charge_or_amount, GeneratedCharge)
            else Charge.of(charge_or_amount, label, percentage)
        )
        self.charges = [*(self.charges or []), charge]
        return self

    def add_barcode(self, barcode: GeneratedBarcode) -> Self:
        self.barcodes = [*(self.barcodes or []), barcode]
        return self

    def add_qr_code(self, data: str, label: Optional[str] = None) -> Self:
        return self.add_barcode(Barcode.qr_code(data, label))


class ReceiptPayload(_GeneratedModelMixin, GeneratedReceiptPayload):
    """Definitive issuer-supplied receipt values.

    Values are serialized and encrypted exactly as supplied; the SDK performs no
    calculations, enrichment, fiscalization, signature, sequence, or QR generation.
    """

    @field_validator(
        "receipt_subtotal",
        "total_before_tax",
        "total_tax_amount",
        "total_amount",
        mode="before",
    )
    @classmethod
    def coerce_amounts(cls, value: object) -> Union[int, float]:
        return _coerce_generated_number(value)

    def add_product(self, product: GeneratedProduct) -> Self:
        self.products = [*self.products, product]
        return self

    def add_tax(self, tax: GeneratedTax) -> Self:
        self.taxes = [*(self.taxes or []), tax]
        return self

    def add_discount(self, discount: GeneratedDiscount) -> Self:
        self.discounts = [*(self.discounts or []), discount]
        return self

    def add_charge(self, charge: GeneratedCharge) -> Self:
        self.charges = [*(self.charges or []), charge]
        return self

    def add_barcode(self, barcode: GeneratedBarcode) -> Self:
        self.barcodes = [*(self.barcodes or []), barcode]
        return self

    def add_qr_code(self, data: str, label: Optional[str] = None) -> Self:
        return self.add_barcode(Barcode.qr_code(data, label))


class DeliveryRouteType(str, Enum):
    DIGITAL = "DIGITAL"
    EMAIL_FALLBACK = "EMAIL_FALLBACK"
    DOWNLOAD_FALLBACK = "DOWNLOAD_FALLBACK"


@dataclass(frozen=True)
class ReceiptResult:
    """Outcome of receipt routing and submission."""

    cheqi_receipt_id: Optional[str]
    match_id: Optional[str]
    delivery_route_type: DeliveryRouteType
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    download_url: Optional[str] = None
    download_envelope_required: bool = False
    email_receipt_required: bool = False

    @property
    def is_accepted(self) -> bool:
        return bool(self.cheqi_receipt_id and self.cheqi_receipt_id.strip())

    @property
    def is_success(self) -> bool:
        return self.is_accepted

    @classmethod
    def accepted(
        cls,
        response: ReceiptSubmissionResponse,
        route: DeliveryRouteType = DeliveryRouteType.DIGITAL,
    ) -> ReceiptResult:
        return cls(
            cheqi_receipt_id=response.cheqi_receipt_id,
            match_id=response.match_id,
            delivery_route_type=route,
            status=response.status,
            created_at=response.created_at,
        )

    @classmethod
    def download_required(cls, resolution: RecipientResolutionResponse) -> ReceiptResult:
        return cls(
            cheqi_receipt_id=None,
            match_id=resolution.match_id,
            delivery_route_type=DeliveryRouteType.DOWNLOAD_FALLBACK,
            expires_at=resolution.expires_at,
            download_envelope_required=True,
        )

    @classmethod
    def email_required(cls, resolution: RecipientResolutionResponse) -> ReceiptResult:
        return cls(
            cheqi_receipt_id=None,
            match_id=resolution.match_id,
            delivery_route_type=DeliveryRouteType.EMAIL_FALLBACK,
            expires_at=resolution.expires_at,
            email_receipt_required=True,
        )

    @classmethod
    def download_accepted(
        cls,
        match_id: Optional[str],
        response: ClientReceiptDownloadResponse,
        download_url: str,
    ) -> ReceiptResult:
        return cls(
            cheqi_receipt_id=response.cheqi_receipt_id,
            match_id=match_id,
            delivery_route_type=DeliveryRouteType.DOWNLOAD_FALLBACK,
            created_at=response.created_at,
            expires_at=response.expires_at,
            download_url=download_url,
        )


__all__ = [
    "Barcode",
    "BarcodeType",
    "Charge",
    "DeliveryRouteType",
    "Discount",
    "FiscalizationData",
    "FiscalizationStatus",
    "JurisdictionField",
    "JurisdictionLegalText",
    "JurisdictionalData",
    "PaymentDetails",
    "Period",
    "Product",
    "ReceiptPayload",
    "ReceiptResult",
    "Tax",
    "UnitCode",
]
