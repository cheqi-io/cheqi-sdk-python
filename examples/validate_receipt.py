"""Validate a receipt, then demonstrate rejection before any API request."""

import sys
from pathlib import Path

import httpx

from cheqi import CheqiSDK, CheqiSDKError, ReceiptPayloadValidator
from cheqi.models import IdentificationDetails, ReceiptPayload

receipt = ReceiptPayload.model_validate_json(Path(sys.argv[1]).read_bytes())
print(f"Original payload valid: {ReceiptPayloadValidator().validate(receipt).valid}")
receipt.payment_details.amount_due = None
receipt.payment_details.rounding_amount = None
requests = []


def unexpected_request(request):
    requests.append(request)
    raise AssertionError("Invalid receipts must not reach the API")


with httpx.Client(transport=httpx.MockTransport(unexpected_request)) as client:
    sdk = CheqiSDK(custom_api_endpoint="https://api.example", api_key="offline-example", http_client=client)
    try:
        sdk.receipt_service.issue_receipt(IdentificationDetails(pairing_code="12345678"), receipt)
        raise AssertionError("The incomplete receipt should have been rejected")
    except CheqiSDKError as error:
        if error.validation_report is None:
            raise
        print(f"Issuance stopped locally: {error.error_code}")
        for issue in error.validation_report.issues:
            print(f"{issue.rule_id} — {issue.path}: {issue.message}")
    finally:
        sdk.close()
assert not requests
