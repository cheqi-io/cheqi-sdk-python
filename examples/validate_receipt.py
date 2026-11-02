"""Validate receipt payload JSON and print all detected findings."""

import sys
from pathlib import Path

from cheqi import ReceiptPayloadValidator

report = ReceiptPayloadValidator().validate_json(Path(sys.argv[1]).read_text(encoding="utf-8"))
if report.valid:
    print("Receipt payload is valid.")
else:
    print("Receipt payload is invalid:")
    for issue in report.issues:
        print(f"{issue.rule_id} — {issue.path}: {issue.message}")
    raise SystemExit(1)
