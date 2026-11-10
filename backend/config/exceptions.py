"""DRF exception handler that turns every error into the uniform error body.

Unexpected exceptions are logged with their traceback but never exposed to
the client, independent of DEBUG.
"""

import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db import OperationalError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler, set_rollback

from config.errors import NOT_FOUND_MESSAGE, error_body

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    # Map Django's own exceptions to their DRF counterparts with generic messages.
    if isinstance(exc, Http404):
        exc = exceptions.NotFound(NOT_FOUND_MESSAGE)
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)

    if response is None:
        set_rollback()
        if isinstance(exc, OperationalError):
            logger.warning("Database unavailable: %s", exc)
            return Response(
                error_body("service_unavailable", "The service is temporarily unavailable."),
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        logger.error("Unhandled API error", exc_info=exc)
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
