"""Compare two OpenAPI YAML documents without depending on mapping order."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional, Sequence

import yaml


def first_difference(expected: Any, actual: Any, path: str = "$") -> Optional[str]:
    """Return the first semantic difference between two parsed YAML values."""
    if type(expected) is not type(actual):
        return f"{path}: expected {type(expected).__name__}, got {type(actual).__name__}"

    if isinstance(expected, dict):
        expected_keys = set(expected)
        actual_keys = set(actual)
        if missing := sorted(expected_keys - actual_keys):
            return f"{path}: missing keys {missing}"
        if unexpected := sorted(actual_keys - expected_keys):
            return f"{path}: unexpected keys {unexpected}"
        for key in expected:
            if difference := first_difference(expected[key], actual[key], f"{path}.{key}"):
                return difference
        return None

    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path}: expected {len(expected)} items, got {len(actual)}"
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            if difference := first_difference(expected_item, actual_item, f"{path}[{index}]"):
                return difference
        return None

    if expected != actual:
        return f"{path}: expected {expected!r}, got {actual!r}"
    return None


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def main(argv: Sequence[str]) -> int:
    if len(argv) not in (3, 4):
        print(f"Usage: {argv[0]} LOCAL_SPEC REMOTE_SPEC [REMOTE_URL]", file=sys.stderr)
        return 2

    local_path = Path(argv[1])
    remote_path = Path(argv[2])
    remote_label = argv[3] if len(argv) == 4 else str(remote_path)

    try:
        difference = first_difference(load_yaml(local_path), load_yaml(remote_path))
    except (OSError, yaml.YAMLError) as error:
        print(f"ERROR: Unable to compare OpenAPI documents: {error}", file=sys.stderr)
        return 2

    if difference is None:
        print("Spec is up to date.")
        return 0

    print(f"ERROR: Local openapi.yaml differs from {remote_label}", file=sys.stderr)
    print(f"First semantic difference: {difference}", file=sys.stderr)
    print("Run 'make fetch-spec' to update.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
