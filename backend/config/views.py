import logging

from django.db import DatabaseError, connection
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from config.errors import NOT_FOUND_MESSAGE, error_body

logger = logging.getLogger(__name__)

# Match the compact output of DRF's JSONRenderer.
_COMPACT = {"separators": (",", ":")}


@api_view(["GET"])
def health(request):
    """Report whether the backend is running and can reach the database."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError as exc:
        logger.warning("Health check: database unavailable: %s", exc)
        return Response(
            error_body("service_unavailable", "The database is not reachable."),
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({"status": "ok", "database": "ok"})


def not_found(request, exception=None):
    return JsonResponse(
        error_body("not_found", NOT_FOUND_MESSAGE), status=404, json_dumps_params=_COMPACT
    )


def server_error(request):
    return JsonResponse(
        error_body("internal_error", "An unexpected error occurred."),
        status=500,
        json_dumps_params=_COMPACT,
    )
