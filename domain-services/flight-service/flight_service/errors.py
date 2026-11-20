"""Errors a provider adapter raises. The service maps them to DS1 ``ServiceError``s.

Adapters translate provider-specific failures (HTTP 429, SOAP faults, ...) into
these classes. Nothing provider-specific reaches the Journey Planner.
"""

from __future__ import annotations

from .contract import ErrorCode


class ProviderError(Exception):
    """Base class. ``code`` is the DS1 error code the service reports."""

    code: ErrorCode = ErrorCode.PROVIDER_UNAVAILABLE

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ProviderTimeout(ProviderError):
    code = ErrorCode.TIMEOUT


class ProviderRateLimited(ProviderError):
    code = ErrorCode.RATE_LIMITED


class ProviderUnavailable(ProviderError):
    code = ErrorCode.PROVIDER_UNAVAILABLE


class ProviderAuthenticationFailed(ProviderError):
    code = ErrorCode.AUTHENTICATION_FAILED


class InvalidProviderResponse(ProviderError):
    code = ErrorCode.INVALID_PROVIDER_RESPONSE


ERROR_CLASSES: dict[ErrorCode, type[ProviderError]] = {
    cls.code: cls
    for cls in (
        ProviderTimeout,
        ProviderRateLimited,
        ProviderUnavailable,
        ProviderAuthenticationFailed,
        InvalidProviderResponse,
    )
}
