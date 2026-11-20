# Train Service

Eigenständiger Transportservice für Bahnverbindungen (`service_id: train`, `mode: train`), [DS2 #23](https://github.com/li-minjian/Traveller/issues/23). Erfüllt den [DS1-Vertrag](../../journey-planner/docs/DS1_CONTRACT.md) und hängt von keinem anderen Service ab.

**Stand:** ein Mock-Adapter `mock-rail`, der für jede Start/Ziel-Kombination **direkte** Zugverbindungen liefert. Ein echter Bahn-Anbieter folgt nach DS3 (#25).

```python
from train_service import create_train_service

service = create_train_service()
result = await service.search_journeys(request)   # DS1 JourneySearchRequest -> JourneySearchResult
```

## Aufbau

| Pfad | Inhalt |
| --- | --- |
| `train_service/service.py` | `TrainService`: fragt alle konfigurierten Adapter parallel ab (Timeout 8 s je Adapter), bildet Fehler auf DS1 ab, wählt den Status. Dazu das interne `ProviderAdapter`-Protocol, die Adapter-Liste `ADAPTERS` und `create_train_service()`. |
| `train_service/errors.py` | Fehlerklassen für Adapter: `ProviderTimeout`, `ProviderRateLimited`, `ProviderUnavailable`, `ProviderAuthenticationFailed`, `InvalidProviderResponse` |
| `train_service/contract.py` | einzige Stelle, die den DS1-Vertrag importiert |
| `train_service/adapters/mock_rail.py` | Mock-Adapter `mock-rail` |
| `train_service/adapters/mock_support.py` | Städte mit Koordinaten, Abfahrtsraster, Fehlersimulation für den Mock |
| `tests/` | Tests dieses Services |

## Provider-Adapter

Ein Adapter erfüllt `ProviderAdapter` (`provider_id`, `async search(request) -> list[Journey]`) und arbeitet in drei Schritten:

1. **Anfrage übersetzen** (`build_query`): Stadt-ID → Bahnhofscode des Anbieters (`berlin` → `mr:berlin`), Alter der Reisenden.
2. **Anbieter aufrufen**: beim Mock `MockRailApi`, die im eigenen Format antwortet (UTC-Zeiten, Cent-Beträge, Produktcodes wie `SPARPREIS`, `bookable`).
3. **Antwort normalisieren** (`parse_response`): Ortszeit mit dem Offset des Requests, `Money` mit `trip_total`, `availability`, Tarifnamen. Unbekanntes bleibt `null`/`unknown`, kaputte oder vertragswidrige Antworten werfen `InvalidProviderResponse`.

Der Service prüft zusätzlich, dass ein Adapter nur Zug-Journeys mit seiner eigenen `provider_id` liefert.

**Echten Anbieter anbinden:** Adapter unter `train_service/adapters/` anlegen, Anbieterfehler in die Klassen aus `errors.py` übersetzen und in `ADAPTERS` eintragen.

## Mock-Daten (`mock-rail`)

- Täglich um 06:00, 09:00, 12:00, 15:00 und 18:00 Uhr eine **direkte** Verbindung, `ICE` ab 150 km, sonst `RE`.
- Dauer: Luftlinie × 1,2 bei 140 km/h plus 15 Minuten.
- Tarife: Sparpreis (etwa jede fünfte Fahrt ausverkauft) und Flexpreis, Preis aus der Entfernung. Unter 6 Jahren frei, unter 15 halber Preis, ohne Alter Erwachsenentarif.
- Ohne `departure_before` gilt ein Fenster von 24 Stunden, es gibt also immer eine Verbindung. `no_results` gibt es nur bei einem engen Zeitfenster ohne Abfahrt oder wenn Start und Ziel dieselbe Stadt sind.
- 12 Städte mit Koordinaten und Bahnhofsnamen. Unbekannte Orts-IDs funktionieren auch (`bad-homburg` → „Bad Homburg Hbf“, pauschal 400 km).
- Deterministisch: dieselbe Abfahrt hat immer dieselbe ID, Zugnummer und denselben Preis.
- Vereinfachung: alle Zeiten verwenden den Offset aus `departure_after`, auch am Ziel.

## Konfiguration

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `TRAIN_SERVICE_PROVIDERS` | `mock-rail` | Adapter, kommagetrennt. Unbekannte Namen führen beim Start zu einem Fehler. |

Fehler und langsame Anbieter simulieren:

```python
create_train_service(adapter_options={"mock-rail": {"failure": ErrorCode.RATE_LIMITED}})
create_train_service(adapter_options={"mock-rail": {"delay_seconds": 12}})
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
cd domain-services/train-service
python3 -m unittest -v
```

Kein Netz, keine Zugangsdaten, nur Standardbibliothek (Python ≥ 3.12). Der DS1-Vertrag aus `journey-planner/` wird automatisch gefunden.
