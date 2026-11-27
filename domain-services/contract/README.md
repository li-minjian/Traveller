# Schnittstelle Transportservices

Dieses Dokument legt fest, wie der Journey Planner **jeden** Transportservice (Flug, Bahn, Taxi/Ride-Hailing, später Bus, Fähre) anfragt. Der Journey Planner kennt nur diesen Vertrag, keine Anbieter-APIs. Wie ein Service intern seine Anbieter anbindet kann unterschiedlich sein

```text
Journey Planner
   │  POST /api/v1/journey-searches/   (JourneySearchRequest → JourneySearchResult)
   ▼
flight-service  ──  Provider-Adapter  ──  Flug-APIs
train-service   ──  Provider-Adapter  ──  Bahn-APIs
taxi-service    ──  Provider-Adapter  ──  Taxi-/Uber-APIs
…               (später Bus, Fähre)
```

Der Vertrag besteht nur aus Dokumentation, **es gibt keinen gemeinsamen Code**. Jeder Service setzt ihn in seiner eigenen Sprache und mit eigenem Code um, der Journey Planner ebenso.

| Datei                          | Inhalt                                                                                                                                                                  |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`openapi.yaml`](openapi.yaml) | **verbindliche Beschreibung** der API: Endpunkt, Felder, Typen, Pflichtfelder, Wertebereiche, Statuscodes                                                               |
| `README.md` (dieses Dokument)  | Bedeutung der Felder und Regeln, die sich in OpenAPI nicht ausdrücken lassen (z. B. Reihenfolge der Legs, erlaubte Kombinationen von `status`, `journeys` und `errors`) |
| [`examples/`](examples/)       | Beispiel-Requests und -Responses für alle Status und den Validierungsfehler                                                                                             |

Ein Service kann sich gegen `openapi.yaml` und `examples/` prüfen, z. B. mit einem OpenAPI-Validator oder indem er die Beispiel-Requests beantwortet und die Antworten gegen das Schema validiert.

## 1. Operation

`POST /api/v1/journey-searches/` mit dem Request als JSON-Body. Jeder Transportservice bietet genau diesen Endpunkt an.

**Regeln für Services:**

- Alle erwartbaren Fehler (Timeout beim Anbieter, Rate Limit, Ausfall, kaputte Anbieterantwort) werden **als Ergebnis mit passendem `status`** und HTTP `200` gemeldet, nicht als HTTP-Fehler.
- `service_id` in der Antwort ist die feste ID des Services (`flight`, `train`, …).
- Anbieterspezifische Codes, IDs und Fehlertypen verlassen den Service nicht.

**Regeln für den Aufrufer:** Der Journey Planner setzt pro Service einen Timeout (Standard 10 s), fragt mehrere Services parallel ab und behandelt Zeitüberschreitung, `5xx`, keine Antwort und vertragswidrige Antworten als `unavailable`. Ein defekter Service betrifft nur sein eigenes Ergebnis.

## 2. Request

Berlin → München ([`examples/request.json`](examples/request.json)):

```json
{
  "origin_coordinates": { "latitude": 52.52, "longitude": 13.405 },
  "destination_coordinates": { "latitude": 48.1374, "longitude": 11.5755 },
  "origin_id": "berlin",
  "destination_id": "munich",
  "departure_after": "2026-12-15T06:00:00+01:00",
  "departure_before": "2026-12-15T14:00:00+01:00",
  "passengers": [{ "age": 34 }, { "age": 8 }]
}
```

Taxifahrt innerhalb Berlins, von einer Adresse zum Flughafen ([`examples/request-taxi.json`](examples/request-taxi.json)): Start und Ziel liegen in derselben Stadt, nur die Koordinaten unterscheiden sich.

