"""Exception hierarchy for the Cheqi SDK."""

from __future__ import annotations

import time
from typing import Optional


class ErrorCodes:
    """Standard error codes used across the SDK."""

    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    INVALID_ACCESS_TOKEN = "INVALID_ACCESS_TOKEN"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    RECEIPT_NOT_FOUND = "RECEIPT_NOT_FOUND"
    ENCRYPTION_ERROR = "ENCRYPTION_ERROR"
    DECRYPTION_ERROR = "DECRYPTION_ERROR"
    KEY_GENERATION_ERROR = "KEY_GENERATION_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"
    SERVER_ERROR = "SERVER_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    SUBMISSION_IN_PROGRESS = "SUBMISSION_IN_PROGRESS"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    RECEIPT_GENERATION_ERROR = "RECEIPT_GENERATION_ERROR"
    TEMPLATE_GENERATION_FAILED = "TEMPLATE_GENERATION_FAILED"
    TEMPLATE_PROCESSING_ERROR = "TEMPLATE_PROCESSING_ERROR"
    NULL_TEMPLATE = "NULL_TEMPLATE"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_FIELD_VALUE = "INVALID_FIELD_VALUE"
    INVALID_CURRENCY_CODE = "INVALID_CURRENCY_CODE"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    INVALID_DATE_FORMAT = "INVALID_DATE_FORMAT"


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

    @property
    def has_http_status_code(self) -> bool:
        return self.http_status_code > 0

    @property
    def has_correlation_id(self) -> bool:
        return bool(self.correlation_id and self.correlation_id.strip())

    @property
    def is_client_error(self) -> bool:
        return 400 <= self.http_status_code < 500

    @property
    def is_server_error(self) -> bool:
        return 500 <= self.http_status_code < 600

    @property
    def is_authentication_error(self) -> bool:
        return self.error_code in {
            ErrorCodes.AUTHENTICATION_FAILED,
            ErrorCodes.INVALID_ACCESS_TOKEN,
        }

    @property
    def is_authorization_error(self) -> bool:
        return self.error_code in {
            ErrorCodes.AUTHORIZATION_FAILED,
            ErrorCodes.INSUFFICIENT_PERMISSIONS,
        }

    @property
    def is_validation_error(self) -> bool:
        return self.error_code in {
            ErrorCodes.VALIDATION_ERROR,
            ErrorCodes.INVALID_REQUEST,
        }

    @property
    def is_network_error(self) -> bool:
        return self.error_code in {ErrorCodes.NETWORK_ERROR, ErrorCodes.TIMEOUT_ERROR}


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
        self.timestamp = time.time_ns() // 1_000_000

    @property
    def is_retryable(self) -> bool:
        """Whether this error can be retried."""
        return self.http_status_code in (408, 429) or 500 <= self.http_status_code < 600

    @property
    def is_rate_limit_error(self) -> bool:
        return self.http_status_code == 429


class SubmissionInProgressError(CheqiApiError):
    """The submission is processing; the caller controls when to recover it."""

    def __init__(self, retry_after_seconds: int = 2) -> None:
        super().__init__("Receipt submission is in progress", ErrorCodes.SUBMISSION_IN_PROGRESS, 202)
        self.retry_after_seconds = retry_after_seconds

    @property
    def is_retryable(self) -> bool:
        return True


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
