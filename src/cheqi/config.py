"""SDK configuration and environment definitions."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger("cheqi.config")


class Environment(str, Enum):
    """Predefined Cheqi API environments."""

    SANDBOX = "https://sandbox.api.cheqi.io"
    PRODUCTION = "https://api.cheqi.io"

    @property
    def base_url(self) -> str:
        return self.value


class CheqiSDKConfig:
    """Immutable SDK configuration.

    Authentication via API key: Bearer token (starts with sk_live_ or sk_test_).
    """

    def __init__(
        self,
        *,
        environment: Optional[Environment] = None,
        custom_api_endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        private_key: Optional[str] = None,
        timeout_seconds: int = 30,
        max_retries: int = 3,
    ) -> None:
        # Resolve API endpoint
        if custom_api_endpoint:
            self._api_endpoint = custom_api_endpoint
        elif environment:
            self._api_endpoint = environment.base_url
        else:
            raise ValueError("Either 'environment' or 'custom_api_endpoint' must be provided")

        self._api_key = api_key
        self._private_key = private_key

        if timeout_seconds <= 0:
            raise ValueError(f"Timeout must be positive, got: {timeout_seconds}")
        self._timeout_seconds = timeout_seconds

        if max_retries < 0:
            raise ValueError(f"Max retries cannot be negative, got: {max_retries}")
        self._max_retries = max_retries

        # Warn if no auth configured
        has_api_key = bool(api_key and api_key.strip())

        if not has_api_key:
            logger.warning("No authentication configured. API calls will fail unless access tokens are provided.")

        if has_api_key and not self._is_valid_api_key_format(api_key):  # type: ignore[arg-type]
            logger.warning("API key does not match expected format (sk_live_* or sk_test_*)")

    @staticmethod
    def _is_valid_api_key_format(key: str) -> bool:
        return key.startswith("sk_live_") or key.startswith("sk_test_")

    @property
    def api_endpoint(self) -> str:
        return self._api_endpoint

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
