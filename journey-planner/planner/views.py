from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from planner.contract import SearchRequestSerializer
from planner.errors import error_body
from planner.providers import get_providers
from planner.service import plan


def health(request):
    return JsonResponse({"status": "ok"})


def places(request):
    """GET /places – every place the providers serve, by country and name."""
    if request.method != "GET":
        return JsonResponse(
            error_body("method_not_allowed", f'Method "{request.method}" not allowed.'), status=405
        )
    found: dict[str, dict] = {}
    for provider in get_providers():
        listing = getattr(provider, "places", None)
        for place in listing() if callable(listing) else []:
            known = found.setdefault(place["name"], {**place, "aliases": []})
            known["aliases"] = sorted({*known["aliases"], *place["aliases"]})
    ordered = sorted(found.values(), key=lambda place: (place["country"], place["name"]))
    return JsonResponse({"places": ordered}, json_dumps_params={"ensure_ascii": False})


class PlanView(APIView):
    """POST /plan – see docs/SEARCH_CONTRACT.md"""

    def post(self, request):
        serializer = SearchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(plan(serializer.validated_data, get_providers()))


def not_found(request, exception=None):
    return JsonResponse(
        error_body("not_found", "The requested resource was not found."), status=404
    )


def server_error(request):
    return JsonResponse(error_body("internal_error", "An unexpected error occurred."), status=500)
