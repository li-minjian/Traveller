# Flight Service

Eigenständiger Transportservice für Flugverbindungen (`service_id: flight`, `mode: flight`), [DS2 #23](https://github.com/li-minjian/Traveller/issues/23). Erfüllt den [DS1-Vertrag](../../journey-planner/docs/DS1_CONTRACT.md) und hängt von keinem anderen Service ab.

**Stand:** ein Mock-Adapter `mock-air`, der für jede Start/Ziel-Kombination **direkte** Flüge liefert. Ein echter Flug-Anbieter folgt nach DS3 (#25).

```python
from flight_service import create_flight_service

service = create_flight_service()
result = await service.search_journeys(request)   # DS1 JourneySearchRequest -> JourneySearchResult
```

## Aufbau

| Pfad | Inhalt |
| --- | --- |
| `flight_service/service.py` | `FlightService`: fragt alle konfigurierten Adapter parallel ab (Timeout 8 s je Adapter), bildet Fehler auf DS1 ab, wählt den Status. Dazu das interne `ProviderAdapter`-Protocol, die Adapter-Liste `ADAPTERS` und `create_flight_service()`. |
| `flight_service/errors.py` | Fehlerklassen für Adapter: `ProviderTimeout`, `ProviderRateLimited`, `ProviderUnavailable`, `ProviderAuthenticationFailed`, `InvalidProviderResponse` |
| `flight_service/contract.py` | einzige Stelle, die den DS1-Vertrag importiert |
| `flight_service/adapters/mock_air.py` | Mock-Adapter `mock-air` |
| `flight_service/adapters/mock_support.py` | Städte mit Koordinaten, Abflugraster, Fehlersimulation für den Mock |
| `tests/` | Tests dieses Services |

## Provider-Adapter

Ein Adapter erfüllt `ProviderAdapter` (`provider_id`, `async search(request) -> list[Journey]`) und arbeitet in drei Schritten:

1. **Anfrage übersetzen** (`build_query`): Stadt-ID → IATA-Code (`berlin` → `BER`; ohne bekannten Flughafen `city:<id>`), Alter → Passagiertypen `ADT`/`CHD`/`INF`.
2. **Anbieter aufrufen**: beim Mock `MockAirApi`, die im eigenen Format antwortet (UTC-Zeiten, Preise als Strings, Tariffamilien wie `LIGHT`, freie Sitzplätze).
3. **Antwort normalisieren** (`parse_response`): Ortszeit mit dem Offset des Requests, `Money` mit `trip_total`, `availability` aus der Sitzplatzzahl, Tarifnamen, IATA-Code im `Stop`. Unbekanntes bleibt `null`/`unknown`, kaputte oder vertragswidrige Antworten werfen `InvalidProviderResponse`.

Der Service prüft zusätzlich, dass ein Adapter nur Flug-Journeys mit seiner eigenen `provider_id` liefert.

**Echten Anbieter anbinden:** Adapter unter `flight_service/adapters/` anlegen, Anbieterfehler in die Klassen aus `errors.py` übersetzen und in `ADAPTERS` eintragen.

## Mock-Daten (`mock-air`)

- Täglich um 07:00, 13:00 und 19:00 Uhr ein **Direktflug** `MA <Nummer>` der Mock Air.
- Dauer: 40 Minuten plus Luftlinie bei 700 km/h.
- Tarife: Economy Light (an manchen Tagen ausverkauft) und Economy Classic, Preis aus der Entfernung. Unter 2 Jahren 10 %, unter 12 Jahren 75 %, ohne Alter Erwachsenentarif.
- Ohne `departure_before` gilt ein Fenster von 24 Stunden, es gibt also immer eine Verbindung. `no_results` gibt es nur bei einem engen Zeitfenster ohne Abfahrt oder wenn Start und Ziel dieselbe Stadt sind.
- 12 Städte mit Koordinaten, Flughafennamen und IATA-Codes. Unbekannte Orts-IDs funktionieren auch (`bad-homburg` → „Bad Homburg Airport“ ohne IATA-Code, pauschal 400 km).
- Deterministisch: dieselbe Abfahrt hat immer dieselbe ID, Flugnummer und denselben Preis.
- Vereinfachung: alle Zeiten verwenden den Offset aus `departure_after`, auch am Ziel.

## Konfiguration

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `FLIGHT_SERVICE_PROVIDERS` | `mock-air` | Adapter, kommagetrennt. Unbekannte Namen führen beim Start zu einem Fehler. |

Fehler und langsame Anbieter simulieren:

```python
create_flight_service(adapter_options={"mock-air": {"failure": ErrorCode.RATE_LIMITED}})
create_flight_service(adapter_options={"mock-air": {"delay_seconds": 12}})
```

| Adapter-Ergebnis | DS1-Ergebnis |
| --- | --- |
| alle Adapter antworten | `success` oder `no_results` |
| ein Teil fällt aus | `partial`, Fehler mit `provider_id` |
| alle fallen aus | `unavailable` |
| Adapter überschreitet 8 s | `timeout` |
| `ProviderError` | Code der Fehlerklasse, z. B. `rate_limited` |
| kaputte oder vertragswidrige Daten | `invalid_provider_response` |
| unerwartete Exception | `internal_error`, Details nur im Log |

Logs enthalten Service, Anbieter und Fehlercode, aber keine Suchparameter oder Zugangsdaten.

## Tests

```sh
cd domain-services/flight-service
python3 -m unittest -v
```

Kein Netz, keine Zugangsdaten, nur Standardbibliothek (Python ≥ 3.12). Der DS1-Vertrag aus `journey-planner/` wird automatisch gefunden.
