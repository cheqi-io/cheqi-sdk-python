"""Stateless helpers for client-encrypted receipt download links."""

from __future__ import annotations

import base64
import os
import re
from typing import Callable
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from cheqi.config import Environment
from cheqi.models.download import DownloadLink
from cheqi.models.envelopes import ReceiptEnvelope
from cheqi.models.receipt import ReceiptTemplateResponse

_DOWNLOAD_ID_LENGTH = 16
_CONTENT_KEY_LENGTH = 32
_IV_LENGTH = 12
_DOWNLOAD_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{22,64}$")
_CONTENT_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


class DownloadService:
    """Generate, parse, encrypt, and decrypt download-link payloads locally."""

    PRODUCTION_BASE_URL = "https://receipt.cheqi.io"
    SANDBOX_BASE_URL = "https://sandbox.receipt.cheqi.io"

    def __init__(self, random_bytes: Callable[[int], bytes] = os.urandom) -> None:
        self._random_bytes = random_bytes

    def generate_download_link(self, environment_or_base_url: Environment | str) -> DownloadLink:
        """Generate an unguessable id and fragment-only AES-256 content key."""
        if isinstance(environment_or_base_url, Environment):
            base_url = environment_or_base_url.receipt_download_base_url
        else:
            base_url = environment_or_base_url
        if not base_url or not base_url.strip():
            raise ValueError("base_url cannot be null or empty")

        download_id = self._base64url(self._random_exact(_DOWNLOAD_ID_LENGTH))
        content_key = self._base64url(self._random_exact(_CONTENT_KEY_LENGTH))
        return DownloadLink(
            download_id=download_id,
            content_key=content_key,
            url=self.build_download_url(base_url, download_id, content_key),
        )

    def build_download_url(self, base_url: str, download_id: str, content_key: str) -> str:
        """Build a URL whose key remains in the browser-only fragment."""
        if not base_url or not base_url.strip():
            raise ValueError("base_url cannot be null or empty")
        self._validate_download_id(download_id)
        self._decode_content_key(content_key)
        return f"{base_url.rstrip('/')}/{download_id}#{content_key}"

    def parse_download_url(self, url: str) -> DownloadLink:
        """Recover an id and content key from a previously generated URL."""
        try:
            parsed = urlsplit(url)
            download_id = parsed.path.rsplit("/", 1)[-1]
            content_key = parsed.fragment
            self._validate_download_id(download_id)
            self._decode_content_key(content_key)
            return DownloadLink(download_id=download_id, content_key=content_key, url=url)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("Invalid receipt download URL") from exc

    def build_download_envelope(self, template: ReceiptTemplateResponse) -> ReceiptEnvelope:
        """Map every available server-generated format into the encrypted envelope."""
        if template is None:
            raise ValueError("template cannot be null")
        return ReceiptEnvelope(
            cheqi=template.cheqi,
            ubl_purchase_receipt=template.ubl_purchase_receipt,
            ubl_invoice=template.ubl_invoice,
            vat_metadata=template.vat_metadata,
        )

    def encrypt_download_envelope(self, envelope: ReceiptEnvelope, content_key: str) -> str:
        """Return Base64(iv || ciphertext || tag), interoperable with Java/JavaScript."""
        if envelope is None:
            raise ValueError("envelope cannot be null")
        key = self._decode_content_key(content_key)
        iv = self._random_exact(_IV_LENGTH)
        ciphertext_and_tag = AESGCM(key).encrypt(iv, envelope.to_json().encode("utf-8"), None)
        return base64.b64encode(iv + ciphertext_and_tag).decode("ascii")

    def decrypt_download_envelope(self, ciphertext: str, content_key: str) -> ReceiptEnvelope:
        """Decrypt and parse a download envelope."""
        try:
            combined = base64.b64decode(ciphertext, validate=True)
            if len(combined) < _IV_LENGTH + 16:
                raise ValueError("ciphertext is too short")
            plaintext = AESGCM(self._decode_content_key(content_key)).decrypt(
                combined[:_IV_LENGTH], combined[_IV_LENGTH:], None
            )
            return ReceiptEnvelope.model_validate_json(plaintext)
        except Exception as exc:
            raise ValueError("Download envelope decryption failed") from exc

    @staticmethod
    def _base64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    def _random_exact(self, length: int) -> bytes:
        value = self._random_bytes(length)
        if len(value) != length:
            raise ValueError(f"random source returned {len(value)} bytes; expected {length}")
        return value

    @staticmethod
    def _validate_download_id(download_id: str) -> None:
        if not download_id or not _DOWNLOAD_ID_PATTERN.fullmatch(download_id):
            raise ValueError("download_id must be 22-64 base64url characters")

    @staticmethod
    def _decode_content_key(content_key: str) -> bytes:
        try:
            if not content_key or not _CONTENT_KEY_PATTERN.fullmatch(content_key):
                raise ValueError
            key = base64.b64decode(content_key + "=", altchars=b"-_", validate=True)
            if len(key) != _CONTENT_KEY_LENGTH:
                raise ValueError
            return key
        except (TypeError, ValueError) as exc:
            raise ValueError("content_key must be an unpadded base64url AES-256 key") from exc
