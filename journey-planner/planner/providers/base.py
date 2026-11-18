"""Interface between the planner and whatever delivers connections.

This is the seam for the domain services: the planner only knows this
interface. The dummy provider implements it with fixed flights; the real
Flight Service is added as a provider that translates the search request into
the DS1 request (#21), calls the service over HTTP and maps its answer back.
"""

from typing import Protocol


class ProviderError(Exception):
    """The provider could not answer (unreachable, timeout, invalid answer).

    Never raise this for "nothing found": an empty list means a successful
    search without results.
    """


class TransportProvider(Protocol):
    #: Mode of transport this provider serves, e.g. "flight".
    mode: str
    #: Shown as `offers[].provider`.
    name: str

    def search(self, request: dict) -> list[dict]:
        """Return all connections for the validated search request.

        `request` has the fields of docs/SEARCH_CONTRACT.md; `departure` holds
        `datetime.date` objects. Each result is a dict with `id`, `legs` and
        `offers` in the shape of that document. Filtering by price and stops
        and the ranking are done by the planner, not by the provider.
        """
        ...

    def places(self) -> list[dict]:
        """Optional: the places the provider serves.

        Each entry is {"name": "Lissabon", "country": "Portugal",
        "aliases": ["lisbon", …]}. The planner offers the union of all
        providers at GET /places; the agent and the form use it to check and
        suggest places. A provider without a fixed list leaves this out.
        """
        ...
