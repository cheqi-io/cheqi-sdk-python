"""Per-call request options."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from cheqi.exceptions import CheqiSDKError, ErrorCodes


@dataclass(frozen=True)
class RequestOptions:
    """Per-call settings that override the SDK-level configuration for a single API call.

    Pass an OAuth access token here when acting on behalf of a connected company. The SDK
    never stores or refreshes tokens: obtain them with
    ``sdk.oauth_service.request_access_token(...)``, cache them per Grant in your own store,
    and pass the current one on each call. Without an access token the call authenticates
    with the configured API key.

    Example::

        options = RequestOptions.with_access_token(token_store.get(grant_id))
        sdk.receipt_service.issue_receipt(identification, payload, options=options)
    """

    access_token: Optional[str] = field(default=None, repr=False)
    """OAuth access token for this call, or ``None`` to use the configured API key."""
    timeout_seconds: Optional[float] = None
    """Timeout for this call, or ``None`` to use the configured timeout."""
    max_retries: Optional[int] = None
    """Maximum retries for this call, or ``None`` to use the configured value."""

    def __post_init__(self) -> None:
        if self.access_token is not None and not self.access_token.strip():
            raise _invalid("access_token cannot be empty")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise _invalid("timeout_seconds must be positive")
        if self.max_retries is not None and self.max_retries < 0:
            raise _invalid("max_retries cannot be negative")

    @classmethod
    def with_access_token(cls, access_token: str) -> RequestOptions:
        """Options that authenticate this call with the given OAuth access token."""
        return cls(access_token=access_token)

    def __repr__(self) -> str:
        # Never print the token itself.
        token = None if self.access_token is None else "***"
        return (
            f"RequestOptions(access_token={token!r}, timeout_seconds={self.timeout_seconds!r}, "
            f"max_retries={self.max_retries!r})"
        )


DEFAULT_REQUEST_OPTIONS = RequestOptions()


def _invalid(message: str) -> CheqiSDKError:
    return CheqiSDKError(message, error_code=ErrorCodes.VALIDATION_ERROR, http_status_code=400)
