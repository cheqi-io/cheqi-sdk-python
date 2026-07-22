"""Parity tests for Java-compatible encrypted receipt download links."""

from __future__ import annotations

import re

import pytest

from cheqi.config import Environment
from cheqi.models.envelopes import ReceiptEnvelope
from cheqi.models.receipt import CheqiReceipt, ReceiptTemplateResponse, VatMetadata
from cheqi.services.download import DownloadService


def test_generates_and_parses_fragment_key_link() -> None:
    service = DownloadService()
    link = service.generate_download_link(Environment.PRODUCTION)

    assert re.fullmatch(r"[A-Za-z0-9_-]{22}", link.download_id)
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", link.content_key)
    assert link.url == f"https://receipt.cheqi.io/{link.download_id}#{link.content_key}"
    assert service.parse_download_url(link.url) == link
    assert link.content_key not in repr(link)


def test_environment_origins_match_java_sdk() -> None:
    service = DownloadService()

    assert service.generate_download_link(Environment.PRODUCTION).url.startswith(
        "https://receipt.cheqi.io/"
    )
    assert service.generate_download_link(Environment.SANDBOX).url.startswith(
        "https://sandbox.receipt.cheqi.io/"
    )


def test_download_envelope_round_trip_includes_every_receipt_format() -> None:
    service = DownloadService()
    link = service.generate_download_link(Environment.SANDBOX)
    template = ReceiptTemplateResponse(
        cheqi=CheqiReceipt(document_number="PY-1"),
        ubl_purchase_receipt="<PurchaseReceipt/>",
        ubl_invoice="<Invoice/>",
        vat_metadata=VatMetadata(taxes_applied=True),
    )

    ciphertext = service.encrypt_download_envelope(
        service.build_download_envelope(template), link.content_key
    )
    decrypted = service.decrypt_download_envelope(ciphertext, link.content_key)

    assert decrypted.cheqi is not None
    assert decrypted.cheqi.document_number == "PY-1"
    assert decrypted.ubl_purchase_receipt == "<PurchaseReceipt/>"
    assert decrypted.ubl_invoice == "<Invoice/>"
    assert decrypted.vat_metadata is not None
    assert decrypted.vat_metadata.taxes_applied is True


def test_encryption_matches_java_interop_vector() -> None:
    service = DownloadService(lambda length: bytes(range(length)))
    content_key = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"

    ciphertext = service.encrypt_download_envelope(
        ReceiptEnvelope(cheqi=CheqiReceipt(document_number="INTEROP")), content_key
    )

    assert ciphertext == (
        "AAECAwQFBgcICQoLPCC1c6CUqzm3OrXv3ooNAOa483qFFj0ZSkXfp1QnVPdTX/"
        "7e0rxBB1BCAdhTN4LdhEsU+1LX"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://receipt.cheqi.io/too-short#bad",
        "https://receipt.cheqi.io/Zk9qYx3vT1KpN8wL2sRd_g",
    ],
)
def test_rejects_invalid_download_urls(url: str) -> None:
    with pytest.raises(ValueError, match="Invalid receipt download URL"):
        DownloadService().parse_download_url(url)