| Feld                                            | Pflicht | Regel                                                                                                                                                                                                                                                                                             |
| ----------------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `origin_coordinates`, `destination_coordinates` | ja      | Start- und Zielpunkt als `{"latitude", "longitude"}` (WGS 84): Adresse, Hotel oder Stadtmitte. Der Service sucht von hier aus passende Haltestellen (Flughäfen, Bahnhöfe) bzw. fährt hier ab (Taxi). Ortsnamen in Koordinaten umzuwandeln ist Aufgabe des Journey Planners, nicht der Services. |
| `origin_id`, `destination_id`                   | nein    | Optionale Orts-ID auf Stadtebene, kleingeschriebener Slug (`berlin`, `frankfurt-am-main`). Nur zur Beschriftung: Services dürfen sie in `Stop.location_id` zurückgeben, sich aber nicht darauf verlassen. Fehlt sie oder ist sie `null`, ist kein Name bekannt. |
| `departure_after`                               | ja      | Früheste Abfahrt (inklusive). ISO 8601 **mit Offset**, Ortszeit des Startorts. Ohne Offset gibt es einen Validierungsfehler (strenger als API-Konventionen §6, weil Ortszeiten ohne Offset mehrdeutig sind).                                                                                      |
| `departure_before`                              | nein    | Späteste Abfahrt (inklusive), muss nach `departure_after` liegen. Fehlt sie oder ist sie `null`, entscheidet der Service, mindestens bis Ende des Ortstags.                                                                                                                                       |
| `passengers`                                    | nein    | Ein Eintrag pro Reisendem, 1 bis 9 Einträge. Fehlt es, gilt ein Reisender ohne Altersangabe.                                                                                                                                                                                                      |
| `passengers[].age`                              | nein    | Alter in Jahren am Reisetag, 0–120. Fehlt es oder ist es `null`, behandelt der Service die Person wie einen Erwachsenen. Services nutzen bekannte Alter für Tarife (Kind, Kleinkind, Senior); ab welchem Alter welcher Tarif gilt, entscheidet der Service bzw. Anbieter, nicht der Vertrag.      |

Unbekannte Felder werden ignoriert (API-Konventionen §5). Filter wie Budget, maximale Umstiege oder Ranking gehören **nicht** in den Request: das macht der Journey Planner (JP03) auf den Ergebnissen.

## 3. Response

Gekürzt aus [`examples/result-success.json`](examples/result-success.json) (2 Reisende, 34 und 8 Jahre: Kindertarif im Preis enthalten):

```json
{
  "contract_version": "1.0",
  "service_id": "flight",
  "status": "success",
  "journeys": [
    {
      "id": "mock-airline-ma100-2026-12-15",
      "provider_id": "mock-airline",
      "legs": [
        {
          "mode": "flight",
          "origin": {
            "location_id": "berlin",
            "name": "Berlin Brandenburg Airport",
            "code": "BER",
            "coordinates": null
          },
          "destination": {
            "location_id": "munich",
            "name": "Munich Airport",
            "code": "MUC",
            "coordinates": null
          },
          "departure_at": "2026-12-15T07:05:00+01:00",
          "arrival_at": "2026-12-15T08:15:00+01:00",
          "operator": "Mock Air",
          "service_number": "MA 100",
          "is_on_demand": false
        }
      ],
      "offers": [
        {
          "id": "mock-airline-ma100-2026-12-15-0",
          "provider_id": "mock-airline",
          "price": {
            "amount": 155.75,
            "currency": "EUR",
            "basis": "trip_total"
          },
          "price_upper": null,
          "availability": "available",
          "is_price_estimate": false,
          "fare_name": "Economy Light",
          "booking_url": null
        }
      ]
    }
  ],
  "errors": [],
  "retrieved_at": "2026-11-16T09:30:00Z"
}
```

### Datenmodell

```text
JourneySearchResult ─┬─ journeys: Journey[]  ─┬─ legs:   Leg[]   (≥ 1, in Reihenfolge)
                     │                        └─ offers: Offer[] | null
                     └─ errors:   ServiceError[]
```

