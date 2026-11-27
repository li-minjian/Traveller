# Flight Service

Der Flight Service setzt den Vertrag aus [`contract/openapi.yaml`](../../contract/openapi.yaml) für Flüge um (`service_id: flight`). Er findet zu einer Geolocation die umliegenden Flughäfen und fragt über Adapter externe Flug-APIs ab. Er läuft als eigenständiger Docker-Service.

## Aufbau

```text
POST /api/v1/journey-searches/
   │
   ▼
Flight Request  ──►  Airport-Finder  ──►  Adapter (Travelpayouts)  ──►  Response
```

**Flight Request** (`src/flight_request/`)
Nimmt die Anfrage an und prüft sie. Er reicht Start- und Zielpunkt an den Airport-Finder weiter, verteilt die Suche auf alle Flughafenpaare und Adapter und baut daraus die Antwort. Findet kein Adapter einen Flug, ist das Ergebnis `no_results`.

**Airport-Finder** (`src/airport_finder/`)
Sucht Flughäfen im Umkreis von 30 km um einen Punkt. Findet er keinen, erweitert er den Radius in 10-km-Schritten. Er nimmt höchstens 3 Flughäfen je Seite, die nächsten zuerst. Geschlossene Flughäfen, Flugplätze ohne Linienverkehr und Heliports werden ignoriert. Die Daten kommen aus `airports.csv` (OurAirports) und `timezones.json`.

**Adapter** (`src/adapters/`)
Sprechen eine externe API an und wandeln die Antwort in das Format des Vertrags um. Scheitert ein Aufruf, meldet der Adapter einen Fehler, und der Flight Service gibt ihn als `partial` oder `unavailable` weiter. Bisher gibt es einen Adapter, `travelpayouts`.

## Starten und testen

```sh
cd domain-services/services/flight-service
docker build -t flight-service .
docker run -d --name flight-service -p 8101:8000 --env-file ../../../.env flight-service

curl -s localhost:8101/health
curl -s -X POST localhost:8101/api/v1/journey-searches/ -H 'Content-Type: application/json' -d '{
  "origin_id": "berlin", "destination_id": "london",
  "origin_coordinates": {"latitude": 52.52, "longitude": 13.405},
  "destination_coordinates": {"latitude": 51.5072, "longitude": -0.1276},
  "departure_after": "2026-12-03T00:00:00+01:00"
}'

docker rm -f flight-service
```

Im Browser zeigt http://localhost:8101/docs eine Testseite für die API.

## Request und Response

- Wie in [`openapi.yaml`](../../contract/openapi.yaml), aber **`origin_coordinates` und `destination_coordinates` sind Pflicht**, denn um diese Punkte wird nach Flughäfen gesucht. Fehlen sie, antwortet der Service mit `400` (`validation_error`).
- Jeder Flug enthält den Flughafen mit IATA-Code, Namen und Koordinaten (`origin`/`destination` im Leg).

| `status` | Bedeutung |
| --- | --- |
| `success` | Flüge gefunden |
| `no_results` | alle Abfragen erfolgreich, aber kein Flug |
| `partial` | ein Teil der Flughafenpaare ist gescheitert. Pro Paar steht ein Fehler in `errors`, z. B. `BER-LCY: Travelpayouts rate limit reached.` |
| `unavailable` | alle Abfragen sind gescheitert |

Fehlercodes: `authentication_failed` (Token ungültig), `rate_limited`, `provider_unavailable`, `timeout` (nach 8 s), `invalid_provider_response`, `internal_error`.

## Travelpayouts

- Abfrage: `prices_for_dates` der Aviasales Data API, je Flughafenpaar einmal pro Monat. Danach filtert der Adapter auf das Zeitfenster. Ohne `departure_before` gilt ein Fenster von 24 Stunden.
- **Nur Direktflüge.** Bei Umstiegen liefert die API keine Umsteigeflughäfen.
- **Nur zwischengespeicherte Preise** pro Person, keine Live-Angebote. Die Angebote sind deshalb `is_price_estimate: true` und `availability: unknown`. An manchen Tagen gibt es keine Daten.

## Konfiguration

Nur der Token ist Pflicht, alles andere hat Standardwerte. Leere Werte gelten als nicht gesetzt.

| Variable | Standard |
| --- | --- |
| `TRAVELPAYOUTS_API_TOKEN` | – (Pflicht) |
| `TRAVELPAYOUTS_CURRENCY` | `EUR` |
| `TRAVELPAYOUTS_MARKER` | – (Partner-Marker für Buchungslinks) |
| `FLIGHT_SEARCH_RADIUS_KM` | `30` |
| `FLIGHT_SEARCH_RADIUS_STEP_KM` | `10` |
| `FLIGHT_MAX_AIRPORTS` | `3` je Seite |

## Entwicklung

```sh
python3 -m unittest -v                          # Tests, ohne Netz und ohne Token
cd src && python3 -m airport_finder.update_data # Flughafendaten neu laden
```

Die Tests nutzen eine aufgezeichnete Travelpayouts-Antwort aus `tests/fixtures/`. Mit `jsonschema` und `pyyaml` prüfen sie die Antworten zusätzlich gegen `contract/openapi.yaml`. Die Tests der HTTP-Schicht laufen nur mit `fastapi` und `httpx`.

Einen neuen Adapter legst du unter `src/adapters/<name>/` an. Er erfüllt `FlightAdapter` aus `src/adapters/base.py` und wird in `src/main.py` eingetragen.
