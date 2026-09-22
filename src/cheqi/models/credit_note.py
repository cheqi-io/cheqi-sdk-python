"""Credit-note return-request models and submission results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Union

from pydantic import field_validator, model_validator
from typing_extensions import Self

from cheqi.models.generated.credit_note_initiation_request import (
    CreditNoteInitiationRequest as GeneratedCreditNoteInitiationRequest,
)
from cheqi.models.generated.encrypted_credit_note_initiation_request import (
    EncryptedCreditNoteInitiationRequest,
)
from cheqi.models.generated.encrypted_credit_note_initiation_request_response import (
    EncryptedCreditNoteInitiationRequestResponse,
)
from cheqi.models.generated.receipt_submission_response import ReceiptSubmissionResponse
from cheqi.models.generated.refund_bank_account import RefundBankAccount as GeneratedRefundBankAccount
from cheqi.models.generated.refund_preference import RefundPreference
from cheqi.models.generated.return_line_item import ReturnLineItem as GeneratedReturnLineItem
from cheqi.models.generated.return_reason_code import ReturnReasonCode
from cheqi.models.generated.webhook_credit_note_initiation_request import (
    WebhookCreditNoteInitiationRequest,
)


class _GeneratedModelMixin:
    def to_dict(self) -> dict[str, object]:
        return self.model_dump(by_alias=True, exclude_none=True, mode="json")  # type: ignore[attr-defined,no-any-return]

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True, exclude_none=True)  # type: ignore[attr-defined,no-any-return]


class ReturnLineItem(_GeneratedModelMixin, GeneratedReturnLineItem):
    """Requested quantity and reason for one original product identifier."""

    @field_validator("quantity", mode="before")
    @classmethod
    def coerce_quantity(cls, value: object) -> Union[int, float]:
        decimal = Decimal(str(value))
        return int(decimal) if decimal == decimal.to_integral_value() else float(decimal)

    @field_validator("product_id")
    @classmethod
    def product_id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("product_id is required")
        return value


class RefundBankAccount(_GeneratedModelMixin, GeneratedRefundBankAccount):
    """Customer bank details used only for a bank-transfer refund."""


class CreditNoteInitiationRequest(_GeneratedModelMixin, GeneratedCreditNoteInitiationRequest):
    """Validated plaintext customer return request.

    This object is encrypted for the original issuer. Cheqi only routes its
    ciphertext and cannot perform these plaintext validations server-side.
    """

    @field_validator("cheqi_receipt_id", "receipt_id")
    @classmethod
    def identifiers_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("receipt identifiers cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_refund_destination(self) -> Self:
        if not self.line_items:
            raise ValueError("at least one return line item is required")
        if any(not item.product_id.strip() for item in self.line_items):
            raise ValueError("line_items.product_id is required")
        if self.refund_preference is RefundPreference.BANK_TRANSFER:
            if self.refund_bank_account is None:
                raise ValueError("refund_bank_account is required for BANK_TRANSFER")
            if not self.refund_bank_account.iban.strip():
                raise ValueError("refund_bank_account.iban is required for BANK_TRANSFER")
            if not self.refund_bank_account.account_holder.strip():
                raise ValueError("refund_bank_account.account_holder is required for BANK_TRANSFER")
        elif self.refund_bank_account is not None:
            raise ValueError("refund_bank_account is only allowed for BANK_TRANSFER")
        return self


@dataclass(frozen=True)
class CreditNoteResult:
    """Result returned after an encrypted credit note is accepted."""

    cheqi_receipt_id: Optional[str]
    parent_cheqi_receipt_id: str
    match_id: Optional[str]
    status: Optional[str] = None
    created_at: Optional[datetime] = None

    @property
    def is_accepted(self) -> bool:
        return bool(self.cheqi_receipt_id and self.cheqi_receipt_id.strip())

    @property
    def is_success(self) -> bool:
        return self.is_accepted

    @classmethod
    def accepted(
        cls,
        parent_cheqi_receipt_id: str,
        response: ReceiptSubmissionResponse,
    ) -> CreditNoteResult:
        return cls(
            cheqi_receipt_id=response.cheqi_receipt_id,
            parent_cheqi_receipt_id=parent_cheqi_receipt_id,
            match_id=response.match_id,
            status=response.status,
            created_at=response.created_at,
        )


__all__ = [
    "CreditNoteInitiationRequest",
    "CreditNoteResult",
    "EncryptedCreditNoteInitiationRequest",
    "EncryptedCreditNoteInitiationRequestResponse",
    "RefundBankAccount",
    "RefundPreference",
    "ReturnLineItem",
    "ReturnReasonCode",
    "WebhookCreditNoteInitiationRequest",
]
