"""Verification service for receipt integrity using canonical hashing."""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from cheqi.utils.hash import sha256_hex
from cheqi.utils.rfc8785 import canonicalize_str
from cheqi.utils.xml import canonicalize_xml


class VerificationService:
    """Receipt integrity verification via canonical hashing."""

    def canonicalize_cheqi_receipt(self, receipt: Any) -> str:
        """Canonicalize a JSON string or Python model according to RFC 8785."""
        return canonicalize_str(self._json_value(receipt))

    def calculate_cheqi_receipt_hash(self, receipt: Any) -> str:
        """Calculate the deterministic hash used for CHEQI JSON documents."""
        return sha256_hex(self.canonicalize_cheqi_receipt(receipt))

    def canonicalize_ubl(self, ubl_xml: str) -> str:
        """Canonicalize a UBL document using exclusive XML C14N."""
        return canonicalize_xml(ubl_xml)

    def calculate_ubl_hash(self, ubl_xml: str) -> str:
        """Calculate the canonical SHA-256 hash of a UBL document."""
        return sha256_hex(self.canonicalize_ubl(ubl_xml))

    def canonicalize_and_hash_json(self, json_value: Any) -> str:
        """Canonicalize JSON per RFC 8785 and compute SHA-256 hash.

        Args:
            json_value: JSON string or Python value to canonicalize.

        Returns:
            Hex-encoded SHA-256 hash of the canonical JSON.
        """
        return self.calculate_cheqi_receipt_hash(json_value)

    def verify_json_hash(self, json_str: str, expected_hash: str) -> bool:
        """Verify that a JSON string matches an expected canonical hash.

        Args:
            json_str: JSON string to verify.
            expected_hash: Expected hex-encoded SHA-256 hash.

        Returns:
            True if the canonical hash matches.
        """
        actual_hash = self.canonicalize_and_hash_json(json_str)
        return actual_hash == expected_hash

    def canonicalize_and_hash_xml(self, xml_str: str) -> str:
        """Canonicalize XML and compute a SHA-256 hash.

        Formatting-only whitespace between elements is removed before
        exclusive XML C14N and hashing.
        """
        return self.calculate_ubl_hash(xml_str)

    def verify_xml_hash(self, xml_str: str, expected_hash: str) -> bool:
        """Verify that an XML string matches an expected canonical hash."""
        actual_hash = self.canonicalize_and_hash_xml(xml_str)
        return actual_hash == expected_hash

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, str):
            return value
        if isinstance(value, BaseModel):
            return value.model_dump(by_alias=True, exclude_none=True, mode="json")

        def default(item: object) -> object:
            if dataclasses.is_dataclass(item) and not isinstance(item, type):
                return dataclasses.asdict(item)
            if isinstance(item, (date, datetime, UUID)):
                return str(item) if isinstance(item, UUID) else item.isoformat()
            if isinstance(item, Decimal):
                return float(item)
            if isinstance(item, Enum):
                return item.value
            to_dict = getattr(item, "to_dict", None)
            if callable(to_dict):
                return to_dict()
            raise TypeError(f"Object of type {type(item).__name__} is not JSON serializable")

        return json.loads(json.dumps(value, default=default))
