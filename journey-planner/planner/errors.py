"""Uniform error body, the same shape as in the backend (docs/API_CONVENTIONS.md §4)."""

import logging

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def error_body(code: str, message: str, fields: dict | None = None) -> dict:
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return {"error": error}


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        logger.error("Unhandled planner error", exc_info=exc)
        return Response(
            error_body("internal_error", "An unexpected error occurred."),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if isinstance(exc, exceptions.ValidationError):
        detail = exc.detail
        fields = detail if isinstance(detail, dict) else {"non_field_errors": detail}
        response.data = error_body("validation_error", "The input is invalid.", fields)
    else:
        response.data = error_body(exc.default_code, str(exc.detail))
    return response
