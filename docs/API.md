# API-Referenz

Alle vorhandenen Endpunkte des Backends mit Parametern, Validierung, Beispielen und Fehlerfällen. Regeln, die für alle Endpunkte gelten, stehen in den [API-Konventionen](API_CONVENTIONS.md). Dazu gehören das Fehlerformat, die Seitenaufteilung von Listen, Datumsformate und Geldbeträge.

Basis-URLs in der lokalen Entwicklung:
- `http://localhost:8000/api/v1/` (Backend direkt)
- `http://localhost:3000/api/v1/` (über den Proxy des Frontends)

| Methode | Pfad | Zweck |
| --- | --- | --- |
| `GET` | [`/api/v1/health/`](#get-apiv1health) | Backend und Datenbank prüfen |
| `POST` | [`/api/v1/planning-sessions/`](#post-apiv1planning-sessions) | Planungssitzung anlegen |
| `GET` | [`/api/v1/planning-sessions/{id}/`](#get-apiv1planning-sessionsid) | Planungssitzung abrufen |
| `GET` | [`/api/v1/reference-cases/`](#get-apiv1reference-cases) | historische Benchmark-Fälle auflisten |
| `GET` | [`/api/v1/reference-cases/{id}/`](#get-apiv1reference-casesid) | einzelnen Benchmark-Fall mit Referenzinformationen abrufen |

Alle Endpunkte beantworten zusätzlich `OPTIONS`, die `GET`-Endpunkte für Sessions und Referenzfälle auch `HEAD`. Das kommt von Django REST Framework und ist nicht Teil des Vertrags. Andere Methoden ergeben `405`.

**Geplant** und noch nicht vorhanden:
- `POST/GET /api/v1/planning-sessions/{id}/messages/` für den Chat mit dem Main-Agent (AG08 #37)
- ein Reise-State pro Planungssitzung (AG03 #32)

Der Journey Planner wird ein eigener interner Service und gehört nicht zu dieser API (JP01 #38).

---

## `GET /api/v1/health/`

Prüft, ob das Backend läuft und PostgreSQL erreicht. Docker Compose und die Statusseite nutzen diesen Endpunkt.

**Parameter:** keine.

```sh
curl http://localhost:8000/api/v1/health/
```

`200 OK`

```json
{"status": "ok", "database": "ok"}
```

**Fehlerfälle**

| Fall | Status | Antwort |
| --- | --- | --- |
| Datenbank nicht erreichbar | `503` | `{"error": {"code": "service_unavailable", "message": "The database is not reachable."}}` |

---

## `POST /api/v1/planning-sessions/`

Legt eine Planungssitzung an. Sie ist der Anker für spätere Reisedaten und den Chat.

**Body** (`Content-Type: application/json`)

| Feld | Typ | Pflicht | Validierung |
| --- | --- | --- | --- |
| `title` | String | ja | wird am Rand von Leerzeichen befreit, danach 1–200 Zeichen |

`id` und `created_at` vergibt der Server, gesendete Werte dafür werden ignoriert. Unbekannte Felder werden ebenfalls ignoriert.

```sh
curl -X POST http://localhost:8000/api/v1/planning-sessions/ \
  -H 'Content-Type: application/json' -d '{"title": "Wochenende in Leipzig"}'
```

`201 Created`

```json
{"id": "d848ece2-0ccb-42a5-a799-41b7bf93b40e", "title": "Wochenende in Leipzig", "created_at": "2026-11-10T12:12:15.800785Z"}
```

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `id` | String (UUID) | Kennung der Sitzung |
| `title` | String | Titel |
| `created_at` | String (ISO 8601, UTC) | Zeitpunkt der Anlage |

**Fehlerfälle**

| Fall | Status | Antwort |
| --- | --- | --- |
| `title` fehlt | `400` | `{"error": {"code": "validation_error", "message": "The input is invalid.", "fields": {"title": ["This field is required."]}}}` |
| `title` leer oder nur Leerzeichen | `400` | `… "fields": {"title": ["This field may not be blank."]}` |
| `title` länger als 200 Zeichen | `400` | `… "fields": {"title": ["Ensure this field has no more than 200 characters."]}` |
| `title` kein String oder `null` | `400` | `… "fields": {"title": ["Not a valid string."]}` bzw. `["This field may not be null."]` |
| Body ist eine Liste statt eines Objekts | `400` | `… "fields": {"non_field_errors": ["Invalid data. Expected a dictionary, but got list."]}` |
| kein gültiges JSON | `400` | `{"error": {"code": "parse_error", "message": "JSON parse error - Expecting value: line 1 column 10 (char 9)"}}` |
| anderer `Content-Type` als JSON | `415` | `{"error": {"code": "unsupported_media_type", "message": "Unsupported media type \"text/plain\" in request."}}` |
| `GET` auf diesen Pfad (keine Liste vorgesehen) | `405` | `{"error": {"code": "method_not_allowed", "message": "Method \"GET\" not allowed."}}`, Header `Allow: POST, OPTIONS` |
| Datenbank nicht erreichbar | `503` | `{"error": {"code": "service_unavailable", "message": "The service is temporarily unavailable."}}` |

---

## `GET /api/v1/planning-sessions/{id}/`

Liefert eine vorhandene Planungssitzung.

**Pfadparameter:** `id` ist die UUID der Sitzung.

```sh
curl http://localhost:8000/api/v1/planning-sessions/d848ece2-0ccb-42a5-a799-41b7bf93b40e/
```

`200 OK`: dieselben Felder wie beim Anlegen.

```json
{"id": "d848ece2-0ccb-42a5-a799-41b7bf93b40e", "title": "Wochenende in Leipzig", "created_at": "2026-11-10T12:12:15.800785Z"}
```

**Fehlerfälle**

| Fall | Status | Antwort |
| --- | --- | --- |
| unbekannte UUID oder keine gültige UUID | `404` | `{"error": {"code": "not_found", "message": "The requested resource was not found."}}` |
| Datenbank nicht erreichbar | `503` | `service_unavailable` wie oben |

---

## `GET /api/v1/reference-cases/`

Listet die historischen TravelPlanner-Benchmark-Fälle auf, nur lesend. Importiert werden sie mit `import_reference_cases`, siehe [DEVELOPMENT.md](DEVELOPMENT.md#referenzdaten-importieren). Die Liste ist seitenweise aufgebaut mit 20 Fällen pro Seite. Die Reihenfolge ist `train`, `validation`, `test`, innerhalb eines Splits nach Zeile der Originaldatei.

**Query-Parameter** (alle optional, kombinierbar)

| Parameter | Werte | Bedeutung |
| --- | --- | --- |
| `split` | `train`, `validation`, `test` | nur dieser Split |
| `level` | `easy`, `medium`, `hard` | nur dieser Schwierigkeitsgrad |
| `days` | Ganzzahl ≥ 1 | nur Reisen mit dieser Anzahl Tage |
| `page` | Ganzzahl ≥ 1 | Seite, Standard 1 |

```sh
curl 'http://localhost:8000/api/v1/reference-cases/?split=train'
```

`200 OK` (gekürzt)

```json
{
  "count": 45,
  "next": "http://localhost:8000/api/v1/reference-cases/?page=2&split=train",
  "previous": null,
  "results": [
    {
      "id": "travelplanner-train-0000",
      "data_kind": "historical_benchmark",
      "dataset": {
        "slug": "travelplanner",
        "name": "TravelPlanner",
        "version": "8736504ecfc31b7f8b7e40122873c337e83fff7c",
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "source_url": "https://huggingface.co/datasets/osunlp/TravelPlanner",
        "homepage_url": "https://osu-nlp-group.github.io/TravelPlanner/",
        "citation": "Jian Xie, Kai Zhang, … (2024): TravelPlanner: A Benchmark for Real-World Planning with Language Agents. arXiv:2402.01622",
        "notice": "Historical benchmark data: trips in 2022 with offers and prices from the benchmark's sandbox database. Not current travel offers."
      },
      "split": "train",
      "level": "easy",
      "query": "Please help me plan a trip from St. Petersburg to Rockford spanning 3 days from March 16th to March 18th, 2022. The travel should be planned for a single person with a budget of $1,700.",
      "org": "St. Petersburg",
      "dest": "Rockford",
      "days": 3,
      "visiting_city_number": 1,
      "date": ["2022-03-16", "2022-03-17", "2022-03-18"],
      "people_number": 1,
      "local_constraint": {"cuisine": null, "room type": null, "house rule": null, "transportation": null},
      "budget": {"amount": 1700, "currency": "USD", "basis": "trip_total"},
      "has_annotated_plan": true
    }
  ]
}
```

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `id` | String | stabile Kennung `travelplanner-<split>-<zeile>` |
| `data_kind` | `"historical_benchmark"` | kennzeichnet die Daten als historische Benchmark-Daten |
| `dataset` | Objekt | Herkunft, Version, Lizenz, Zitat und Hinweis des Datensatzes |
| `split`, `level` | String | siehe Query-Parameter |
| `query` | String | Reiseanfrage in natürlicher Sprache |
| `org`, `dest` | String | Start- und Zielort, Namen wie im Original |
| `days` | Ganzzahl | Reisedauer in Tagen |
| `visiting_city_number` | Ganzzahl oder `null` | Anzahl der besuchten Städte |
| `date` | Liste von Daten (`YYYY-MM-DD`) | Reisetage, genau `days` Einträge |
| `people_number` | Ganzzahl oder `null` | Anzahl der Reisenden |
| `local_constraint` | Objekt oder `null` | harte Vorgaben: `house rule`, `cuisine`, `room type`, `transportation` |
| `budget` | Geldbetrag oder `null` | Budget in USD für die ganze Reise und alle Reisenden |
| `has_annotated_plan` | Boolean | ob ein menschlich annotierter Plan vorliegt (nur `train`) |

Im Split `test` sind `visiting_city_number`, `people_number`, `local_constraint` und `budget` immer `null`, weil sie im Original fehlen.

**Fehlerfälle**

| Fall | Status | Antwort |
| --- | --- | --- |
| ungültiger Filterwert | `400` | `{"error": {"code": "validation_error", "message": "The input is invalid.", "fields": {"level": ["\"extreme\" is not a valid choice."]}}}` |
| `days` kleiner als 1 | `400` | `… "fields": {"days": ["Ensure this value is greater than or equal to 1."]}` |
| Seite existiert nicht | `404` | `{"error": {"code": "not_found", "message": "Invalid page."}}` |
| `POST`, `PUT`, `PATCH`, `DELETE` | `405` | `{"error": {"code": "method_not_allowed", "message": "Method \"POST\" not allowed."}}` |
| Datenbank nicht erreichbar | `503` | `service_unavailable` |

Ist noch nichts importiert, ist die Antwort ein `200` mit `"count": 0` und leeren `results`.

---

## `GET /api/v1/reference-cases/{id}/`

Liefert einen Fall mit allen Feldern der Liste und zusätzlich den beiden großen Feldern.

**Pfadparameter:** `id`, z. B. `travelplanner-train-0000`.

```sh
curl http://localhost:8000/api/v1/reference-cases/travelplanner-train-0000/
```

`200 OK`: Felder wie in der Liste, dazu diese beiden (gekürzt):

```json
{
  "annotated_plan": [
    {"org": "St. Petersburg", "dest": "Rockford", "days": 3, "…": "…"},
    [
      {"days": 1, "current_city": "from St. Petersburg to Rockford", "transportation": "Flight Number: F3573659, from St. Petersburg to Rockford, Departure Time: 15:40, Arrival Time: 17:04", "breakfast": "-", "attraction": "-", "lunch": "-", "dinner": "Coco Bambu, Rockford", "accommodation": "Pure luxury one bdrm + sofa bed on Central Park, Rockford"},
      "…"
    ]
  ],
  "reference_information": [
    {"Description": "Attractions in Rockford", "Content": "Name  Latitude  Longitude  Address  Phone  Website  City\nBurpee Museum of Natural History 42.277324 -89.088142 …"},
    "…"
  ]
}
```

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `annotated_plan` | Liste oder `null` | Plan aus dem Original, unverändert: zuerst die Reiseparameter, dann ein Eintrag pro Tag. Nur im Split `train`. |
| `reference_information` | Liste | Referenzinformationen für den Modus „sole-planning“, unverändert: Einträge mit `Description` und `Content`, wobei `Content` eine Tabelle als Text ist |

**Fehlerfälle**

| Fall | Status | Antwort |
| --- | --- | --- |
| unbekannte Kennung | `404` | `{"error": {"code": "not_found", "message": "The requested resource was not found."}}` |
| `PUT`, `PATCH`, `DELETE` | `405` | `method_not_allowed` |
