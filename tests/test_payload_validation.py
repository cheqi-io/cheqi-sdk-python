from __future__ import annotations

import gzip
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cheqi import CheqiSDKError, ErrorCodes, ReceiptPayloadValidator
from cheqi.models import ReceiptPayload
from cheqi.validation import _load_module, _verify_bundle

FIXTURES = Path(__file__).parent / "fixtures" / "validation"
with gzip.open(FIXTURES / "parity-cases.json.gz", "rt") as source:
    CASES = json.load(source)


def payload() -> ReceiptPayload:
    return ReceiptPayload.model_validate_json((FIXTURES / "receipt-payload.json").read_bytes())


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_bundled_validator_matches_reference_reports(case: dict[str, str]) -> None:
    report = ReceiptPayloadValidator().validate_json(case["input"])
    assert report.model_dump(mode="json", by_alias=True) == json.loads(case["expected"])


def test_validation_preserves_existing_model_values_and_numeric_json() -> None:
    receipt = payload()
    original_json = receipt.to_json()
    assert ReceiptPayloadValidator().validate(receipt).valid
    ReceiptPayloadValidator().validate_or_raise(receipt)
    assert receipt.to_json() == original_json
    assert json.loads(original_json)["totalAmount"] == 19.41
    assert json.loads(original_json)["products"][0]["unitPrice"] == 8.905
    assert json.loads(original_json)["paymentDetails"]["roundingAmount"] == 0


def test_all_findings_are_available_on_the_existing_exception() -> None:
    receipt = payload()
    receipt.payment_details.amount_due = None
    receipt.payment_details.rounding_amount = None
    receipt.products[0].taxes[0].category = None
    original_json = receipt.to_json()
    with pytest.raises(CheqiSDKError) as caught:
        ReceiptPayloadValidator().validate_or_raise(receipt)
    error = caught.value
    assert error.is_validation_error
    assert not error.validation_report.valid
    assert not error.validation_report.complete_document
    paths = {issue.path for issue in error.validation_report.issues}
    assert {"paymentDetails.amountDue", "paymentDetails.roundingAmount", "products[0].taxes[0].category"} <= paths
    for issue in error.validation_report.issues:
        assert issue.rule_id in str(error)
        assert issue.path in str(error)
        assert issue.message in str(error)
    assert receipt.to_json() == original_json


def test_concurrent_calls_have_independent_validation_state() -> None:
    raw = (FIXTURES / "receipt-payload.json").read_text()
    validator = ReceiptPayloadValidator()
    assert validator.validate_json(raw).valid
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(lambda _: validator.validate_json(raw).valid, range(20)))


def test_corrupt_bundle_is_rejected_before_compilation() -> None:
    manifest = {"abiVersion": 1, "sourceDirty": False, "target": "wasm32-unknown-unknown",
                "sourceCommit": "a" * 40, "engineVersion": "0.4.4", "sha256": hashlib.sha256(b"original").hexdigest()}
    with pytest.raises(ValueError, match="checksum mismatch"):
        _verify_bundle(b"wrong module", manifest)
    manifest["sourceDirty"] = True
    with pytest.raises(ValueError, match="clean source"):
        _verify_bundle(b"wrong module", manifest)


def test_missing_bundle_reports_the_original_cause(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import cheqi.validation

    _load_module.cache_clear()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(cheqi.validation, "files", lambda _: tmp_path)
            with pytest.raises(CheqiSDKError) as caught:
                ReceiptPayloadValidator().validate(payload())
            assert caught.value.error_code == ErrorCodes.CONFIGURATION_ERROR
            assert isinstance(caught.value.__cause__, FileNotFoundError)
    finally:
        _load_module.cache_clear()


def test_a_trapped_instance_does_not_affect_the_next_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    import cheqi.validation

    with monkeypatch.context() as patch:
        patch.setattr(cheqi.validation, "_FUEL", 1)
        with pytest.raises(CheqiSDKError) as caught:
            ReceiptPayloadValidator().validate(payload())
        assert caught.value.error_code == ErrorCodes.CONFIGURATION_ERROR
        assert caught.value.__cause__ is not None
    assert ReceiptPayloadValidator().validate(payload()).valid


def test_wrong_payload_type_reports_a_validation_error() -> None:
    with pytest.raises(CheqiSDKError) as caught:
        ReceiptPayloadValidator().validate(None)
    assert caught.value.error_code == ErrorCodes.VALIDATION_ERROR
    assert isinstance(caught.value.__cause__, TypeError)
