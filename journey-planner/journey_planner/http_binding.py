"""HTTP/JSON binding of the DS1 contract (see ``openapi.yaml``).

    POST /api/v1/journey-searches/      body: JourneySearchRequest JSON

Status code mapping, used by both sides:

* ``200``: the service handled the search. The body is a JourneySearchResult
  with status success, no_results, partial or unavailable. "Provider down" is
  a normal answer of a running service, not an HTTP error.
* ``400``: the request was rejected. The body uses the error format from
  docs/API_CONVENTIONS.md §4 (``validation_error`` with ``fields`` or
  ``parse_error``). The caller turns it into ``invalid_request``.
* anything else / no answer: the service itself is down. The caller turns it
  into ``unavailable``.

The transport itself (requests, httpx, Django view, ...) is not part of DS1;
these functions only translate between HTTP and contract objects.
"""

from __future__ import annotations

from typing import Any

from .contract import (
    ContractValidationError,
    ErrorCode,
    JourneySearchRequest,
    JourneySearchResult,
    SearchStatus,
    ServiceError,
)

SEARCH_PATH = "/api/v1/journey-searches/"


# --- service side ------------------------------------------------------------ #


def parse_request_body(body: Any) -> JourneySearchRequest:
    """Parse the decoded JSON body. Raises ``ContractValidationError`` -> answer with 400."""
    return JourneySearchRequest.from_dict(body)


def validation_error_body(error: ContractValidationError) -> dict[str, Any]:
    return {"error": {"code": "validation_error", "message": "The input is invalid.", "fields": error.fields}}


def result_to_http(result: JourneySearchResult) -> tuple[int, dict[str, Any]]:
    """Status code and JSON body for a result produced by the service."""
    if result.status is SearchStatus.INVALID_REQUEST:
        return 400, {
            "error": {"code": "validation_error", "message": "The input is invalid.", "fields": result.validation_fields()}
        }
    return 200, result.to_dict()


# --- caller side (Journey Planner) ------------------------------------------- #


def result_from_http(service_id: str, status_code: int | None, body: Any) -> JourneySearchResult:
    """Turn an HTTP answer into a result. ``status_code=None``: no answer (connection error).

    Never raises; a broken answer becomes ``unavailable``.
    """
    if status_code == 200:
        try:
            result = JourneySearchResult.from_dict(body)
        except ContractValidationError:
            return _unavailable(service_id, ErrorCode.INTERNAL_ERROR, "The service answered with an invalid result.")
        if result.service_id != service_id:
            return _unavailable(service_id, ErrorCode.INTERNAL_ERROR, "The service answered with a different service_id.")
        return result

    if status_code == 400:
        error = body.get("error") if isinstance(body, dict) else None
        fields = error.get("fields") if isinstance(error, dict) else None
        if isinstance(fields, dict) and fields:
            normalized = {
                str(key): [str(m) for m in (messages if isinstance(messages, list) else [messages])]
                for key, messages in fields.items()
            }
        else:
            message = error.get("message") if isinstance(error, dict) else None
            normalized = {"non_field_errors": [str(message or "The request was rejected.")]}
        return JourneySearchResult.invalid_request(service_id, normalized)

    if status_code is None:
        return _unavailable(service_id, ErrorCode.PROVIDER_UNAVAILABLE, "The service could not be reached.")
    if status_code == 429:
        return _unavailable(service_id, ErrorCode.RATE_LIMITED, "The service is rate limiting requests.")
    if status_code in (502, 503, 504):
        return _unavailable(service_id, ErrorCode.PROVIDER_UNAVAILABLE, f"The service is unavailable ({status_code}).")
    return _unavailable(service_id, ErrorCode.INTERNAL_ERROR, f"Unexpected HTTP status {status_code}.", retryable=False)


def _unavailable(service_id: str, code: ErrorCode, message: str, *, retryable: bool | None = None) -> JourneySearchResult:
    return JourneySearchResult.unavailable(service_id, ServiceError(code=code, message=message, is_retryable=retryable))
