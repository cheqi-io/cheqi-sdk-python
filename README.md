# Cheqi Python SDK

Python SDK for resolving receipt recipients and issuing end-to-end encrypted Cheqi receipts and
credit notes. It also provides client-encrypted receipt downloads, receipt-envelope decryption,
integrity helpers, and store management.

The SDK preserves Cheqi's zero-knowledge boundary: the issuer supplies definitive receipt values,
which are encrypted locally for each owner device. The SDK does not calculate totals, enrich
payment data, fiscalize receipts, or submit plaintext receipt bodies to Cheqi on the digital route.

## Install

```bash
pip install cheqi-sdk
```

Python 3.9 or newer is required.

Version `1.1.1` matches the Java SDK 2.3 contract, including company-expense receipt attribution,
member receipt identities, employee invitation roles, and the latest encrypted delivery metadata.

## Initialize

```python
from cheqi import CheqiSDK, Environment

sdk = CheqiSDK(
    environment=Environment.SANDBOX,
    api_key="your_api_key",
)
```

For OAuth, omit `api_key` and pass `access_token=` to service calls. A custom backend can be used
with `custom_api_endpoint=` and, when needed, `receipt_download_base_url=`.

An existing synchronous `httpx.Client` can be injected with `http_client=`. The SDK leaves an
injected client open; clients created by the SDK are closed by `sdk.close()` or the context manager.

## Issue a receipt

The generated classes are the canonical API contract. Handwritten receipt classes subclass that
contract only to add Python-friendly `Decimal` handling and small convenience methods.

```python
from datetime import datetime, timezone

from cheqi.models import (
    CardDetails,
    IdentificationDetails,
    PaymentDetails,
    PaymentType,
    Product,
    ReceiptPayload,
    Tax,
    UnitCode,
)

identification = IdentificationDetails(
    payment_type=PaymentType.CARD_PAYMENT,
    card_details=CardDetails(
        payment_account_reference="PAR123456789",
        card_provider="VISA",
        last_four_digits="4242",
    ),
)

product = Product(
    name="Coffee beans",
    brand_name="Cheqi Coffee",
    identifier="SKU-COFFEE-001",
    quantity=1,
    base_quantity=1,
    unit_code=UnitCode.C62,
    unit_price="10.00",
    subtotal="10.00",
    total="12.10",
).add_tax(21, "VAT", "10.00", "2.10")

payload = ReceiptPayload(
    document_number="POS-2026-0001",
    issue_date=datetime.now(timezone.utc),
    currency="EUR",
    receipt_subtotal="10.00",
    total_before_tax="10.00",
    total_tax_amount="2.10",
    total_amount="12.10",
    taxes_applied=True,
    products=[product],
    taxes=[Tax(rate=21, type="VAT", taxable_amount="10.00", amount="2.10")],
    payment_details=PaymentDetails(
        payment_means_code="48",
        description="Card payment",
        card_provider="VISA",
        card_last_four="4242",
        merchant_id="MID-123",
        payment_terminal_id="TID-456",
    ),
)

result = sdk.receipt_service.issue_receipt(identification, payload)

if result.is_accepted:
    print(result.cheqi_receipt_id)
elif result.email_receipt_required:
    # Generate and submit the permitted email-fallback receipt explicitly.
    pass
elif result.download_envelope_required:
    # Generate the final ReceiptEnvelope locally and complete the fallback.
    pass
```

To associate a receipt with a store or use OAuth:

```python
result = sdk.receipt_service.issue_receipt(
    identification,
    payload,
    store_id=store_id,
    access_token=access_token,
)
```

All monetary, tax, payment, barcode, and jurisdictional values remain caller-supplied. For example,
`Product.add_tax(...)` only appends the supplied tax; it does not calculate it.

## Delivery routes and downloads

The backend selects `DIGITAL`, `DOWNLOAD_FALLBACK`, or `EMAIL_FALLBACK`.

- Digital receipts are independently encrypted for every matched device and submitted immediately.
- Download fallback is completed automatically when `IdentificationDetails.payment_type` is set.
- Without local payment context, `download_envelope_required` asks the caller for a final generated
  `ReceiptEnvelope`.
- Email fallback is returned as an explicit action and is not performed automatically.

An explicit customer-without-Cheqi flow can skip matching:

```python
result = sdk.receipt_service.issue_download_receipt(
    IdentificationDetails(payment_type=PaymentType.CASH),
    payload,
    access_token=access_token,
)
print(result.download_url)
```

The AES key is stored only in the URL fragment and is never sent to Cheqi.

## Credit notes and return requests

Definitive merchant-issued credit notes use the same device encryption model and a separate API
envelope:

```python
result = sdk.credit_note_service.issue_credit_note(
    identification,
    parent_cheqi_receipt_id,
    credit_note_payload,
    access_token=access_token,
)
```

Customer return requests are represented by `CreditNoteInitiationRequest`, `ReturnLineItem`,
`ReturnReasonCode`, and `RefundPreference`. Pydantic validates positive return quantities and the
bank-account rules for `BANK_TRANSFER`. Receiving issuers can decrypt and validate queued or
webhook requests in one call:

```python
request = sdk.decryption_service.decrypt_credit_note_initiation_request(
    encrypted_request,
    private_key_base64,
)
```

## Receipt decryption

```python
envelope = sdk.decryption_service.decrypt_receipt(
    encrypted_receipt_delivery_or_webhook_envelope,
    private_key_base64,
)
```

The plaintext is the generated `ReceiptEnvelope`; no backend-context merge step is required.
For company-expense deliveries, its optional `expense_submission` field contains the encrypted
`ExpenseSubmissionEnvelope` attribution metadata.

## Lower-level operations

The matching, encryption, submission, download, verification, and store services are exposed on
`CheqiSDK`. Examples include:

```python
resolution = sdk.matching_service.match_customer(identification, access_token)
delivery = sdk.encryption_service.encrypt_for_device(payload.to_json(), resolution.recipients[0])
receipt_hash = sdk.verification_service.calculate_cheqi_receipt_hash(payload.to_json())
canonical_json = sdk.verification_service.canonicalize_cheqi_receipt(payload)
ubl_hash = sdk.verification_service.calculate_ubl_hash(ubl_xml)
stores = sdk.store_service.get_stores(company_id, access_token=access_token)
```

## Development

```bash
python -m pip install -e '.[dev]'
pytest
ruff check src tests
mypy src/cheqi
```
