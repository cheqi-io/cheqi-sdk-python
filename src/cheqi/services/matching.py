"""Customer matching service."""

from __future__ import annotations

import logging
from typing import Optional

from cheqi.exceptions import CheqiApiError, ErrorCodes
from cheqi.http.client import CheqiApiClient
from cheqi.models.matching import IdentificationDetails, RecipientResolutionResponse

logger = logging.getLogger("cheqi.matching")


class MatchingService:
    """Service for secure customer matching using payment details."""

    def __init__(self, api_client: CheqiApiClient) -> None:
        self._api_client = api_client

    def match_customer(
        self,
        identification_details: IdentificationDetails,
        access_token: Optional[str] = None,
    ) -> RecipientResolutionResponse:
        """Match a customer using the provided identification details.

        A customer locator may be supplied through a pairing code, card details,
        payment account details, email, or Cheqi receipt ID. A payment type by
        itself is also valid and represents the anonymous download-fallback case.
        """
        if not self._has_valid_identifiers(identification_details):
            raise ValueError(
                "IdentificationDetails must contain a customer identifier or payment type "
                "(card details, payment account details, email, pairing code, Cheqi receipt ID, "
                "or payment type for anonymous fallback)"
            )

        self._log_available_identifiers(identification_details)

        try:
            response = self._api_client.match_customer(identification_details, access_token)

            if response.customer_found:
                count = len(response.recipients) if response.recipients else 0
                logger.info("Customer matched successfully: %d recipients found", count)
            else:
                logger.info("No customer match found")

            return response
        except CheqiApiError:
            raise
        except Exception as e:
            logger.error("Unexpected error during customer matching: %s", e)
            raise CheqiApiError(
                f"Customer matching failed: {e}",
                error_code=ErrorCodes.UNKNOWN_ERROR,
            ) from e

    def _has_valid_identifiers(self, details: IdentificationDetails) -> bool:
        if details is None:
            return False
        return bool(
            self._has_card_details(details)
            or self._has_payment_account(details)
            or self._has_email(details)
            or self._has_pairing_code(details)
            or self._has_cheqi_receipt_id(details)
            or details.payment_type is not None
        )

    def _has_card_details(self, details: IdentificationDetails) -> bool:
        if not details.card_details:
            return False
        card = details.card_details
        return bool(card.payment_account_number or card.payment_account_reference)

    def _has_payment_account(self, details: IdentificationDetails) -> bool:
        if not details.payment_account_details:
            return False
        return bool(details.payment_account_details.identifier)

    def _has_email(self, details: IdentificationDetails) -> bool:
        return bool(details.recipient_email and details.recipient_email.strip())

    def _has_pairing_code(self, details: IdentificationDetails) -> bool:
        return bool(details.pairing_code and details.pairing_code.strip())

    def _has_cheqi_receipt_id(self, details: IdentificationDetails) -> bool:
        return bool(details.cheqi_receipt_id and details.cheqi_receipt_id.strip())

    def _log_available_identifiers(self, details: IdentificationDetails) -> None:
        ids = []
        if self._has_card_details(details):
            ids.append("Card")
        if self._has_payment_account(details):
            ids.append("PaymentAccount")
        if self._has_email(details):
            ids.append("Email")
        if self._has_cheqi_receipt_id(details):
            ids.append("CheqiReceiptId")
        if self._has_pairing_code(details):
            ids.append("PairingCode")
        if details.payment_type is not None:
            ids.append("PaymentType")
        logger.debug("Available identifiers: %s", ", ".join(ids))
