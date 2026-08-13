"""Models for client-generated, end-to-end encrypted receipt downloads."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadLink:
    """Public URL plus the local credentials from which it was generated."""

    download_id: str
    content_key: str
    url: str

    def __repr__(self) -> str:
        return f"DownloadLink(download_id={self.download_id!r}, url='<redacted>')"