| Objekt      | Felder                                                                                                       | Regeln                                                                                                                                                                                                                                                                                                                                                                                                   |
| ----------- | ------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Journey** | `id`, `provider_id`, `legs`, `offers`                                                                        | Eine vollständige Verbindung vom Start zum Ziel. **Mehrere Legs** = Umstiege. `id` ist im Ergebnis eindeutig.                                                                                                                                                                                                                                                                                            |
| **Leg**     | `mode`, `origin`, `destination`, `departure_at`, `arrival_at`, `operator`, `service_number`, `is_on_demand`  | Eine Fahrt in einem Fahrzeug. `mode`: `flight`, `train`, `bus`, `ferry`, `taxi`. Zeiten in Ortszeit mit Offset. Jedes Leg fährt nicht vor der Ankunft des vorigen ab. `is_on_demand: true` = kein Fahrplan, das Fahrzeug kommt bei Buchung (Taxi): `departure_at` ist die früheste Abholung, `arrival_at` eine Schätzung.                                                                                |
| **Stop**    | `location_id`, `name`, `code`, `coordinates`                                                                 | `location_id`: Orts-ID aus dem Request (`origin_id`/`destination_id`), falls angegeben, sonst `null`. `name`/`code` für den konkreten Bahnhof oder Flughafen (`BER`), `coordinates` für den genauen Punkt, falls bekannt (bei Taxi immer).                                                                                                                                                                                                                               |
| **Offer**   | `id`, `provider_id`, `price`, `price_upper`, `availability`, `is_price_estimate`, `fare_name`, `booking_url` | Ein Tarif für die ganze Journey, bei Taxi eine Fahrzeugklasse (`Standard`, `XL`). `availability`: `available`, `sold_out`, `unknown`. `is_price_estimate: true` = Preis aus Fahrplan-/Tarifdaten oder Fahrpreisschätzung, kein bestätigtes, buchbares Angebot. `price_upper`: Obergrenze, wenn der Anbieter nur eine Spanne nennt (typisch bei Uber & Co., „23–29 €“); `price` ist dann die Untergrenze. |
| **Money**   | `amount`, `currency`, `basis`                                                                                | Wie API-Konventionen §7. `basis`: `trip_total` (alle Reisenden) oder `per_person`.                                                                                                                                                                                                                                                                                                                       |

Abgeleitete Werte wie Gesamtdauer, Anzahl der Umstiege oder günstigster Preis werden nicht übertragen. Der Aufrufer berechnet sie aus Legs und Offers.

### Taxi und Ride-Hailing

Taxi und Uber-artige Dienste laufen über denselben Vertrag, als Service `taxi` mit `mode: taxi`. Welcher Anbieter (Taxizentrale, Uber, Bolt) eine Fahrt stellt, steht in `provider_id` und `operator`; ein eigener Modus pro Anbieter ist nicht nötig. Besonderheiten:

- Start und Ziel sind `origin_coordinates`/`destination_coordinates`.
- Eine Journey hat ein Leg mit `is_on_demand: true`; die Ankunft ist geschätzt.
- Preise gelten pro Fahrzeug (`basis: trip_total`), sind immer `is_price_estimate: true` und oft eine Spanne (`price`–`price_upper`).
- Angebote gibt es nur für Fahrzeugklassen mit genug Plätzen für alle Reisenden. Passt keine, ist `offers: []`.
- Der Journey Planner kann Taxi-Journeys als Zubringer mit anderen Journeys kombinieren (z. B. Hotel → Flughafen); das ist Aufgabe des Journey Planners, nicht des Services.

### Fehlende Informationen

Jedes dokumentierte Feld ist immer vorhanden (API-Konventionen §5). Fehlendes wird so dargestellt:

| Situation                                                      | Darstellung                          |
| -------------------------------------------------------------- | ------------------------------------ |
| Preis unbekannt                                                | `"price": null`, **nie** `amount: 0` |
| Preis ist keine Spanne                                         | `"price_upper": null`                |
| genauer Punkt unbekannt                                        | `"coordinates": null`                |
| Alter eines Reisenden nicht angegeben (Request)                | `"age": null` oder Feld weglassen    |
| Quelle liefert gar keine Tarife (z. B. nur Fahrplan)           | `"offers": null`                     |
| Bekanntermaßen keine Angebote (z. B. Buchung noch nicht offen) | `"offers": []`                       |
| Verfügbarkeit unbekannt                                        | `"availability": "unknown"`          |
| Name, Code, Betreiber, Nummer, Buchungslink unbekannt          | `null`                               |

## 4. Status- und Fehlerfälle

`status` sagt, wie verlässlich das Ergebnis ist. **Nur `no_results` heißt „es gibt keine Verbindung“.** Alle anderen Status ohne Journeys heißen „wir wissen es nicht“. Vollständig ist ein Ergebnis genau bei `success` und `no_results`.

