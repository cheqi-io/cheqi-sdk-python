"""Tests for RFC 8785 JSON canonicalization."""

from __future__ import annotations

import json

from cheqi.utils.hash import sha256_hex
from cheqi.utils.rfc8785 import canonicalize, canonicalize_str


class TestRFC8785:
    """Verify RFC 8785 canonicalization produces deterministic output."""

    def test_sorted_keys(self) -> None:
        data = {"z": 1, "a": 2, "m": 3}
        result = canonicalize_str(data)
        assert result == '{"a":2,"m":3,"z":1}'

    def test_nested_sorted_keys(self) -> None:
        data = {"b": {"z": 1, "a": 2}, "a": 1}
        result = canonicalize_str(data)
        assert result == '{"a":1,"b":{"a":2,"z":1}}'

    def test_null_value(self) -> None:
        data = {"a": None}
        result = canonicalize_str(data)
        assert result == '{"a":null}'

    def test_boolean_values(self) -> None:
        data = {"t": True, "f": False}
        result = canonicalize_str(data)
        assert result == '{"f":false,"t":true}'

    def test_integer_values(self) -> None:
        data = {"n": 42}
        result = canonicalize_str(data)
        assert result == '{"n":42}'

    def test_string_escaping(self) -> None:
        data = {"s": 'hello\n"world"'}
        result = canonicalize_str(data)
        assert result == '{"s":"hello\\n\\"world\\""}'

    def test_array_values(self) -> None:
        data = {"a": [3, 1, 2]}
        result = canonicalize_str(data)
        # Arrays preserve order
        assert result == '{"a":[3,1,2]}'

    def test_empty_object(self) -> None:
        assert canonicalize_str({}) == "{}"

    def test_empty_array(self) -> None:
        assert canonicalize_str([]) == "[]"

    def test_from_json_string(self) -> None:
        json_str = '{"z": 1, "a": 2}'
        result = canonicalize_str(json_str)
        assert result == '{"a":2,"z":1}'

    def test_bytes_output(self) -> None:
        data = {"a": 1}
        result = canonicalize(data)
        assert isinstance(result, bytes)
        assert result == b'{"a":1}'

    def test_canonical_hash_deterministic(self) -> None:
        data1 = '{"z": 1, "a": 2, "m": 3}'
        data2 = '{"a": 2, "m": 3, "z": 1}'

        canonical1 = canonicalize_str(data1)
        canonical2 = canonicalize_str(data2)

        # Same canonical form regardless of input key order
        assert canonical1 == canonical2

        hash1 = sha256_hex(canonical1)
        hash2 = sha256_hex(canonical2)
        assert hash1 == hash2

    def test_float_zero(self) -> None:
        data = {"n": 0.0}
        result = canonicalize_str(data)
        assert result == '{"n":0}'

    def test_control_char_escaping(self) -> None:
        data = {"s": "\x01\x1f"}
        result = canonicalize_str(data)
        assert result == '{"s":"\\u0001\\u001f"}'
