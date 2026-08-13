from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from cheqi.models import (
    CreditNoteInitiationRequest,
    FiscalizationData,
    FiscalizationStatus,
    JurisdictionalData,
    Product,
    ReceiptPayload,
    RefundBankAccount,
    RefundPreference,
    ReturnLineItem,
    ReturnReasonCode,
    UnitCode,
)


def test_product_supports_compact_tax_addition() -> None:
    product = Product(
        name="Coffee beans",
        identifier="SKU-1",
        quantity=1,
        unit_code=UnitCode.C62,
        unit_price="10.00",
        subtotal="10.00",
        total="12.10",
    ).add_tax(21, "VAT", "10.00", "2.10", label="VAT 21%")

    data = json.loads(product.to_json())

    assert data["unitPrice"] == 10
    assert data["taxes"] == [
        {
            "rate": 21,
            "type": "VAT",
            "amount": 2.1,
            "taxableAmount": 10,
            "label": "VAT 21%",
        }
    ]


def test_receipt_payload_serializes_definitive_values_without_template_wrapper() -> None:
    jurisdiction = JurisdictionalData(country_code="AT").add_field("receiptType", "STANDARD", "Receipt type")
    jurisdiction.fiscalization = FiscalizationData(
        system="RKSV",
        status=FiscalizationStatus.FISCALIZED,
    ).add_field("signatureValue", "issuer-signature", "Signature")
    product = Product(
        name="Supplied line",
        identifier="LINE-1",
        quantity=2,
        unit_code=UnitCode.C62,
        unit_price="1.11",
        subtotal="2.22",
        total="3.33",
    )
    payload = ReceiptPayload(
        document_number="AT-100",
        issue_date=datetime(2026, 7, 29, 10, tzinfo=timezone.utc),
        currency="EUR",
        receipt_subtotal="7.01",
        total_before_tax="8.02",
        total_tax_amount="3.03",
        total_amount="9.04",
        taxes_applied=True,
        products=[product],
        jurisdictional_data=jurisdiction,
    ).add_qr_code("https://verify.example/AT-100", "Verify")

    data = json.loads(payload.to_json())

    assert data["receiptSubtotal"] == 7.01
    assert data["products"][0]["total"] == 3.33
    assert data["jurisdictionalData"]["fiscalization"]["additionalFields"][0]["value"] == "issuer-signature"
    assert data["barcodes"][0]["data"] == "https://verify.example/AT-100"
    assert "receiptTemplateRequest" not in data


def test_credit_note_initiation_request_validates_refund_rules() -> None:
    line = ReturnLineItem(
        product_id="SKU-1",
        quantity="0.5",
        reason_code=ReturnReasonCode.DEFECTIVE,
    )
    request = CreditNoteInitiationRequest(
        cheqi_receipt_id="cheqi-1",
        receipt_id="merchant-1",
        line_items=[line],
        refund_preference=RefundPreference.BANK_TRANSFER,
        refund_bank_account=RefundBankAccount(
            iban="NL91ABNA0417164300",
            account_holder="Customer",
        ),
    )

    assert json.loads(request.to_json())["lineItems"][0]["quantity"] == 0.5

    with pytest.raises(ValidationError, match="refund_bank_account is required"):
        CreditNoteInitiationRequest(
            cheqi_receipt_id="cheqi-1",
            receipt_id="merchant-1",
            line_items=[line],
            refund_preference=RefundPreference.BANK_TRANSFER,
        )


def test_return_line_requires_positive_quantity_and_product_id() -> None:
    with pytest.raises(ValidationError):
        ReturnLineItem(product_id="", quantity=1, reason_code=ReturnReasonCode.UNWANTED)
    with pytest.raises(ValidationError):
        ReturnLineItem(product_id="SKU", quantity=0, reason_code=ReturnReasonCode.UNWANTED)
