"""Payment-related models."""

from __future__ import annotations

from typing import List, Optional

from cheqi.models.base import CheqiBaseModel, CheqiDecimal
from cheqi.models.enums import AccountIdentifierType, CardProvider, PaymentType


class CardDetails(CheqiBaseModel):
    """Card identification details (PAR, PAN, last four digits)."""

    card_provider: Optional[CardProvider] = None
    payment_account_number: Optional[str] = None
    payment_account_reference: Optional[str] = None


class PaymentAccountDetails(CheqiBaseModel):
    """Payment account identification (IBAN, WERO)."""

    identifier: Optional[str] = None
    account_identifier_type: Optional[AccountIdentifierType] = None
    bic: Optional[str] = None
    bank_name: Optional[str] = None
    account_holder_name: Optional[str] = None


class Payment(CheqiBaseModel):
    """Payment details for a receipt."""

    payment_type: Optional[PaymentType] = None
    payment_account_reference: Optional[str] = None
    card_issuer: Optional[str] = None
    card_brand: Optional[str] = None
    last_four_digits: Optional[str] = None
    amount_tendered: Optional[CheqiDecimal] = None
    change_given: Optional[CheqiDecimal] = None
    transaction_reference: Optional[str] = None
    processor: Optional[str] = None
    terminal_id: Optional[str] = None
    payment_ids: Optional[List[str]] = None
