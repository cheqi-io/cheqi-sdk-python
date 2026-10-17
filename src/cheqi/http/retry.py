"""Exponential backoff retry handler for HTTP requests."""

from __future__ import annotations

import logging
import random
import time
from typing import Callable, Optional, TypeVar

import httpx

from cheqi.exceptions import CheqiApiError, ErrorCodes

logger = logging.getLogger("cheqi.http.retry")

T = TypeVar("T")

_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_MAX_BACKOFF_MS = 30000
_BASE_DELAY_RATE_LIMITED_MS = 5000
_BASE_DELAY_MS = 1000


class RetryHandler:
    """Handles HTTP request retry logic with exponential backoff and jitter."""

    def __init__(self, max_retries: int = 3) -> None:
        self._max_retries = max_retries

    def execute_with_retry(
        self,
        operation: Callable[[], httpx.Response],
        operation_name: str,
        max_retries: Optional[int] = None,
    ) -> httpx.Response:
        """Execute an HTTP operation with automatic retry for transient failures.

        Retries on: 408, 429, 5xx status codes, and network errors.
        Respects Retry-After header.
        """
        max_retries = self._max_retries if max_retries is None else max_retries
        attempt = 0
        last_exception: Exception | None = None

        while attempt <= max_retries:
            try:
                if attempt > 0:
                    logger.debug("Retry attempt %d for %s", attempt, operation_name)

                response = operation()

                if self._should_retry(response.status_code, attempt, max_retries):
                    retry_after = response.headers.get("Retry-After")
                    delay_ms = self._calculate_backoff(attempt, response.status_code, retry_after)
                    logger.warning(
                        "%s failed with status %d (attempt %d/%d), retrying in %dms",
                        operation_name,
                        response.status_code,
                        attempt + 1,
                        max_retries + 1,
                        delay_ms,
                    )
                    time.sleep(delay_ms / 1000.0)
                    attempt += 1
                    continue

                return response

            except httpx.HTTPError as e:
                attempt += 1
                last_exception = e

                if attempt <= max_retries:
                    delay_ms = self._calculate_backoff(attempt, 0, None)
                    logger.warning(
                        "%s network error (attempt %d/%d), retrying in %dms: %s",
                        operation_name,
                        attempt,
                        max_retries + 1,
                        delay_ms,
                        e,
                    )
                    time.sleep(delay_ms / 1000.0)
                else:
                    logger.error("%s failed after %d attempts", operation_name, attempt)

        if last_exception:
            raise CheqiApiError(
                f"Network error: {last_exception}",
                error_code=ErrorCodes.NETWORK_ERROR,
            ) from last_exception

        raise CheqiApiError(
            f"{operation_name} failed after {max_retries + 1} attempts",
            error_code=ErrorCodes.UNKNOWN_ERROR,
        )

    @staticmethod
    def _should_retry(status_code: int, attempt: int, max_retries: int) -> bool:
        if attempt >= max_retries:
            return False
        return status_code in _RETRYABLE_STATUS_CODES

    def _calculate_backoff(
        self, attempt: int, status_code: int, retry_after: str | None
    ) -> int:
        """Calculate backoff delay in milliseconds."""
        if retry_after:
            try:
                return int(retry_after) * 1000
            except ValueError:
                pass

        base_delay = _BASE_DELAY_RATE_LIMITED_MS if status_code == 429 else _BASE_DELAY_MS
        exponential_delay = base_delay * (2**attempt)
        jitter = 0.75 + random.random() * 0.5  # noqa: S311
        delay_with_jitter = int(exponential_delay * jitter)
        return min(delay_with_jitter, _MAX_BACKOFF_MS)
