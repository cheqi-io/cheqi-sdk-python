"""Validate issuer receipt data before matching, encryption or submission."""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from importlib.resources import files
from typing import TYPE_CHECKING, Mapping

from cheqi.exceptions import CheqiSDKError, ErrorCodes
from cheqi.models.generated.receipt_payload import ReceiptPayload
from cheqi.models.validation import InvoiceValidationReport

if TYPE_CHECKING:
    import wasmtime

_MAX_INPUT_BYTES = 2 * 1024 * 1024
_MAX_MEMORY_BYTES = 64 * 1024 * 1024
_FUEL = 200_000_000


def _verify_bundle(wasm: bytes, manifest: Mapping[str, object]) -> None:
    if manifest.get("abiVersion") != 1 or manifest.get("sourceDirty") is not False:
        raise ValueError("Validator requires ABI version 1 and a clean source build")
    if (manifest.get("target") != "wasm32-unknown-unknown"
            or not re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("sourceCommit", "")))
            or not manifest.get("engineVersion")):
        raise ValueError("Validator manifest has invalid source provenance or target")
    actual = hashlib.sha256(wasm).hexdigest()
    if actual != manifest.get("sha256"):
        raise ValueError(f"Validator checksum mismatch: expected {manifest.get('sha256')}, got {actual}")


@lru_cache(maxsize=1)
def _load_module() -> tuple[wasmtime.Engine, wasmtime.Module]:
    import wasmtime

    bundle = files("cheqi").joinpath("_validator")
    wasm = bundle.joinpath("cheqi-receipt-validator.wasm").read_bytes()
    manifest = json.loads(bundle.joinpath("manifest.json").read_text(encoding="utf-8"))
    _verify_bundle(wasm, manifest)
    config = wasmtime.Config()
    config.consume_fuel = True
    engine = wasmtime.Engine(config)
    module = wasmtime.Module(engine, wasm)
    if module.imports:
        raise ValueError("Receipt validator must not require host imports")
    return engine, module


class ReceiptPayloadValidator:
    """Check receipt fields and amounts without changing supplied values."""

    def validate(self, payload: ReceiptPayload) -> InvoiceValidationReport:
        """Return all detected issues for a receipt payload."""
        return self.validate_json(self._serialize(payload))

    def validate_json(self, payload_json: str) -> InvoiceValidationReport:
        """Check public receipt payload JSON and return its validation report."""
        try:
            raw = payload_json.encode("utf-8")
        except Exception as exc:
            raise CheqiSDKError(f"Cannot encode receipt payload: {exc}", ErrorCodes.VALIDATION_ERROR) from exc
        try:
            import wasmtime

            engine, module = _load_module()
            with wasmtime.Store(engine) as store:
                store.set_limits(memory_size=_MAX_MEMORY_BYTES, instances=1, memories=1)
                store.set_fuel(_FUEL)
                api = wasmtime.Instance(store, module, []).exports(store)

                def call(name: str, *args: int) -> int:
                    function = api["cheqi_validator_" + name]
                    if not isinstance(function, wasmtime.Func):
                        raise ValueError(f"Missing validator function: {name}")
                    result = function(store, *args)
                    if not isinstance(result, int):
                        raise ValueError(f"Invalid result from validator function: {name}")
                    return result

                if call("abi_version") != 1:
                    raise ValueError("Unsupported receipt validator ABI")
                memory = api["memory"]
                if not isinstance(memory, wasmtime.Memory) or memory.type(store).limits.max != 1024:
                    raise ValueError("Receipt validator must have bounded memory")
                pointer = call("alloc", min(len(raw), _MAX_INPUT_BYTES + 1))
                if pointer:
                    if memory.write(store, raw, pointer) != len(raw):
                        raise ValueError("Receipt input was not completely written")
                    length = call("validate")
                else:
                    length = call("result_len")
                start = call("result_ptr")
                if (length <= 0 or length != call("result_len") or start < 0
                        or start + length > memory.data_len(store)):
                    raise ValueError("Missing or invalid receipt validation report")
                report = InvoiceValidationReport.model_validate_json(bytes(memory.read(store, start, start + length)))
                if report.valid != (not report.issues):
                    raise ValueError("Receipt validation result disagrees with its issues")
                return report
        except Exception as exc:
            raise CheqiSDKError(f"Receipt validator could not run: {exc}", ErrorCodes.CONFIGURATION_ERROR) from exc

    def validate_or_raise(self, payload: ReceiptPayload) -> None:
        """Stop issuance with all detected receipt data issues."""
        report = self.validate(payload)
        if not report.valid:
            details = "; ".join(f"{issue.rule_id} — {issue.path}: {issue.message}" for issue in report.issues)
            raise CheqiSDKError(
                f"Invalid receipt payload: {details}", ErrorCodes.VALIDATION_ERROR,
                validation_report=report,
            )

    @staticmethod
    def _serialize(payload: ReceiptPayload) -> str:
        try:
            if not isinstance(payload, ReceiptPayload):
                raise TypeError("receipt_payload must be a ReceiptPayload")
            return payload.model_dump_json(by_alias=True, exclude_none=True)
        except Exception as exc:
            raise CheqiSDKError(f"Cannot serialize receipt payload: {exc}", ErrorCodes.VALIDATION_ERROR) from exc
