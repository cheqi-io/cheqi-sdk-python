from __future__ import annotations

import gzip
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from cheqi import CheqiSDKError, ErrorCodes, ReceiptPayloadValidator
from cheqi.models import ReceiptPayload
from cheqi.models.generated.receipt_payload import ReceiptPayload as GeneratedReceiptPayload
from cheqi.validation import _load_module, _verify_bundle

FIXTURES = Path(__file__).parent / "fixtures" / "validation"
with gzip.open(FIXTURES / "parity-cases.json.gz", "rt") as source:
    CASES = json.load(source)


def payload() -> ReceiptPayload:
    return ReceiptPayload.model_validate_json((FIXTURES / "receipt-payload.json").read_bytes())


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_bundled_validator_matches_all_native_reference_reports(case: dict[str, str]) -> None:
    report = ReceiptPayloadValidator().validate_json(case["input"])
    assert report.model_dump(mode="json", by_alias=True) == json.loads(case["expected"])


def test_all_findings_are_structured_and_readable_on_the_existing_exception() -> None:
    receipt = payload()
    receipt.payment_details.amount_due = None
    receipt.payment_details.rounding_amount = None
    receipt.products[0].taxes[0].category = None
    with pytest.raises(CheqiSDKError) as caught:
        ReceiptPayloadValidator().require_valid_json(receipt)
    error = caught.value
    assert error.is_validation_error
    assert not error.validation_report.complete_document
    assert not error.validation_report.valid
    paths = {issue.path for issue in error.validation_report.issues}
    assert {"paymentDetails.amountDue", "paymentDetails.roundingAmount", "products[0].taxes[0].category"} <= paths
    for issue in error.validation_report.issues:
        assert issue.rule_id in str(error)
        assert issue.path in str(error)
        assert issue.message in str(error)
    with pytest.raises(ValidationError):
        error.validation_report.valid = True


@pytest.mark.parametrize("model", [ReceiptPayload, GeneratedReceiptPayload])
def test_decimal_values_and_scale_survive_models_and_validation_unchanged(model: type) -> None:
    receipt = model.model_validate_json((FIXTURES / "receipt-payload.json").read_bytes())
    precise = Decimal("8.9050000000000001")
    receipt.products[0].unit_price = precise
    before = receipt.model_dump_json(by_alias=True, exclude_none=True)
    encoded = ReceiptPayloadValidator().require_valid_json(receipt)
    assert encoded == before
    assert json.loads(encoded)["products"][0]["unitPrice"] == "8.9050000000000001"
    assert receipt.products[0].unit_price == precise
    assert receipt.total_amount == Decimal("19.41")
    receipt.total_amount = Decimal("19.4100")
    assert json.loads(receipt.model_dump_json(by_alias=True))["totalAmount"] == "19.4100"


def test_generated_json_helpers_preserve_precise_input() -> None:
    receipt = payload()
    receipt.products[0].unit_price = Decimal("8.9050000000000001")
    restored = GeneratedReceiptPayload.from_json(receipt.to_json())
    assert restored.products[0].unit_price == Decimal("8.9050000000000001")


def test_required_fields_and_collection_limits_come_from_generated_schema() -> None:
    data = json.loads((FIXTURES / "receipt-payload.json").read_text())
    for field in ["paymentDetails", "taxes"]:
        invalid = dict(data)
        del invalid[field]
        with pytest.raises(ValidationError) as caught:
            GeneratedReceiptPayload.model_validate(invalid)
        assert any(item["loc"] == (field,) for item in caught.value.errors())
    for field in ["taxes", "products"]:
        with pytest.raises(ValidationError):
            GeneratedReceiptPayload.model_validate({**data, field: []})


def test_concurrent_validation_calls_have_independent_state() -> None:
    raw = (FIXTURES / "receipt-payload.json").read_text()
    validator = ReceiptPayloadValidator()
    assert validator.validate_json(raw).valid
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(lambda _: validator.validate_json(raw).valid, range(20)))


def test_corrupt_bundle_is_rejected_before_compilation() -> None:
    wasm = b"wrong module"
    manifest = {"abiVersion": 1, "sourceDirty": False, "target": "wasm32-unknown-unknown",
                "sourceCommit": "a" * 40, "engineVersion": "0.4.4", "sha256": hashlib.sha256(b"original").hexdigest()}
    with pytest.raises(ValueError, match="checksum mismatch"):
        _verify_bundle(wasm, manifest)
    manifest["sourceDirty"] = True
    with pytest.raises(ValueError, match="clean source"):
        _verify_bundle(wasm, manifest)


def test_missing_bundle_stops_validation_with_original_cause(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import cheqi.validation

    _load_module.cache_clear()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(cheqi.validation, "files", lambda _: tmp_path)
            with pytest.raises(CheqiSDKError) as caught:
                ReceiptPayloadValidator().validate(payload())
            assert caught.value.error_code == ErrorCodes.CONFIGURATION_ERROR
            assert isinstance(caught.value.__cause__, FileNotFoundError)
            assert "cheqi-receipt-validator.wasm" in str(caught.value)
    finally:
        _load_module.cache_clear()


def test_a_trapped_instance_is_discarded_and_next_call_can_validate(monkeypatch: pytest.MonkeyPatch) -> None:
    import cheqi.validation

    with monkeypatch.context() as patch:
        patch.setattr(cheqi.validation, "_FUEL", 1)
        with pytest.raises(CheqiSDKError) as caught:
            ReceiptPayloadValidator().validate(payload())
        assert caught.value.error_code == ErrorCodes.CONFIGURATION_ERROR
        assert caught.value.__cause__ is not None
    assert ReceiptPayloadValidator().validate(payload()).valid


def test_serialization_failure_keeps_the_underlying_exception() -> None:
    with pytest.raises(CheqiSDKError) as caught:
        ReceiptPayloadValidator().validate(None)
    assert caught.value.error_code == ErrorCodes.VALIDATION_ERROR
    assert isinstance(caught.value.__cause__, TypeError)
    assert "ReceiptPayload" in str(caught.value)
