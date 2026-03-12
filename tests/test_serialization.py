"""Tests for model serialization (camelCase, decimal handling, etc.)."""

from __future__ import annotations

import json
from decimal import Decimal

from cheqi.models.enums import BarcodeType, PaymentType, UnitCode
from cheqi.models.matching import IdentificationDetails
from cheqi.models.payment import CardDetails
from cheqi.models.receipt import (
    Barcode,
    CheqiReceipt,
    Discount,
    Product,
    ReceiptTemplateRequest,
    Tax,
)


class TestCamelCaseSerialization:
    """Verify that Python snake_case fields serialize to camelCase JSON."""

    def test_product_serialization(self) -> None:
        product = Product(
            name="Laptop",
            identifier="LAP-001",
            quantity=1.0,
            base_quantity=1.0,
            unit_code=UnitCode.ONE,
            unit_price=Decimal("1000.00"),
            subtotal=Decimal("1000.00"),
            total=Decimal("1210.00"),
        )

        data = product.to_dict()
        assert "name" in data
        assert "unitCode" in data
        assert "unitPrice" in data
        assert "baseQuantity" in data
        assert data["unitCode"] == "C62"

    def test_receipt_template_serialization(self) -> None:
        request = ReceiptTemplateRequest(
            document_number="INV-001",
            currency="EUR",
            receipt_subtotal=Decimal("100"),
            total_before_tax=Decimal("100"),
            total_tax_amount=Decimal("21"),
            total_amount=Decimal("121"),
        )

        data = request.to_dict()
        assert "documentNumber" in data
        assert "receiptSubtotal" in data
        assert "totalBeforeTax" in data
        assert "totalTaxAmount" in data
        assert "totalAmount" in data

    def test_identification_details_serialization(self) -> None:
        details = IdentificationDetails(
            payment_type=PaymentType.CARD_PAYMENT,
            card_details=CardDetails(
                payment_account_reference="PAR123",
            ),
            recipient_email="test@example.com",
        )

        data = details.to_dict()
        assert "paymentType" in data
        assert data["paymentType"] == "CARD_PAYMENT"
        assert "cardDetails" in data
        assert "recipientEmail" in data


class TestDecimalSerialization:
    """Verify that CheqiDecimal strips trailing zeros in JSON."""

    def test_trailing_zeros_stripped(self) -> None:
        product = Product(
            unit_price=Decimal("100.00"),
            subtotal=Decimal("21.50"),
            total=Decimal("121.00"),
        )

        json_str = product.to_json()
        data = json.loads(json_str)

        # 100.00 → "100" (integer-like)
        assert data["unitPrice"] == "100"
        # 21.50 → "21.5"
        assert data["subtotal"] == "21.5"
        # 121.00 → "121"
        assert data["total"] == "121"

    def test_decimal_precision_preserved(self) -> None:
        tax = Tax(
            rate=21.0,
            type="VAT",
            taxable_amount=Decimal("99.99"),
            amount=Decimal("20.9979"),
        )

        json_str = tax.to_json()
        data = json.loads(json_str)
        assert data["taxableAmount"] == "99.99"
        assert data["amount"] == "20.9979"


class TestNoneExclusion:
    """Verify that None values are excluded from serialization."""

    def test_none_fields_excluded(self) -> None:
        product = Product(name="Test")

        data = product.to_dict()
        assert "name" in data
        assert "identifier" not in data
        assert "description" not in data
        assert "quantity" not in data

    def test_empty_lists_excluded(self) -> None:
        request = ReceiptTemplateRequest(document_number="INV-001")

        data = request.to_dict()
        assert "documentNumber" in data
        # None lists should not appear
        assert "products" not in data
        assert "taxes" not in data


class TestImmutability:
    """Verify that models are frozen (immutable)."""

    def test_product_is_frozen(self) -> None:
        product = Product(name="Laptop")
        try:
            product.name = "Desktop"  # type: ignore[misc]
            assert False, "Should have raised"
        except Exception:
            pass

    def test_add_methods_return_new_instance(self) -> None:
        request = ReceiptTemplateRequest(document_number="INV-001")
        tax = Tax(rate=21.0, type="VAT", taxable_amount=Decimal("100"))

        new_request = request.add_tax(tax)

        # Original unchanged
        assert request.taxes is None
        # New instance has the tax
        assert new_request.taxes is not None
        assert len(new_request.taxes) == 1
        assert new_request.document_number == "INV-001"


class TestConvenienceMethods:
    """Test chainable convenience methods."""

    def test_chained_additions(self) -> None:
        product1 = Product(name="Laptop", unit_price=Decimal("1000"))
        product2 = Product(name="Mouse", unit_price=Decimal("25"))
        tax = Tax(rate=21.0, type="VAT", taxable_amount=Decimal("1025"))
        discount = Discount(amount=Decimal("50"), label="10% off")

        request = (
            ReceiptTemplateRequest(document_number="INV-001", currency="EUR")
            .add_product(product1)
            .add_product(product2)
            .add_tax(tax)
            .add_discount(discount)
        )

        assert request.products is not None
        assert len(request.products) == 2
        assert request.taxes is not None
        assert len(request.taxes) == 1
        assert request.discounts is not None
        assert len(request.discounts) == 1

    def test_barcode_factory_methods(self) -> None:
        qr = Barcode.qr_code("https://cheqi.io", "Website")
        assert qr.type == BarcodeType.QR_CODE
        assert qr.data == "https://cheqi.io"

        ean = Barcode.of(BarcodeType.EAN_13, "5901234123457", "Product EAN")
        assert ean.type == BarcodeType.EAN_13
