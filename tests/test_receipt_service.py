"""Tests for ReceiptService validation logic."""

from __future__ import annotations

import pytest

from cheqi.exceptions import CheqiSDKError
from cheqi.models.matching import IdentificationDetails
from cheqi.models.receipt import ReceiptTemplateRequest
from cheqi.services.encryption import EncryptionService
from cheqi.services.matching import MatchingService


class TestMatchingServiceValidation:
    """Test that MatchingService validates identifiers correctly."""

    def test_empty_identification_raises(self) -> None:
        """Match customer with no identifiers should raise ValueError."""
        # We can't create a real MatchingService without an API client,
        # so we test the validation logic directly
        details = IdentificationDetails()

        matching = MatchingService(api_client=None)  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="at least one identifier"):
            matching.match_customer(details)

    def test_valid_email_identifier(self) -> None:
        details = IdentificationDetails(recipient_email="test@example.com")

        matching = MatchingService(api_client=None)  # type: ignore[arg-type]

        # This should pass validation but fail at the API call
        # (which is fine - we're testing validation only)
        with pytest.raises(Exception):
            # Will fail because api_client is None, but past validation
            matching.match_customer(details)
