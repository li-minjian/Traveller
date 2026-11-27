# Journey Planner

Der Journey Planner nimmt Suchaufträge an, fragt die Transportservices ab und wählt passende Reisevarianten aus.

Bisher enthält dieser Ordner nur die Anbindung an die Transportservices: eine eigene Umsetzung des DS1-Vertrags als Python-Typen, den generischen Aufrufer und Mock-Services. Verbindlich ist der Vertrag in [`domain-services/contract/openapi.yaml`](../domain-services/contract/openapi.yaml); der Code hier ist nur die Sicht des Journey Planners darauf.

```python
from journey_planner import JourneySearchRequest, search_all
from journey_planner.mocks import mock_flight_service, mock_taxi_service, mock_train_service

request = JourneySearchRequest.from_dict({
    "origin_id": "berlin",
    "destination_id": "munich",
    "departure_after": "2026-12-15T06:00:00+01:00",
    "passengers": [{"age": 34}, {"age": 8}],
})
results = await search_all([mock_flight_service(), mock_train_service(), mock_taxi_service()], request)
for result in results:
    print(result.service_id, result.status, len(result.journeys))
```

Der Vertrag, alle Regeln und Status- und Fehlerfälle: **[domain-services/contract/README.md](../domain-services/contract/README.md)**.

## Aufbau

| Pfad | Inhalt |
| --- | --- |
| `journey_planner/contract.py` | DS1-Vertrag als Python-Typen (Request, `Journey`/`Leg`/`Offer`, Status, Fehler, `TransportService`-Protocol); prüft alle Regeln aus `openapi.yaml` und der Vertrags-README beim Anlegen |
| `journey_planner/http_binding.py` | HTTP-Statuscodes ↔ Ergebnis (`200`, `400`, `429`, `5xx`, keine Antwort) |
| `journey_planner/gateway.py` | generischer Aufrufer `search_one` / `search_all` mit Timeout, parallel über alle Services; macht aus Hängen, Exceptions und vertragswidrigen Antworten `unavailable` |
| `journey_planner/mocks.py` | Mock-Services `flight`, `train` und `taxi` |
| `tests/` | Tests für Typen, HTTP-Abbildung, Aufrufer und Mocks; prüfen auch die Beispiele aus `domain-services/contract/examples/` |

## Mocks

| Service | Anbieter | Strecken (täglich) | zeigt |
| --- | --- | --- | --- |
| `flight` | `mock-airline`, `mock-charter` | Berlin → München (3 Flüge), Berlin → Paris (direkt und über Frankfurt) | unbekannter Preis, ausverkaufter Tarif, Umstieg |
| `train` | `mock-rail` | Berlin → München (2 Züge), Berlin → Paris über Köln | `offers: null`, `offers: []`, Preisschätzung, Umstieg |
| `taxi` | `mock-taxi` (Festpreis-Schätzung), `mock-ride` (Preisspanne, wie Uber) | beliebige Punkte in Berlin, Potsdam, München, Köln, Frankfurt, Paris; bis 150 km | Koordinaten, `is_on_demand`, `price_upper`, Fahrzeugklassen nach Gruppengröße |

Altersabhängige Tarife: Bahn – unter 6 Jahren frei, unter 15 halber Preis; Flug – unter 2 Jahren 10 %, unter 12 Jahren 75 %. Ohne Alter gilt der Erwachsenentarif. Mit `unavailable_providers=[...]` und `delay_seconds=...` lassen sich Ausfälle (`partial`, `unavailable`) und Timeouts simulieren.

Nur Python-Standardbibliothek, Python ≥ 3.12 (Projektstandard 3.14).

## Tests

```sh
cd journey-planner
python3 -m unittest -v
```

Die Tests brauchen kein Netz und keine Zugangsdaten. Sind `jsonschema` und `pyyaml` installiert, prüft ein zusätzlicher Test die Beispiele gegen `openapi.yaml`; sonst wird er übersprungen. `domain-services/contract/examples/result-success.json` ist echte Ausgabe des Flug-Mocks: Ändert sich der Mock, schlägt `test_examples_match_mock_output` fehl.

## Noch nicht enthalten

Der Journey-Planner-Service selbst (JP01), seine Docker-Compose-Einbindung (IN02) und echte Transportservices (DS2, DS6) sind **geplant**.
