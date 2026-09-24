"""SDK configuration and environment definitions."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

import httpx

logger = logging.getLogger("cheqi.config")


class Environment(str, Enum):
    """Predefined Cheqi API environments."""

    SANDBOX = "https://sandbox.api.cheqi.io"
    TEST = "https://test.api.cheqi.io"
    PRODUCTION = "https://api.cheqi.io"

    @property
    def base_url(self) -> str:
        return self.value

    @property
    def receipt_download_base_url(self) -> str:
        """Customer-facing origin used for encrypted receipt download links."""
        if self is Environment.PRODUCTION:
            return "https://receipt.cheqi.io"
        if self is Environment.TEST:
            return "https://test.receipt.cheqi.io"
        return "https://sandbox.receipt.cheqi.io"


class CheqiSDKConfig:
    """Immutable SDK configuration.

    Authentication via API key: Bearer token.
    """

    def __init__(
        self,
        *,
        environment: Optional[Environment] = None,
        custom_api_endpoint: Optional[str] = None,
        receipt_download_base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        private_key: Optional[str] = None,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        # Resolve API endpoint
        self._environment = environment if not custom_api_endpoint else None
        if custom_api_endpoint:
            self._api_endpoint = custom_api_endpoint
        elif environment:
            self._api_endpoint = environment.base_url
        else:
            raise ValueError("Either 'environment' or 'custom_api_endpoint' must be provided")

        self._api_key = api_key
        self._private_key = private_key
        self._receipt_download_base_url = (
            receipt_download_base_url
            if receipt_download_base_url is not None
            else self._environment.receipt_download_base_url
            if self._environment
            else None
        )

        if timeout_seconds <= 0:
            raise ValueError(f"Timeout must be positive, got: {timeout_seconds}")
        self._timeout_seconds = timeout_seconds

        if max_retries < 0:
            raise ValueError(f"Max retries cannot be negative, got: {max_retries}")
        self._max_retries = max_retries
        self._http_client = http_client

        if timeout_seconds > 300:
            logger.warning("Timeout is very high (%ss). Consider using a lower value", timeout_seconds)

        if max_retries > 10:
            logger.warning("Max retries is very high (%s). Consider using a lower value", max_retries)

        # Warn if no auth configured
        has_api_key = bool(api_key and api_key.strip())

        if not has_api_key:
            logger.warning("No authentication configured. API calls will fail unless access tokens are provided.")

    @property
    def api_endpoint(self) -> str:
        return self._api_endpoint

    @property
    def environment(self) -> Optional[Environment]:
        return self._environment

    @property
    def receipt_download_base_url(self) -> Optional[str]:
        return self._receipt_download_base_url

    @property
    def api_key(self) -> Optional[str]:
        return self._api_key

    @property
    def private_key(self) -> Optional[str]:
        return self._private_key

    @property
    def timeout_seconds(self) -> int:
        return self._timeout_seconds

    @property
    def max_retries(self) -> int:
        return self._max_retries

    @property
    def http_client(self) -> Optional[httpx.Client]:
        """Caller-owned HTTP client, when one was supplied."""
        return self._http_client
