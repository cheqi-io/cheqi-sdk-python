# Cheqi Python SDK

Python SDK for end-to-end encrypted receipt and credit note processing via the Cheqi API.

## Installation

```bash
pip install cheqi-sdk
```

Or with uv:

```bash
uv add cheqi-sdk
```

## Quick Start

```python
from cheqi import CheqiSDK, Environment
from cheqi.models import (
    IdentificationDetails,
    CardDetails,
    ReceiptTemplateRequest,
    NotificationDisplayCode,
    Product,
    Tax,
    UnitCode,
    BarcodeType,
    PaymentType,
    CardProvider,
)
from decimal import Decimal

# Initialize the SDK
sdk = CheqiSDK(
    environment=Environment.PRODUCTION,
    api_key="sk_live_...",
)

# Build identification details
identification = IdentificationDetails(
    payment_type=PaymentType.CARD_PAYMENT,
    card_details=CardDetails(
        payment_account_reference="PAR123456",
        card_provider=CardProvider.VISA,
    ),
)

# Build a receipt request
product = Product(
    name="Laptop",
    identifier="LAP-001",
    quantity=1.0,
    base_quantity=1.0,
    unit_code=UnitCode.ONE,
    unit_price=Decimal("1000.00"),
    subtotal=Decimal("1000.00"),
    total=Decimal("1210.00"),
    taxes=[Tax(rate=21.0, type="VAT", taxable_amount=Decimal("1000.00"), amount=Decimal("210.00"))],
)

receipt_request = ReceiptTemplateRequest(
    document_number="INV-2024-001",
    currency="EUR",
    receipt_subtotal=Decimal("1000.00"),
    total_before_tax=Decimal("1000.00"),
    total_tax_amount=Decimal("210.00"),
    total_amount=Decimal("1210.00"),
    products=[product],
    taxes=[Tax(rate=21.0, type="VAT", taxable_amount=Decimal("1000.00"), amount=Decimal("210.00"))],
)

# Process the complete receipt (match -> template -> encrypt -> send)
result = sdk.receipt_service.process_complete_receipt(
    identification_details=identification,
    receipt_request=receipt_request,
)

if result.success:
    print(f"Receipt delivered! ID: {result.cheqi_receipt_id}")
```

## Notification Display Code

If the merchant has notification-code rendering enabled, you can attach a QR code or barcode to the high-level receipt flow. The code is sent as request metadata and rendered by supported mobile clients directly from the push notification.

```python
notification_display_code = NotificationDisplayCode(
    type=BarcodeType.QR_CODE,
    data="https://example.com/receipt/INV-2024-001",
)

result = sdk.receipt_service.process_complete_receipt(
    identification_details=identification,
    receipt_request=receipt_request,
    notification_display_code=notification_display_code,
)
```

If the merchant is not enabled for this feature, or you omit `notification_display_code`, the normal receipt push is sent.

## Chainable Model Building

Models are immutable. Convenience methods return new instances:

```python
request = (
    ReceiptTemplateRequest(document_number="INV-001", currency="EUR")
    .add_product(product1)
    .add_product(product2)
    .add_tax(tax1)
    .add_discount(discount1)
)
```

## Authentication

```python
sdk = CheqiSDK(
    environment=Environment.PRODUCTION,
    api_key="sk_live_...",
)
```

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```
