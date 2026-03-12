"""Exception hierarchy for the Cheqi SDK."""

from __future__ import annotations

from typing import Optional


class ErrorCodes:
    """Standard error codes used across the SDK."""

    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    RECEIPT_NOT_FOUND = "RECEIPT_NOT_FOUND"
    ENCRYPTION_ERROR = "ENCRYPTION_ERROR"
    DECRYPTION_ERROR = "DECRYPTION_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    SERVER_ERROR = "SERVER_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"


class CheqiSDKError(Exception):
    """Base exception for all Cheqi SDK errors."""

    def __init__(
        self,
        message: str,
        error_code: str = ErrorCodes.UNKNOWN_ERROR,
        http_status_code: int = 0,
        correlation_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.http_status_code = http_status_code
        self.correlation_id = correlation_id


class CheqiApiError(CheqiSDKError):
    """Exception for HTTP/API communication errors."""

    def __init__(
        self,
        message: str,
        error_code: str = ErrorCodes.UNKNOWN_ERROR,
        http_status_code: int = 0,
        correlation_id: Optional[str] = None,
    ) -> None:
        super().__init__(message, error_code, http_status_code, correlation_id)

    @property
    def is_retryable(self) -> bool:
        """Whether this error can be retried."""
        return self.http_status_code in (408, 429) or 500 <= self.http_status_code < 600


class EncryptionError(CheqiSDKError):
    """Exception for encryption failures."""

    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorCodes.ENCRYPTION_ERROR)


class DecryptionError(CheqiSDKError):
    """Exception for decryption failures."""

    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorCodes.DECRYPTION_ERROR)


class ReceiptProcessingError(CheqiSDKError):
    """Exception for receipt processing failures."""

    pass


class CreditNoteProcessingError(CheqiSDKError):
    """Exception for credit note processing failures."""

    pass
