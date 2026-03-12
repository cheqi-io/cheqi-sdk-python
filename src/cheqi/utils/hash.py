"""SHA-256 hashing utilities."""

from __future__ import annotations

import hashlib


def sha256_hex(data: str) -> str:
    """Compute SHA-256 hash of a string and return as hex digest."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hash of bytes and return as hex digest."""
    return hashlib.sha256(data).hexdigest()
