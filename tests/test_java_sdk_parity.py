from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

from cheqi import CheqiApiError, CheqiSDK, ErrorCodes, __version__
from cheqi.config import Environment
from cheqi.models import (
    EncryptedReceiptDeliveryResponse,
    ExpenseSubmissionEnvelope,
    IdentificationDetails,
    InviteEmployeeRequest,
    ReceiptEnvelope,
    ReceiptEnvelopeDocument,
    ReceivingParty,
)
from cheqi.services.verification import VerificationService


def test_sdk_version_and_user_agent_use_python_release_line() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"routeFound": True, "deliveryRouteType": "DIGITAL", "matchId": "match-1"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sdk = CheqiSDK(
        environment=Environment.SANDBOX,
        api_key="example_api_key",
        http_client=client,
    )

    sdk.matching_service.match_customer(IdentificationDetails(pairing_code="12345678"))
    sdk.close()

    assert __version__ == "2.0.0"
    assert requests[0].url == "https://sandbox.api.cheqi.io/recipient/resolve"
    assert requests[0].headers["User-Agent"] == "CheqiSDK-Python/2.0.0"
    assert not client.is_closed
    client.close()


def test_java_2_3_schema_models_are_public_and_nested_in_receipt_envelope() -> None:
    submitted_at = datetime(2026, 9, 23, 8, 30, tzinfo=timezone.utc)
    expense = ExpenseSubmissionEnvelope(
        expense_submission_id="2315a790-7838-413f-bbb1-a8ec05401f29",
        target_company_id="5c5f6883-e36b-41ef-b9ed-c43454ac546c",
        submitted_by_user_id="a58d53ad-dfcb-4a5d-8727-56ad4b6b2528",
        submitted_at=submitted_at,
        reason="Customer visit",
    )
    envelope = ReceiptEnvelope(
        cheqi_receipt_id="receipt-1",
        documents={
            "CHEQI": ReceiptEnvelopeDocument(
                content='{"documentNumber":"POS-1"}',
                media_type="application/json",
            )
        },
        envelope_version=1,
        expense_submission=expense,
        receipt_generator_version="1.0.0",
        receipt_uuid="34d267cf-357f-41d6-a62a-d7cb680aa3ba",
    )
    invitation = InviteEmployeeRequest(
        emails=["employee@example.com"],
    )

    data = json.loads(envelope.model_dump_json(by_alias=True))
    assert data["expenseSubmission"]["reason"] == "Customer visit"
    assert invitation.emails == ["employee@example.com"]

    delivery = EncryptedReceiptDeliveryResponse(
        delivery_purpose="COMPANY_EXPENSE",
        expense_submission_id=expense.expense_submission_id,
        submitted_by_user_id=expense.submitted_by_user_id,
    )
    receiving_party = ReceivingParty(contact_first_name="Ada", contact_last_name="Lovelace")
    assert delivery.delivery_purpose == "COMPANY_EXPENSE"
    assert receiving_party.contact_first_name == "Ada"


def test_verification_service_supports_java_api_operations_and_python_models() -> None:
    service = VerificationService()
    value = {"z": 1, "a": 2}
    ubl = "<Invoice><ID>1</ID></Invoice>"

    assert service.canonicalize_cheqi_receipt(value) == '{"a":2,"z":1}'
    assert service.calculate_cheqi_receipt_hash(value) == service.canonicalize_and_hash_json(value)
    assert service.canonicalize_ubl(ubl) == "<Invoice><ID>1</ID></Invoice>"
    assert service.calculate_ubl_hash(ubl) == service.canonicalize_and_hash_xml(ubl)


def test_exception_introspection_matches_java_sdk() -> None:
    error = CheqiApiError(
        "rate limited",
        error_code=ErrorCodes.RATE_LIMIT_EXCEEDED,
        http_status_code=429,
        correlation_id="correlation-1",
    )

    assert error.has_http_status_code
    assert error.has_correlation_id
    assert error.is_client_error
    assert not error.is_server_error
    assert error.is_rate_limit_error
    assert error.is_retryable
    assert error.timestamp > 0
