"""Verification service for receipt integrity using RFC 8785 JSON canonicalization."""

from __future__ import annotations

from cheqi.utils.hash import sha256_hex
from cheqi.utils.rfc8785 import canonicalize_str


class VerificationService:
    """Receipt integrity verification via canonical hashing."""

    def canonicalize_and_hash_json(self, json_str: str) -> str:
        """Canonicalize JSON per RFC 8785 and compute SHA-256 hash.

        Args:
            json_str: JSON string to canonicalize.

        Returns:
            Hex-encoded SHA-256 hash of the canonical JSON.
        """
        canonical = canonicalize_str(json_str)
        return sha256_hex(canonical)

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