| `status`          | Bedeutung                                                                  | `journeys`          | `errors`               | HTTP                                            |
| ----------------- | -------------------------------------------------------------------------- | ------------------- | ---------------------- | ----------------------------------------------- |
| `success`         | alle Anbieter haben geantwortet, Treffer vorhanden                         | ≥ 1                 | keine                  | 200                                             |
| `no_results`      | alle Anbieter haben geantwortet, kein Treffer                              | leer                | keine                  | 200                                             |
| `partial`         | mindestens ein Anbieter ist ausgefallen, die anderen haben geantwortet     | beliebig, auch leer | ≥ 1 mit `provider_id`  | 200                                             |
| `unavailable`     | kein Anbieter hat geantwortet oder der Service selbst ist nicht erreichbar | leer                | ≥ 1                    | 200, bzw. 5xx/keine Antwort beim Service selbst |
| `invalid_request` | der Service lehnt die Anfrage ab                                           | leer                | nur `validation_error` | 400 im Fehlerformat der API-Konventionen        |

Andere Kombinationen sind vertragswidrig; der Aufrufer behandelt sie wie eine kaputte Antwort (`unavailable`).

**ServiceError:** `code`, `message`, `provider_id` (welcher Anbieter, sonst `null`), `field` (nur bei `validation_error`), `is_retryable`.

| `code`                      | Wann                                                  | `is_retryable` |
| --------------------------- | ----------------------------------------------------- | -------------- |
| `validation_error`          | Request ungültig, z. B. Koordinaten fehlen            | nein           |
| `timeout`                   | Anbieter oder Service antwortet nicht rechtzeitig     | ja             |
| `rate_limited`              | Anbieter drosselt                                     | ja             |
| `provider_unavailable`      | Anbieter nicht erreichbar oder meldet Ausfall         | ja             |
| `authentication_failed`     | Zugangsdaten des Services beim Anbieter ungültig      | nein           |
| `invalid_provider_response` | Anbieter antwortet, aber unlesbar                     | nein           |
| `internal_error`            | Fehler im Service selbst oder vertragswidrige Antwort | nein           |

Abgrenzung „keine Verbindung“ vs. „ungültig“: Gültige Koordinaten, zwischen denen ein Service keine Verbindung kennt, ergeben `no_results`. Fehlende oder ungültige Koordinaten ergeben `invalid_request`.

**HTTP:** Ein Ausfall eines Anbieters _hinter_ dem Service ist eine normale Antwort (`200` mit `partial`/`unavailable`), weil der Service selbst funktioniert und die Details mitliefern kann. `4xx`/`5xx` bleiben Fehlern des Aufrufs vorbehalten. Der Aufrufer bildet sie so ab: `400` → `invalid_request`, `429` → `rate_limited`, `502/503/504` und keine Antwort → `provider_unavailable`, sonst `internal_error` (jeweils `unavailable`).

Beispiele für alle Fälle liegen in [`examples/`](examples/).

## 5. Versionierung

`contract_version` steht in jeder Antwort. Neue optionale Felder oder neue Enum-Werte, die der Aufrufer ignorieren kann, erhöhen die Nebenversion (`1.1`). Entfernen, Umbenennen oder Bedeutungsänderungen erhöhen die Hauptversion und den Pfad (`/api/v2/`). Der Aufrufer lehnt Antworten mit anderer Hauptversion ab.

## 6. Offene Punkte zur Abstimmung

- **Orts-IDs:** `origin_id`/`destination_id` sind optional und dienen nur der Beschriftung. Ob es dafür eine gemeinsame Liste gibt, ist noch offen; bis dahin gelten die Slugs aus den Beispielen.
- **Timeout-Standard** von 10 s: mit realen Anbietern in DS3/DS4 überprüfen.
- **Abstimmung mit AG04 (#33):** Der Suchauftrag Agent → Journey Planner soll Journey/Leg/Offer aus diesem Vertrag wiederverwenden.

## Nicht Teil dieses Vertrags

Echte Services und Anbieter-Adapter (DS2 #23, DS6 #41), gemeinsame Contract-Tests für alle Services (DS4 #26), Caching (DS5 #27), Kombination von Teilstrecken, Filtern und Ranking (Journey Planner JP02/JP03), Buchung.
