"""Refreshes the data of the Airport-Finder (network, no token needed).

    cd domain-services/services/flight-service/src
    python3 -m airport_finder.update_data

* airports.csv   <- https://davidmegginson.github.io/ourairports-data/airports.csv (public domain)
* timezones.json <- https://api.travelpayouts.com/data/en/airports.json (IATA -> time zone)
"""

from __future__ import annotations

import json
import urllib.request

from .finder import AIRPORTS_CSV, TIMEZONES_JSON

OURAIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
TRAVELPAYOUTS_AIRPORTS_URL = "https://api.travelpayouts.com/data/en/airports.json"


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - fixed https URLs
        return response.read()


def main() -> None:
    AIRPORTS_CSV.write_bytes(_download(OURAIRPORTS_URL))
    airports = json.loads(_download(TRAVELPAYOUTS_AIRPORTS_URL))
    zones = {
        a["code"]: a["time_zone"]
        for a in airports
        if a.get("iata_type") == "airport" and a.get("code") and a.get("time_zone")
    }
    TIMEZONES_JSON.write_text(json.dumps(dict(sorted(zones.items())), separators=(",", ":")), encoding="utf-8")
    print(f"airports.csv updated, {len(zones)} time zones")


if __name__ == "__main__":
    main()
