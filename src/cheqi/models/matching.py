"""Customer matching models."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from cheqi.models.base import CheqiBaseModel
from cheqi.models.enums import KeyAlgorithm, PaymentType, ReceiptFormat, ReceiverType, RecipientEntityType
from cheqi.models.payment import CardDetails, PaymentAccountDetails


class IdentificationDetails(CheqiBaseModel):
    """Customer identification details for matching.

    At least one identifier must be provided. The system tries them in priority order:
    pairing code -> card details -> payment account -> email -> cheqi receipt ID.
    """

    payment_type: Optional[PaymentType] = None
    card_details: Optional[CardDetails] = None
    payment_account_details: Optional[PaymentAccountDetails] = None
    payment_ids: Optional[List[str]] = None
    recipient_email: Optional[str] = None
    cheqi_receipt_id: Optional[str] = None
    pairing_code: Optional[str] = None


class Recipient(CheqiBaseModel):
    """Recipient with cryptographic key info for encryption."""

    id: Optional[str] = None
    receiver_type: Optional[ReceiverType] = None
    public_key: Optional[str] = None
    key_algorithm: Optional[KeyAlgorithm] = None
    accepted_formats: Optional[List[ReceiptFormat]] = None


class RecipientResolutionResponse(CheqiBaseModel):
    """Response from customer matching."""

    customer_found: bool = False
    match_id: Optional[str] = None
    recipients: Optional[List[Recipient]] = None
    expires_at: Optional[datetime] = None
    buyer_country_code: Optional[str] = None
    recipient_entity_type: Optional[RecipientEntityType] = None
