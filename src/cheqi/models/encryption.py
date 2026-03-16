"""Encryption-related models."""

from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

from cheqi.models.base import CheqiBaseModel
from cheqi.models.enums import BarcodeType, ReceiptFormat, ReceiverType


class NotificationDisplayCode(CheqiBaseModel):
    """Optional code to render directly in the push notification."""

    type: BarcodeType
    data: str


class EncryptedReceiptRequestDto(CheqiBaseModel):
    """Encrypted receipt ready for delivery to a single recipient."""

    recipient_id: Optional[str] = None
    receipt_id: Optional[str] = None
    receiver_type: Optional[ReceiverType] = None
    encrypted_receipt: Optional[str] = None
    encrypted_symmetric_key: Optional[str] = None
    final_hash: Optional[str] = None
    public_key: Optional[str] = None
    supplier_party_id: Optional[UUID] = None
    receipt_formats: Optional[List[ReceiptFormat]] = None
    notification_display_code: Optional[NotificationDisplayCode] = None


class EncryptedReceiptsRequest(CheqiBaseModel):
    """Wrapper for sending multiple encrypted receipts."""

    match_id: Optional[str] = None
    encrypted_receipts: Optional[List[EncryptedReceiptRequestDto]] = None
    template_hash: Optional[str] = None


class EncryptedReceipt(CheqiBaseModel):
    """Encrypted receipt received from backend (for decryption)."""

    recipient_id: Optional[str] = None
    receipt_id: Optional[str] = None
    receiver_type: Optional[ReceiverType] = None
    encrypted_receipt: Optional[str] = None
    encrypted_symmetric_key: Optional[str] = None
    encrypted_customer_details: Optional[str] = None
    encrypted_customer_aes_key: Optional[str] = None
    final_hash: Optional[str] = None
    public_key: Optional[str] = None
    supplier_party_id: Optional[UUID] = None
    additional_properties: Optional[Dict[str, object]] = None
