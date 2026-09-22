from __future__ import annotations

from cheqi.models import ReceiptEnvelope, ReceiptEnvelopeDocument
from cheqi.services.download import DownloadService


def _bytes(length: int) -> bytes:
    return bytes(range(length))


def test_download_link_keeps_content_key_in_fragment() -> None:
    service = DownloadService(random_bytes=_bytes)

    link = service.generate_download_link("https://receipt.example")

    assert link.url == f"https://receipt.example/{link.download_id}#{link.content_key}"
    assert service.parse_download_url(link.url) == link


def test_download_envelope_round_trip_uses_generated_contract() -> None:
    service = DownloadService(random_bytes=_bytes)
    link = service.generate_download_link("https://receipt.example")
    envelope = ReceiptEnvelope(
        cheqi_receipt_id="receipt-1",
        documents={
            "CHEQI": ReceiptEnvelopeDocument(
                content='{"documentNumber":"POS-1"}',
                media_type="application/json",
            )
        },
        envelope_version=1,
        receipt_generator_version="receipt-payload-v1",
        receipt_uuid="34d267cf-357f-41d6-a62a-d7cb680aa3ba",
    )

    ciphertext = service.encrypt_download_envelope(envelope, link.content_key)
    decrypted = service.decrypt_download_envelope(ciphertext, link.content_key)

    assert decrypted == envelope
