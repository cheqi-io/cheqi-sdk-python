#!/usr/bin/env python3
"""Import a verified, pinned producer bundle; SDK builds and runtime stay offline."""
import argparse
import hashlib
import json
import pathlib
import re
import shutil

parser = argparse.ArgumentParser()
parser.add_argument("bundle", type=pathlib.Path, help="Directory containing WASM and manifest.json")
args = parser.parse_args()
manifest = json.loads((args.bundle / "manifest.json").read_text())
wasm = args.bundle / "cheqi-receipt-validator.wasm"
if (manifest.get("abiVersion") != 1 or manifest.get("sourceDirty") is not False
        or manifest.get("target") != "wasm32-unknown-unknown"
        or not re.fullmatch(r"[0-9a-f]{40}", manifest.get("sourceCommit", ""))
        or hashlib.sha256(wasm.read_bytes()).hexdigest() != manifest.get("sha256")):
    raise SystemExit("Validator bundle failed integrity/provenance checks")
destination = pathlib.Path(__file__).resolve().parents[1] / "src/cheqi/_validator"
destination.mkdir(parents=True, exist_ok=True)
for name in ["cheqi-receipt-validator.wasm", "manifest.json"]:
    shutil.copyfile(args.bundle / name, destination / name)
print(f"Imported validator from {manifest['sourceCommit']}; run the SDK tests before release")
