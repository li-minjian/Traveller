# Journey Planner

Der Journey Planner nimmt Suchaufträge an, fragt die Transportservices ab und wählt passende Reisevarianten aus.

----> Bisher dient dieser Ordner lediglich dazu ein einheitliches Format für eine Journey Request an die Domain Services festzulegen!

```python
from domain_services import JourneySearchRequest, search_all
from domain_services.mocks import mock_flight_service, mock_taxi_service, mock_train_service

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

Der Vertrag, alle Regeln und Status- und Fehlerfälle: **[docs/DS1_CONTRACT.md](docs/DS1_CONTRACT.md)**.

## Aufbau

| Pfad                              | Inhalt                                                                                                                                          |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `domain_services/contract.py`     | Request (Reisende mit optionalem Alter, optionale Koordinaten), Response (`Journey`/`Leg`/`Offer`), Status, Fehler, `TransportService`-Protocol |
| `domain_services/gateway.py`      | generischer Aufrufer mit Timeout, parallel über alle Services                                                                                   |
| `domain_services/http_binding.py` | Abbildung auf HTTP/JSON                                                                                                                         |
| `domain_services/mocks.py`        | Mock-Services `flight`, `train` und `taxi`                                                                                                      |
| `openapi.yaml`                    | Vertrag als OpenAPI 3.1                                                                                                                         |
| `examples/`                       | Beispiel-JSON für Request, alle Status und den Validierungsfehler                                                                               |
| `tests/`                          | Tests für Vertrag, Aufrufer, Mocks und HTTP-Abbildung                                                                                           |

Nur Python-Standardbibliothek, Python ≥ 3.12 (Projektstandard 3.14).

## Tests

```sh
cd journey-planner
python3 -m unittest -v
```

Die Tests brauchen kein Netz und keine Zugangsdaten. Sind `jsonschema` und `pyyaml` installiert, prüft ein zusätzlicher Test die Beispiele gegen `openapi.yaml`; sonst wird er übersprungen.

Ändert sich die Ausgabe der Mocks, müssen die Dateien in `examples/` angepasst werden. `test_examples_match_mock_output` schlägt sonst fehl.

## Noch nicht enthalten

Der Journey-Planner-Service selbst (JP01), seine Docker-Compose-Einbindung (IN02) und echte Transportservices (DS2, DS6) sind **geplant**.
