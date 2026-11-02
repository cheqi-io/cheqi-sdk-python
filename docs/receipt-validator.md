# Receipt payload validator

The wheel and source distribution include the validator WASM module and its
manifest from `src/cheqi/_validator`. Wasmtime 50 loads this pinned module
locally. One compiled module is cached per process; each validation uses a new
store and memory, with a 64 MiB memory limit and fuel limit. The module has no
host imports or network access. Stores are closed on success and failure.
The loader verifies ABI, source provenance and SHA-256 before use.

The artifact comes from merged [Cheqi PR #712](https://github.com/cheqi-io/cheqi/pull/712),
[successful four-language run 41487248795](https://github.com/cheqi-io/cheqi/actions/runs/41487248795),
main commit `fb96508512b4d42eb72078632dd4238c174bbe75`.
It is a tested main artifact, not a published validator release.

`InvoiceValidationReport` and `InvoiceValidationIssue` bind the existing report
contract. No business rules or financial calculations are duplicated in Python.
All receipt entrypoints validate one JSON snapshot before external work and
reuse it for every device and download fallback. No report or receipt contents
are sent to Cheqi by validation.

## Model generation

```sh
make fetch-spec
make generate
```

The backend specification remains the source of truth. Generation is pinned to
OpenAPI Generator 7.12.0. `scripts/finalize_models.py`, invoked by `make generate`,
uses the specification's `format: decimal` to emit Python `Decimal` fields and
Pydantic JSON helpers. This avoids converting financial values to floats or
losing precision through `json.loads`. Generated classes are never edited
manually. Quantity and rate fields retain the backend's numeric types.

The production-spec CI guard remains enabled. The test API schema is ahead of
production; normal production promotion and schema synchronization are required
before SDK publication. No version or release tag is changed by this work.

## Offline example

After installing the SDK wheel, run:

```sh
python examples/validate_receipt.py tests/fixtures/validation/receipt-payload.json
```

It validates a complete receipt, removes amount due and rounding, then calls
normal issuance. Both findings are reported before any API request. It uses a
mock HTTP transport and does not contact Odoo or Cheqi.

## Update the bundled validator

Download a specific tested validator artifact, then run:

```sh
python scripts/update-receipt-validator.py /path/to/verified-bundle
make test
make lint
make typecheck
python -m build
```

The importer rejects dirty source builds, unsupported ABIs and checksum
mismatches. Review the binary and manifest together. The normal SDK release
ships this pinned bundle; customer machines never build Rust or fetch a
validator at runtime.
