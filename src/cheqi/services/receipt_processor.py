"""Merge decrypted recipient context into Cheqi JSON and UBL receipt formats."""

from __future__ import annotations

from dataclasses import replace

from cheqi.services.decryption import DecryptedReceipt

_PARTY_PLACEHOLDER = "<cac:AccountingCustomerParty/>"
_PARTY_CLOSING_TAG = "</cac:AccountingCustomerParty>"


class ReceiptProcessor:
    """Apply Java-compatible receiving-party and payment-means merges."""

    def merge(self, decrypted: DecryptedReceipt) -> DecryptedReceipt:
        context = decrypted.receipt_context_envelope
        envelope = decrypted.receipt_envelope
        if context is None or envelope is None:
            return decrypted

        receiving_context = context.receiving_party
        payment_context = context.payment_means
        xml_party = receiving_context.xml_receiving_party if receiving_context else None
        xml_payment = payment_context.xml_payment_means if payment_context else None

        ubl_purchase_receipt = self._merge_xml(envelope.ubl_purchase_receipt, xml_party, xml_payment)
        ubl_invoice = self._merge_xml(envelope.ubl_invoice, xml_party, xml_payment)

        cheqi = envelope.cheqi
        if cheqi is not None and receiving_context and receiving_context.receiving_party is not None:
            cheqi = cheqi.model_copy(update={"receiving_party": receiving_context.receiving_party})

        merged_envelope = envelope.model_copy(
            update={
                "cheqi": cheqi,
                "ubl_purchase_receipt": ubl_purchase_receipt,
                "ubl_invoice": ubl_invoice,
            }
        )
        return replace(decrypted, receipt_envelope=merged_envelope)

    @staticmethod
    def _merge_xml(xml: str | None, xml_party: str | None, xml_payment: str | None) -> str | None:
        if xml is None:
            return None
        merged = xml
        if xml_party and _PARTY_PLACEHOLDER in merged:
            merged = merged.replace(_PARTY_PLACEHOLDER, xml_party)
        if xml_payment:
            if _PARTY_CLOSING_TAG in merged:
                merged = merged.replace(_PARTY_CLOSING_TAG, _PARTY_CLOSING_TAG + xml_payment)
            elif _PARTY_PLACEHOLDER in merged:
                merged = merged.replace(_PARTY_PLACEHOLDER, _PARTY_PLACEHOLDER + xml_payment)
        return merged
