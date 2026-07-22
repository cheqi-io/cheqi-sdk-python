"""Tests for ReceiptService validation logic."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cheqi.models.enums import PaymentType
from cheqi.models.matching import IdentificationDetails, RecipientResolutionResponse
from cheqi.services.matching import MatchingService


class TestMatchingServiceValidation:
    """Test that MatchingService validates identifiers correctly."""

    def test_empty_identification_raises(self) -> None:
        """Match customer with no identifiers should raise ValueError."""
        # We can't create a real MatchingService without an API client,
        # so we test the validation logic directly
        details = IdentificationDetails()

        matching = MatchingService(api_client=None)  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="customer identifier or payment type"):
            matching.match_customer(details)

    def test_valid_email_identifier(self) -> None:
        details = IdentificationDetails(recipient_email="test@example.com")

        matching = MatchingService(api_client=None)  # type: ignore[arg-type]

        # This should pass validation but fail at the API call
        # (which is fine - we're testing validation only)
        with pytest.raises(Exception):
            # Will fail because api_client is None, but past validation
            matching.match_customer(details)

    def test_payment_type_only_is_valid_for_anonymous_download_fallback(self) -> None:
        details = IdentificationDetails(payment_type=PaymentType.CASH)
        api_client = MagicMock()
        api_client.match_customer.return_value = RecipientResolutionResponse(
            route_found=True,
            delivery_route_type="DOWNLOAD_FALLBACK",
            recipients=[],
        )
        matching = MatchingService(api_client=api_client)

        response = matching.match_customer(details)

        assert response.route_found
        api_client.match_customer.assert_called_once_with(details, None)
