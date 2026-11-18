import json
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from cheqi.models.receipt import PreparedReceiptDownload
from cheqi.services.credit_note import CreditNoteService
from cheqi.services.download import DownloadService
from cheqi.services.encryption import EncryptionService


def test_credit_note_uses_normal_encrypted_download_without_parent_lookup():
    api = MagicMock()
    service = CreditNoteService(api, EncryptionService(), MagicMock())
    payload = {
        "documentNumber": "CN-123",
        "originatorDocumentReference": " INV-123 ",
        "creditNoteSubtotal": Decimal("12.123456789012345678"),
    }
    prepared = service.prepare_download({"taxesApplied": False, "creditNoteTemplateRequest": payload})
    api.assert_not_called()
    assert not api.mock_calls
    restored = PreparedReceiptDownload.model_validate_json(prepared.model_dump_json())
    downloads = DownloadService()
    link = downloads.parse_download_url(restored.download_url)
    envelope = downloads.decrypt_download_envelope(restored.upload_request.ciphertext, link.content_key)
    document = json.loads(envelope.documents["CREDIT_NOTE_PAYLOAD"].content)
    assert document == {**payload, "creditNoteSubtotal": str(payload["creditNoteSubtotal"]), "taxesApplied": False}
    assert prepared.upload_request == restored.upload_request
    wire = restored.upload_request.model_dump_json(by_alias=True, exclude_none=True)
    assert set(json.loads(wire)) == {"downloadId", "ciphertext"}
    assert "INV-123" not in wire
    assert link.content_key not in wire
    with pytest.raises(ValueError, match="originatorDocumentReference"):
        service.prepare_download({"documentNumber": "CN", "taxesApplied": True})
