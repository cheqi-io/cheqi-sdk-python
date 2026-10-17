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

Version `1.3.0` adds version 2 QR download envelopes carrying the unmodified
receipt payload and separate identification details. It retains match-recovery
tools, company-expense receipt attribution, member receipt identities, employee
invitation roles, and the latest encrypted delivery metadata.

## Initialize

```python
from cheqi import CheqiSDK, Environment

sdk = CheqiSDK(
    environment=Environment.SANDBOX,
    api_key="your_api_key",
)
```

A custom backend can be used with `custom_api_endpoint=` and, when needed,
`receipt_download_base_url=`.

## Request options and OAuth

Every API method takes a keyword-only `options: RequestOptions`. Use it to act on behalf of a
connected company with its OAuth access token, or to override the timeout or retry count for one
call. Without an access token, the call uses the configured `api_key`.

```python
from cheqi import RequestOptions

options = RequestOptions.with_access_token(access_token)
stores = sdk.store_service.get_stores(company_id, options=options)

slow_call = RequestOptions(access_token=access_token, timeout_seconds=60, max_retries=0)
```

Company access tokens are short-lived and bound to one Grant, so an integration that serves
several companies holds one token per Grant. Request one with the client-credentials grant:

```python
from cheqi.models.generated.client_credentials_token_request import ClientCredentialsTokenRequest

token = sdk.oauth_service.request_access_token(ClientCredentialsTokenRequest(
    client_id=client_id,
    client_secret=client_secret,
    grant_id=str(grant_id),
    scope="receipt:issue",
))
# token.access_token, token.expires_in
```

The SDK does not cache or refresh tokens. Store each token with its expiry in your own token
store, request a new one before it expires, and pass the current token with `RequestOptions`.

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
    options=RequestOptions.with_access_token(access_token),
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
    options=RequestOptions.with_access_token(access_token),
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
    options=RequestOptions.with_access_token(access_token),
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
resolution = sdk.matching_service.match_customer(identification, options=options)
delivery = sdk.encryption_service.encrypt_for_device(payload.to_json(), resolution.recipients[0])
receipt_hash = sdk.verification_service.calculate_cheqi_receipt_hash(payload.to_json())
canonical_json = sdk.verification_service.canonicalize_cheqi_receipt(payload)
ubl_hash = sdk.verification_service.calculate_ubl_hash(ubl_xml)
stores = sdk.store_service.get_stores(company_id, options=options)
```

## Development

```bash
python -m pip install -e '.[dev]'
pytest
ruff check src tests
mypy src/cheqi
```


## Match recovery and low-level tools

`issue_receipt` returns `ReceiptResult.state`: `DIGITAL_SUBMITTED`, `DIGITAL_PENDING`,
`DIGITAL_EXPIRED`, `DOWNLOAD_FALLBACK`, or the existing `EMAIL_FALLBACK`.
An uncertain digital acknowledgement preserves `match_id` and prepares an encrypted
download locally. Upload `prepared_download` before the QR can serve its content.
Persist that object locally (it includes the secret URL fragment), and retain the original QR.

```python
match = sdk.receipt_service.get_match(match_id)
envelope = sdk.receipt_service.generate_encrypted_receipt_envelope(
    match, receipt_payload, store_id=store_id,
)
submission = sdk.receipt_service.submit_encrypted_receipt(envelope)

# Alternatively, one explicit high-level recovery operation:
result = sdk.receipt_service.resume_receipt(match_id, receipt_payload, store_id=store_id)
# Upload the original persisted fallback independently:
sdk.receipt_service.upload_prepared_download(prepared_download)
```

Generated `MatchStatusResponse`, `MatchState`, `EncryptedReceiptEnvelope`,
`ReceiptSubmissionResponse`, and `ClientReceiptDownloadRequest` are reused.
Recovery needs no PAR, PAR-derived hash, saved resolution, or saved recipient keys.
Completed submissions are recoverable after expiry; unsubmitted expiry is terminal
(`DIGITAL_EXPIRED`, `retryable=False`). A healthy no-route match still raises
customer-not-found rather than bypassing fallback policy.
The existing HTTP retry policy is unchanged. No polling, queues, storage, or background
workers are added: integration partners own scheduling and recovery architecture.
Low-level failures preserve API status, code, correlation id and in-progress retry delay.
See [the recovery flow](docs/receipt-retry.mmd).
