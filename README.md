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
    Product,
    Tax,
    UnitCode,
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
