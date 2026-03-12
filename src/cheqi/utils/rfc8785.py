"""RFC 8785 JSON Canonicalization Scheme (JCS).

Produces deterministic JSON output with:
- Sorted object keys (lexicographic by Unicode code point)
- Specific number formatting (no trailing zeros, no unnecessary decimal point)
- Minimal string escaping per JSON spec
- No whitespace between tokens
"""

from __future__ import annotations

import json
import math
import struct
from typing import Any


def canonicalize(data: Any) -> bytes:
    """Canonicalize a Python object to RFC 8785 JSON bytes.

    Args:
        data: A Python object (dict, list, str, int, float, bool, None)
              or a JSON string to be parsed and canonicalized.

    Returns:
        UTF-8 encoded canonical JSON bytes.
    """
    if isinstance(data, str):
        data = json.loads(data)
    return _serialize(data).encode("utf-8")


def canonicalize_str(data: Any) -> str:
    """Canonicalize a Python object to RFC 8785 JSON string."""
    if isinstance(data, str):
        data = json.loads(data)
    return _serialize(data)


def _serialize(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _serialize_number(value)
    if isinstance(value, str):
        return _serialize_string(value)
    if isinstance(value, list):
        items = ",".join(_serialize(item) for item in value)
        return f"[{items}]"
    if isinstance(value, dict):
        # Sort keys by Unicode code point order
        sorted_keys = sorted(value.keys())
        pairs = ",".join(
            f"{_serialize_string(k)}:{_serialize(value[k])}" for k in sorted_keys
        )
        return "{" + pairs + "}"
    raise TypeError(f"Cannot canonicalize type: {type(value)}")


def _serialize_number(value: float) -> str:
    """Serialize a number per RFC 8785 rules (ES6 Number serialization)."""
    if math.isnan(value) or math.isinf(value):
        raise ValueError("NaN and Infinity are not valid JSON values")

    if value == 0:
        return "0"

    # Use ES6/IEEE 754 number serialization
    # Check if it's an integer value
    if value == int(value) and abs(value) < 2**53:
        return str(int(value))

    # Use repr-like formatting that matches ES6 Number.toString()
    return _es6_number_to_string(value)


def _es6_number_to_string(value: float) -> str:
    """Format a float according to ES6 Number.prototype.toString() rules."""
    # Get the shortest representation that round-trips
    s = repr(value)
    # Python's repr should already produce the shortest representation
    # but we need to handle a few edge cases

    # Remove trailing zeros after decimal point, but keep at least one digit
    if "." in s and "e" not in s and "E" not in s:
        s = s.rstrip("0").rstrip(".")

    return s


def _serialize_string(value: str) -> str:
    """Serialize a string with JSON escaping per RFC 8785."""
    result = ['"']
    for ch in value:
        code = ord(ch)
        if ch == '"':
            result.append('\\"')
        elif ch == "\\":
            result.append("\\\\")
        elif ch == "\b":
            result.append("\\b")
        elif ch == "\f":
            result.append("\\f")
        elif ch == "\n":
            result.append("\\n")
        elif ch == "\r":
            result.append("\\r")
        elif ch == "\t":
            result.append("\\t")
        elif code < 0x20:
            result.append(f"\\u{code:04x}")
        else:
            result.append(ch)
    result.append('"')
    return "".join(result)
