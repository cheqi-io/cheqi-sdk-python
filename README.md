# Cheqi Python SDK

Python SDK for issuing end-to-end encrypted Cheqi receipts, encrypted credit notes,
email delivery, client-encrypted download fallback, receipt decryption/merge, and store management.

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
    DeliveryStatus,
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
    print(f"Receipt route: {result.delivery_status}")
    print(f"Receipt ID: {result.cheqi_receipt_id}")
```

The high-level flow now follows the same route contract as the Java SDK:

- `DIGITAL` encrypts a recipient-specific envelope with AES-256-GCM and wraps its key with RSA-OAEP SHA-256.
- `DOWNLOAD_FALLBACK` creates a QR URL locally, encrypts the complete envelope with the fragment key, and uploads only ciphertext to `/receipt/download`.
- If no route is found and `recipient_email` is available, the CHEQI receipt is sent through `/receipt/email`.
- A found route without `deliveryRouteType` is rejected to avoid accidentally using the retired server-held fallback-key flow.

## VAT Context and Formats

Recipient resolution supplies `buyer_country_code` and `buyer_type`; the high-level flow adds them to template generation unless the receipt request overrides them. If `taxes_applied` is omitted, the SDK infers it from a positive total tax amount or a non-empty receipt tax list.

The supported recipient formats are `CHEQI`, `UBL_PURCHASE_RECEIPT`, `UBL_INVOICE`, and `UBL_CREDIT_NOTE`. Each digital recipient receives only the formats it declared.

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

## Client-Encrypted Download Fallback

Standard environments automatically map to the customer-facing origins `https://receipt.cheqi.io` and `https://sandbox.receipt.cheqi.io`. For a custom API endpoint, configure the receipt origin explicitly:

```python
sdk = CheqiSDK(
    custom_api_endpoint="http://localhost:8080",
    receipt_download_base_url="http://localhost:3000/receipt",
    api_key="sk_test_...",
)
```

`process_complete_receipt` handles a `DOWNLOAD_FALLBACK` response automatically. The AES-256 key exists only in the URL fragment, so it is never sent to Cheqi:

```python
result = sdk.receipt_service.process_complete_receipt(identification, receipt_request)

if result.delivery_status == DeliveryStatus.DELIVERED_DOWNLOAD:
    render_qr(result.download_url)
```

You can also create the URL before any network call and own persistence/scheduling yourself:

```python
from cheqi.models import ClientReceiptDownloadRequest, ReceiptFormat

link = sdk.download_service.generate_download_link(Environment.PRODUCTION)
persist_link_credentials(link.download_id, link.content_key)
render_qr(link.url)

# Later, after obtaining the normal server-generated template:
template = sdk.receipt_service.generate_receipt_template(
    receipt_request,
    [ReceiptFormat.CHEQI],
)
envelope = sdk.download_service.build_download_envelope(template)
ciphertext = sdk.download_service.encrypt_download_envelope(envelope, link.content_key)

# Persist these exact bytes before uploading. A retry must reuse the ciphertext;
# encrypting again generates a new GCM IV.
persist_ciphertext(link.download_id, ciphertext)
response = sdk.receipt_service.upload_client_encrypted_receipt(
    ClientReceiptDownloadRequest(
        download_id=link.download_id,
        ciphertext=ciphertext,
    )
)
```

Transient matching/template failures return `PENDING_DOWNLOAD_TEMPLATE` with a usable URL. A transient upload failure returns `PENDING_DOWNLOAD_UPLOAD` with `download_ciphertext`, `template_hash`, and the same URL so the integration can safely resume. The SDK deliberately does not create background workers or store pending jobs.

## Receipt Decryption and Context Merge

Queued encrypted receipts can contain a separately encrypted customer-context envelope. The SDK decrypts both payloads and merges receiving-party and payment-means data into CHEQI JSON, UBL PurchaseReceipt, and UBL Invoice representations:

```python
decrypted = sdk.process_encrypted_receipt(encrypted_receipt, private_key)
complete_envelope = decrypted.receipt_envelope
```

Raw decrypted strings remain available as `decrypted.receipt_content` and `decrypted.customer_details` for backward compatibility.

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
