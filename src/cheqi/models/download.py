"""Models for client-generated, end-to-end encrypted receipt downloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pydantic import Field

from cheqi.models.base import CheqiBaseModel


@dataclass(frozen=True)
class DownloadLink:
    """Public URL plus the local credentials from which it was generated."""

    download_id: str
    content_key: str
    url: str

    def __repr__(self) -> str:
        return f"DownloadLink(download_id={self.download_id!r}, url='<redacted>')"


class ClientReceiptDownloadRequest(CheqiBaseModel):
    """Exact ciphertext stored behind a client-generated download id."""

    download_id: str = Field(pattern=r"^[A-Za-z0-9_-]{22,64}$")
    ciphertext: str = Field(min_length=1)
    template_hash: Optional[str] = None


class ClientReceiptDownloadResponse(CheqiBaseModel):
    """Identifiers returned after Cheqi accepts the encrypted upload."""

    cheqi_receipt_id: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
