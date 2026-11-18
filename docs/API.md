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
| `GET` | [`/api/v1/places/`](#get-apiv1places) | Orte, für die es Flugdaten gibt (Vorschläge im Formular) |
| `GET` | [`/api/v1/planning-sessions/{id}/trip-state/`](#get-apiv1planning-sessionsidtrip-state) | Reise-State einer Planungssitzung abrufen |
| `POST` | [`/api/v1/planning-sessions/{id}/messages/`](#post-apiv1planning-sessionsidmessages) | Nachricht oder Formularwerte an den Main-Agent senden, Antwort erhalten |
| `GET` | [`/api/v1/planning-sessions/{id}/messages/`](#get-apiv1planning-sessionsidmessages) | Gesprächsverlauf einer Planungssitzung abrufen |
| `GET` | [`/api/v1/reference-cases/`](#get-apiv1reference-cases) | historische Benchmark-Fälle auflisten |
| `GET` | [`/api/v1/reference-cases/{id}/`](#get-apiv1reference-casesid) | einzelnen Benchmark-Fall mit Referenzinformationen abrufen |

Alle Endpunkte beantworten zusätzlich `OPTIONS`, die `GET`-Endpunkte für Sessions, Reise-State, Nachrichten und Referenzfälle auch `HEAD`. Das kommt von Django REST Framework und ist nicht Teil des Vertrags. Andere Methoden ergeben `405`.

Der Journey Planner ist ein eigener interner Service und gehört nicht zu dieser API (JP01 #38). Das Frontend ruft ihn nie direkt auf. Seinen Endpunkt `POST /plan` beschreiben [SEARCH_CONTRACT.md](SEARCH_CONTRACT.md) und die [README des Planners](../journey-planner/README.md).

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

Legt eine Planungssitzung an. Sie ist der Anker für den Reise-State und den Chat.

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

## `GET /api/v1/places/`

Alle Orte, für die der Journey Planner Flugdaten hat. Das Formular nutzt die Liste für Vorschläge bei Start und Ziel; man kann nach Stadt, alternativem Namen oder Land suchen. Das Backend holt die Liste beim Planner (`GET /places`) und hält sie fünf Minuten vor.

**Derzeit:** 30 europäische Städte aus dem Dummy-Provider. Mit echten Verkehrs-Services wächst die Liste; jeder Provider meldet seine Orte über `places()`.

**Parameter:** keine.

```sh
curl http://localhost:8000/api/v1/places/
```

`200 OK`, sortiert nach Land, dann Name, alle Orte auf einer Seite:

```json
{"count": 30, "next": null, "previous": null, "results": [
  {"name": "Berlin", "country": "Deutschland", "aliases": ["ber"]},
  {"name": "Lissabon", "country": "Portugal", "aliases": ["lis", "lisboa", "lisbon"]}
]}
```

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `name` | String | Name, unter dem der Ort im Reise-State steht |
| `country` | String | Land, deutsch |
| `aliases` | Liste von Strings | weitere Schreibweisen und Flughafencodes, klein geschrieben |

**Prüfung der Orte:** Ein Ort aus dem Chat oder dem Formular wird gegen diese Liste geprüft, ohne Rücksicht auf Groß- und Kleinschreibung und Akzente. Ein bekannter Name oder Alias wird zum Namen aus der Liste („lisbon“ → „Lissabon“). Ein unbekannter Ort wird mit dem Grund abgelehnt („There are no flights for this place yet …“): im Chat sagt der Agent das, im Formular gibt es `400` mit `fields.fields.<origin|destination>`. Ist der Planner nicht erreichbar, werden Orte ungeprüft übernommen.

| Fall | Status | Antwort |
| --- | --- | --- |
| Planner nicht erreichbar und keine Liste vorgehalten | `503` | `{"error": {"code": "service_unavailable", "message": "The list of places is temporarily unavailable."}}` |

---

## `GET /api/v1/planning-sessions/{id}/trip-state/`

Liefert, was über die Reise einer Planungssitzung bekannt ist, ohne eine Nachricht zu senden. Die Oberfläche füllt damit nach dem Neuladen ihr Reiseformular. Der Aufruf ändert nichts und ruft weder das LLM noch den Journey Planner auf.

**Pfadparameter:** `id` ist die UUID der Sitzung.

```sh
curl http://localhost:8000/api/v1/planning-sessions/d848ece2-0ccb-42a5-a799-41b7bf93b40e/trip-state/
```

`200 OK`

```json
{
  "trip_state": {
    "origin": {"value": null, "provenance": "unknown"},
    "destination": {"value": "Lissabon", "provenance": "confirmed"},
    "departure": {"value": null, "provenance": "unknown"},
    "return": {"value": null, "provenance": "unknown"},
    "travelers": {"value": null, "provenance": "unknown"},
    "budget": {"value": null, "provenance": "unknown"},
    "max_stops": {"value": null, "provenance": "unknown"},
    "trip_type": {"value": null, "provenance": "unknown"}
  },
  "missing_fields": ["origin", "departure", "return", "travelers"]
}
```

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `trip_state` | Objekt | Reise-State der Sitzung, Aufbau wie in der Antwort auf [`POST …/messages/`](#post-apiv1planning-sessionsidmessages) |
| `missing_fields` | Liste von Strings | fehlende Pflichtangaben in der Reihenfolge, in der der Agent fragt |

Eine Sitzung ohne Nachrichten ergibt `200` mit allen acht Feldern auf `unknown` und `"missing_fields": ["origin", "destination", "departure", "return", "travelers"]`.

**Fehlerfälle**

| Fall | Status | Antwort |
| --- | --- | --- |
| unbekannte UUID oder keine gültige UUID | `404` | `{"error": {"code": "not_found", "message": "The requested resource was not found."}}` |
| `POST`, `PUT`, `PATCH`, `DELETE` | `405` | `method_not_allowed` |
| Datenbank nicht erreichbar | `503` | `service_unavailable` wie oben |

---

## `POST /api/v1/planning-sessions/{id}/messages/`

Ein Gesprächsschritt mit dem Main-Agent (AG08 #37). Der Aufruf nimmt Freitext, Formularwerte oder beides entgegen, übernimmt die gültigen Angaben in den Reise-State der Sitzung und liefert die Antwort des Agenten:

Der Code prüft die folgenden Fälle in dieser Reihenfolge, der erste zutreffende gilt:

1. **Fehlt eine Pflichtangabe** (`origin`, `destination`, `departure`, `return`, `travelers`), fragt der Agent nach der ersten fehlenden, immer in dieser Reihenfolge. `result` ist `null`. `return` ist keine Pflichtangabe, wenn `trip_type` `one_way` ist.
2. **Ist eine Pflichtangabe nur geraten** (Herkunft `inferred`), nennt der Agent seine Annahme und bittet um Bestätigung oder eine genauere Angabe. Er sucht noch nicht, `result` ist `null`. Eine Zustimmung wie „ja“ oder „passt“ setzt die Herkunft auf `confirmed`. Der Agent fragt nur einmal: Enthält die nächste Nachricht andere Reisedaten und keine Korrektur, gilt die Annahme ebenfalls als bestätigt.
3. **Hat sich nichts geändert und enthält die Nachricht keine Reisedaten**, antwortet der Agent ohne neue Suche, `result` ist `null`. Das ist der Fall, wenn der Aufruf einen `text` enthält, die Sitzung schon eine Antwort mit `result` hat (ein `result` mit dem Status `error` zählt nicht), der Reise-State nach dem Aufruf derselbe ist wie davor und das LLM die Nachricht nicht als Reisedaten einstuft, etwa bei „Danke“ oder einer Frage. Wiederholt die Nachricht dagegen Reisedaten, sucht der Agent erneut.
4. **Sonst sucht der Agent** über den Journey Planner und hängt das Ergebnis als `result` an seine Antwort. Ein Aufruf nur mit `fields` sucht immer, wenn die Fälle 1 und 2 nicht zutreffen, auch mit unveränderten Werten. Mit einem Zeitraum in `return` sucht der Agent Hin- und Rückflug, mit `trip_type` `one_way` nur den Hinflug.

Mit `LLM_PROVIDER=gemini` schreibt das LLM die Antworttexte in der Sprache der Nachricht, im Zweifel deutsch. Die Liste der Verbindungen in `content` hängt immer der Code an; sie und die Meldungen über einen Ausfall der Flugsuche sind immer deutsch. Mit `LLM_PROVIDER=offline` (Standard) liest ein regelbasierter Ersatz die Nachricht, und alle Antworten sind die festen deutschen Texte des Agenten, siehe [DEVELOPMENT.md](DEVELOPMENT.md#llm-zugang). Die Beispiele auf dieser Seite sind mit dem Offline-Ersatz erzeugt.

**Pfadparameter:** `id` ist die UUID der Sitzung.

**Body** (`Content-Type: application/json`)

| Feld | Typ | Pflicht | Validierung |
| --- | --- | --- | --- |
| `text` | String | nein | Freitext, wird am Rand von Leerzeichen befreit, höchstens 2000 Zeichen. Ein leerer Text zählt als nicht gesendet. |
| `fields` | Objekt | nein | Formularwerte für den Reise-State, Feldname → Wert, siehe unten. `null` löscht eine Angabe. |

Mindestens eines von beiden muss Inhalt haben. Unbekannte Felder auf oberster Ebene werden ignoriert.

Erlaubte Einträge in `fields`:

| Feld | Wert | Validierung |
| --- | --- | --- |
| `origin`, `destination` | String | nicht leer, höchstens 100 Zeichen. Start und Ziel müssen sich unterscheiden, Groß- und Kleinschreibung zählt dabei nicht. |
| `departure` | Datum `YYYY-MM-DD` oder `{"earliest": …, "latest": …}` | Zeitraum des Hinflugs, nicht vollständig in der Vergangenheit. Fehlt eines der beiden Enden, gilt das andere. Liegt `latest` vor `earliest`, werden die Enden getauscht. Hat der Zeitraum schon begonnen, beginnt er heute. Ein Zeitstempel wie `2027-05-20T00:00:00` wird als sein Datum gelesen. |
| `return` | wie `departure` | Zeitraum des Rückflugs, dieselben Regeln. Er darf nicht vor dem Hinflug liegen: `latest` nicht vor `departure.earliest`. |
| `trip_type` | String | `round_trip` oder `one_way` |
| `travelers` | Ganzzahl | mindestens 1; eine ganzzahlige Kommazahl wie `2.0` wird angenommen |
| `budget` | Zahl oder [Geldbetrag](API_CONVENTIONS.md#7-geldbeträge) | größer als 0. Eine bloße Zahl gilt als EUR pro Person. `basis` ist `per_person` oder `trip_total`. |
| `max_stops` | Ganzzahl | mindestens 0, je Richtung |

Jeder Eintrag darf `null` sein. `null` löscht die Angabe: Eine gelöschte Pflichtangabe fragt der Agent wieder ab, ein gelöschtes Budget oder `max_stops` bedeutet keine Grenze. Das Budget gilt für die ganze Reise, bei Hin- und Rückflug also für beide Flüge zusammen.

Der Unterschied zwischen beiden Wegen:

- **`fields`** kommen direkt von der Nutzerin oder dem Nutzer und gelten als bestätigt (`confirmed`). Ein ungültiger Wert oder ein unbekannter Feldname ergibt `400`, und der ganze Aufruf ändert nichts.
- **`text`** liest das LLM, danach prüft der Code jeden Wert. Alles, was eine Nachricht sagt, wird in einem Schritt übernommen, damit die Werte einer Nachricht gegeneinander geprüft werden und nicht gegen veraltete. Ein ungültiger Wert ist hier kein Fehler, er wird nur nicht übernommen. Außer bei einem Ausfall der Flugsuche weist der Agent in seiner Antwort darauf hin. Werte, die das LLM nur erschlossen hat, bekommen die Herkunft `inferred`. Sie ersetzen auch eine bestätigte Angabe; ist eine Pflichtangabe darunter, lässt der Agent sie vor der Suche bestätigen (Fall 2 oben). Nimmt die Nachricht eine Angabe zurück, ohne eine neue zu nennen, etwa „Budget ist mir egal“, wird sie gelöscht. Der Offline-Ersatz rät nie und erkennt keine Rücknahme: Mit ihm entsteht kein `inferred`.

**Widersprüche: Die letzte Aussage gewinnt.** Das gilt für `text` und `fields`. Abgelehnt wird ein Wert nur, wenn er für sich ungültig ist. Widerspricht er einer älteren Angabe, wird die ältere gelöscht und der Agent fragt wieder danach:

| Neue Angabe | Folge |
| --- | --- |
| Start gleich dem bekannten Ziel, oder Ziel gleich dem bekannten Start | Der Ort wechselt die Rolle, das andere Feld ist wieder offen. Hat das LLM den Ort nur erschlossen (`inferred`), wird er stattdessen abgelehnt. |
| Start und Ziel in derselben Nachricht oder demselben Aufruf gleich | `destination` wird abgelehnt |
| Hinflug nach dem bekannten Rückflug | `return` ist wieder offen |
| Rückflug vor dem Hinflug | `return` wird abgelehnt |
| `trip_type` `one_way` | `return` wird gelöscht und ist keine Pflichtangabe mehr |
| Rückflugdatum bei `trip_type` `one_way`, auch wenn beides zusammen kommt | `trip_type` wird `round_trip`, das Datum gilt |

„Abgelehnt“ heißt bei `fields` `400`, bei `text` ein Hinweis in der Antwort des Agenten.

```sh
curl -X POST http://localhost:8000/api/v1/planning-sessions/d848ece2-0ccb-42a5-a799-41b7bf93b40e/messages/ \
  -H 'Content-Type: application/json' -d '{"text": "Hallo, ich will nach Lissabon"}'
```

`201 Created`

```json
{
  "user_message": {
    "id": "6f0f8a0e-5d0b-4c57-9a52-0c8f1c8f8a11",
    "role": "user",
    "content": "Hallo, ich will nach Lissabon",
    "created_at": "2026-11-15T17:30:02.114532Z",
    "result": null
  },
  "reply": {
    "id": "0b6c2b1e-3c1f-4c0e-8e58-7a1c5a0f4d22",
    "role": "assistant",
    "content": "Von wo möchtest du starten?",
    "created_at": "2026-11-15T17:30:02.120871Z",
    "result": null
  },
  "trip_state": {
    "origin": {"value": null, "provenance": "unknown"},
    "destination": {"value": "Lissabon", "provenance": "confirmed"},
    "departure": {"value": null, "provenance": "unknown"},
    "return": {"value": null, "provenance": "unknown"},
    "travelers": {"value": null, "provenance": "unknown"},
    "budget": {"value": null, "provenance": "unknown"},
    "max_stops": {"value": null, "provenance": "unknown"},
    "trip_type": {"value": null, "provenance": "unknown"}
  },
  "missing_fields": ["origin", "departure", "return", "travelers"]
}
```

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `user_message` | Nachricht oder `null` | die gespeicherte Nachricht; `null`, wenn nur `fields` gesendet wurden |
| `reply` | Nachricht | Antwort des Agenten |
| `trip_state` | Objekt | Reise-State nach diesem Schritt: immer alle acht Felder (`origin`, `destination`, `departure`, `return`, `travelers`, `budget`, `max_stops`, `trip_type`), jedes mit `value` und `provenance` |
| `trip_state.*.provenance` | String | `confirmed` (von der Nutzerin oder dem Nutzer genannt oder bestätigt), `inferred` (vom Agenten erschlossen und noch nicht bestätigt), `unknown` (kein Wert, `value` ist `null`) |
| `trip_state.departure.value`, `trip_state.return.value` | Objekt oder `null` | immer ein Zeitraum `{"earliest": "YYYY-MM-DD", "latest": "YYYY-MM-DD"}`, bei einem festen Datum zweimal derselbe Tag |
| `trip_state.trip_type.value` | String oder `null` | `round_trip`, `one_way` oder `null`. `null` wird wie `round_trip` behandelt: Der Agent fragt nach dem Rückflug. |
| `trip_state.budget.value` | Geldbetrag oder `null` | Obergrenze mit `basis` `per_person` oder `trip_total` |
| `missing_fields` | Liste von Strings | fehlende Pflichtangaben in der Reihenfolge, in der der Agent fragt: `origin`, `destination`, `departure`, `return`, `travelers`. `return` fehlt nie bei `trip_type` `one_way`. `[]`, wenn alle Pflichtangaben da sind. |

Eine **Nachricht** hat diese Felder:

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `id` | String (UUID) | Kennung der Nachricht |
| `role` | String | `user` oder `assistant` |
| `content` | String | Text der Nachricht |
| `created_at` | String (ISO 8601, UTC) | Zeitpunkt der Anlage |
| `result` | Objekt oder `null` | Suchergebnis; nur bei Antworten des Agenten, die auf eine Suche folgen, sonst `null` (Rückfrage, Bitte um Bestätigung, Antwort ohne neue Suche) |

### Suchergebnis `result`

Sobald der Agent sucht, hat `reply.result` immer diese fünf Felder:

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `status` | String | `ok` (Treffer), `no_results` (Suche hat funktioniert, nichts passt), `error` (Suche konnte nicht ausgeführt werden) |
| `journeys` | Liste | bei `ok` 1–5 Varianten, beste zuerst, unverändert vom Journey Planner; sonst `[]`. Aufbau einer Variante: [SEARCH_CONTRACT.md](SEARCH_CONTRACT.md#journey-vorläufig-wird-an-ds1-angeglichen). Bei Hin- und Rückflug ist jede Variante ein Paar: der Hinflug mit dem Rückflug in `inbound` und dem Preis beider Flüge in `total_price`. Ohne Rückflug ist `inbound` `null` und `total_price` gleich `price`. |
| `review` | Objekt | Prüfung durch den Optimization Agent, Kennung der Variante → `{"tags": […], "warnings": […]}` mit einem Eintrag je Variante. `{}` bei `no_results` und `error` sowie bei `OPTIMIZATION_AGENT_ENABLED=false`. |
| `no_results` | Objekt oder `null` | nur bei `no_results`: `reason`, `direction` und `closest_journey` wie in [SEARCH_CONTRACT.md](SEARCH_CONTRACT.md#no_results) |
| `alternative` | Objekt oder `null` | nur bei `no_results` und nur, wenn eine gelockerte Suche etwas gefunden hat, siehe unten |

`review`:

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `tags` | Liste von Strings | `cheapest` und `fastest` (nur bei mehr als einer Variante), `recommended` (bestes Verhältnis von Preis und Dauer unter den Varianten mit Preis und ohne Warnung). Bei Hin- und Rückflug zählen der Gesamtpreis und die Summe beider Flugdauern. |
| `warnings` | Liste von Strings | deutsche Hinweise: Ankunft nicht nach der Abfahrt, Anschluss vor der Ankunft, weniger als 45 Minuten zum Umsteigen, mehr als 5 Stunden Wartezeit, kein Preis bekannt. Hinweise zum Rückflug beginnen mit „Rückflug: “. |

`alternative`:

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `strategy` | String | `flexible_dates` (Zeitraum um drei Tage davor und danach erweitert, nie in die Vergangenheit; bei Hin- und Rückflug auch der Zeitraum des Rückflugs, der nie vor dem frühesten Hinflug beginnt) oder `more_stops` (ein Umstieg mehr erlaubt) |
| `description` | String | deutscher Satz, der die Lockerung nennt |
| `request` | Objekt | der gelockerte Suchauftrag, mit dem die Varianten gefunden wurden: Aufbau wie in [SEARCH_CONTRACT.md](SEARCH_CONTRACT.md#request), gegenüber dem ursprünglichen Auftrag sind nur `departure` und `return` oder nur `max_stops` geändert |
| `journeys` | Liste | Varianten der gelockerten Suche, Aufbau wie oben |
| `review` | Objekt | Prüfung dieser Varianten, Aufbau wie oben |

Das Budget lockert der Agent nie. Der Reise-State bleibt bei einer Alternative unverändert.

Aufbau von `reply.content` mit dem Offline-Ersatz:

- **Treffer:** ein Absatz mit der Zusammenfassung der Suche und der Zahl der Verbindungen, danach ein Zeilenumbruch und die Liste, eine Zeile je Variante, Warnungen eingerückt darunter. Bei Hin- und Rückflug nennt die Zeile den Gesamtpreis mit dem Zusatz „für Hin- und Rückflug“, eingerückt darunter folgen je eine Zeile „Hin:“ und „Zurück:“ mit Preis, Dauer, Umstiegen und Abflug des einzelnen Flugs.
- **Keine Treffer:** die Begründung mit einem Vorschlag. Gibt es eine Alternative, folgen im selben Absatz ihre `description`, dann ein Zeilenumbruch und die Liste ihrer Varianten.

Mit Gemini schreibt das LLM den Text vor der Liste selbst, die Liste bleibt dieselbe.

Beispiel für `no_results` mit Alternative, nur `content` und `result` der Antwort, gekürzt: Berlin nach Rom am 20.05.2027 für eine Person, nur Hinflug (`"trip_type": "one_way"`). Der Dummy-Provider bedient diese Strecke donnerstags nicht.

```json
{
  "content": "Für Berlin nach Rom am 20.05.2027 für 1 Person habe ich leider nichts gefunden. An diesen Tagen gibt es keine Verbindung auf dieser Strecke. Du könntest ein anderes Datum oder einen Zeitraum angeben. Wenn du beim Datum flexibel bist, habe ich für den Abflug zwischen 17.05.2027 und 23.05.2027 aber etwas gefunden:\n1. 66,30 € pro Person · 3 h 55 min · 1 Umstieg (München) · ab 19.05.2027 10:00 Uhr · günstigste\n…",
  "result": {
    "status": "no_results",
    "journeys": [],
    "review": {},
    "no_results": {"reason": "no_connection", "direction": null, "closest_journey": null},
    "alternative": {
      "strategy": "flexible_dates",
      "description": "Wenn du beim Datum flexibel bist, habe ich für den Abflug zwischen 17.05.2027 und 23.05.2027 aber etwas gefunden:",
      "request": {"origin": "Berlin", "destination": "Rom", "departure": {"earliest": "2027-05-17", "latest": "2027-05-23"}, "return": null, "travelers": 1, "max_price": null, "max_stops": null, "modes": ["flight"]},
      "journeys": ["…"],
      "review": {"dummy-berlin-rom-2027-05-19-via-muenchen": {"tags": ["cheapest"], "warnings": []}, "…": "…"}
    }
  }
}
```

Bei Hin- und Rückflug nennt `description` beide Zeiträume: „Wenn du beim Datum flexibel bist, habe ich für den Abflug zwischen … und … und den Rückflug zwischen … und … aber etwas gefunden:“.

Beispiel mit vollständigen Angaben für Hin- und Rückflug, `content` und `journeys` gekürzt. Die ungekürzten Varianten stehen in [`contracts/search-v1/response_round_trip.json`](contracts/search-v1/response_round_trip.json).

```sh
curl -X POST http://localhost:8000/api/v1/planning-sessions/d848ece2-0ccb-42a5-a799-41b7bf93b40e/messages/ \
  -H 'Content-Type: application/json' \
  -d '{"fields": {"origin": "Berlin", "destination": "Lissabon", "departure": "2027-05-20", "return": "2027-05-27", "travelers": 2, "budget": 400}}'
```

`201 Created`

```json
{
  "user_message": null,
  "reply": {
    "id": "c0a4e6c8-0f8e-4b7e-9d2f-3b9f5f6f0a33",
    "role": "assistant",
    "content": "Ich habe alles, was ich brauche: Berlin nach Lissabon am 20.05.2027, zurück am 27.05.2027, für 2 Personen, höchstens 400,00 € pro Person. Dafür habe ich 5 Verbindungen gefunden:\n1. 200,67 € pro Person für Hin- und Rückflug · günstigste, Empfehlung\n   Hin: 98,00 € pro Person · 8 h 20 min · 2 Umstiege (Zürich, Madrid) · ab 20.05.2027 06:00 Uhr\n   Zurück: 102,67 € pro Person · 8 h 50 min · 2 Umstiege (Paris, Frankfurt) · ab 27.05.2027 05:45 Uhr\n2. 221,67 € pro Person für Hin- und Rückflug\n   Hin: 119,00 € pro Person · 4 h 40 min · 1 Umstieg (Frankfurt) · ab 20.05.2027 07:05 Uhr\n   Zurück: 102,67 € pro Person · 8 h 50 min · 2 Umstiege (Paris, Frankfurt) · ab 27.05.2027 05:45 Uhr\n   Achtung: Nur 25 Minuten zum Umsteigen in Frankfurt.\n…",
    "created_at": "2026-11-15T17:31:40.402915Z",
    "result": {
      "status": "ok",
      "journeys": [
        {
          "id": "dummy-berlin-lissabon-2027-05-20-via-zuerich-madrid+dummy-lissabon-berlin-2027-05-27-via-paris-frankfurt",
          "legs": ["…"], "offers": ["…"], "duration_minutes": 500, "stops": 2,
          "price": {"amount": 98.0, "currency": "EUR", "basis": "per_person"},
          "inbound": {
            "id": "dummy-lissabon-berlin-2027-05-27-via-paris-frankfurt",
            "legs": ["…"], "offers": ["…"], "duration_minutes": 530, "stops": 2,
            "price": {"amount": 102.67, "currency": "EUR", "basis": "per_person"}
          },
          "total_price": {"amount": 200.67, "currency": "EUR", "basis": "per_person"}
        },
        "…"
      ],
      "review": {
        "dummy-berlin-lissabon-2027-05-20-via-zuerich-madrid+dummy-lissabon-berlin-2027-05-27-via-paris-frankfurt": {"tags": ["cheapest", "recommended"], "warnings": []},
        "dummy-berlin-lissabon-2027-05-20-via-frankfurt+dummy-lissabon-berlin-2027-05-27-via-paris-frankfurt": {"tags": [], "warnings": ["Nur 25 Minuten zum Umsteigen in Frankfurt."]},
        "dummy-berlin-lissabon-2027-05-20-via-zuerich-madrid+dummy-lissabon-berlin-2027-05-27-via-madrid": {"tags": [], "warnings": []},
        "dummy-berlin-lissabon-2027-05-20-via-frankfurt+dummy-lissabon-berlin-2027-05-27-via-madrid": {"tags": ["fastest"], "warnings": ["Nur 25 Minuten zum Umsteigen in Frankfurt."]},
        "dummy-berlin-lissabon-2027-05-20-via-madrid+dummy-lissabon-berlin-2027-05-27-via-paris": {"tags": [], "warnings": []}
      },
      "no_results": null,
      "alternative": null
    }
  },
  "trip_state": {
    "origin": {"value": "Berlin", "provenance": "confirmed"},
    "destination": {"value": "Lissabon", "provenance": "confirmed"},
    "departure": {"value": {"earliest": "2027-05-20", "latest": "2027-05-20"}, "provenance": "confirmed"},
    "return": {"value": {"earliest": "2027-05-27", "latest": "2027-05-27"}, "provenance": "confirmed"},
    "travelers": {"value": 2, "provenance": "confirmed"},
    "budget": {"value": {"amount": 400.0, "currency": "EUR", "basis": "per_person"}, "provenance": "confirmed"},
    "max_stops": {"value": null, "provenance": "unknown"},
    "trip_type": {"value": null, "provenance": "unknown"}
  },
  "missing_fields": []
}
```

Derselbe Aufruf mit `"trip_type": "one_way"` statt `return` und einem Budget von 300 sucht nur den Hinflug. Die Liste hat dann eine Zeile je Variante, zum Beispiel `1. 98,00 € pro Person · 8 h 20 min · 2 Umstiege (Zürich, Madrid) · ab 20.05.2027 06:00 Uhr · günstigste, Empfehlung`, und die Varianten stehen in [`contracts/search-v1/response_ok.json`](contracts/search-v1/response_ok.json).

Folgt in derselben Sitzung eine Nachricht ohne Reisedaten, etwa `{"text": "Danke"}`, sucht der Agent nicht noch einmal (Fall 3). `reply.result` ist `null`, `trip_state` und `missing_fields` sind unverändert. Der Text des Agenten ohne LLM lautet dafür:

```text
Deine Suche steht weiterhin: Berlin nach Lissabon am 20.05.2027, zurück am 27.05.2027, für 2 Personen, höchstens 400,00 € pro Person. Sag mir einfach, was ich ändern soll, zum Beispiel Datum, Budget oder Umstiege.
```

Der Offline-Ersatz stuft eine Nachricht, in der er keine Reisedaten erkennt, als Smalltalk ein; damit gilt Fall 3 auch ohne LLM.

Die Bitte um Bestätigung (Fall 2) hat ohne LLM die Form „Ich habe das so verstanden: Abflug zwischen 26.03.2027 und 29.03.2027. Passt das, oder möchtest du es genauer angeben?“, für einen geratenen Rückflug entsprechend „Rückflug am …“. Mit dem Offline-Ersatz kommt sie nur vor, wenn der Reise-State schon einen Wert mit der Herkunft `inferred` enthält.

**Fehlerfälle**

| Fall | Status | Antwort |
| --- | --- | --- |
| weder `text` noch `fields`, oder `text` nur aus Leerzeichen | `400` | `{"error": {"code": "validation_error", "message": "The input is invalid.", "fields": {"non_field_errors": ["Send a text, form fields, or both."]}}}` |
| `text` länger als 2000 Zeichen | `400` | `… "fields": {"text": ["Ensure this field has no more than 2000 characters."]}` |
| `fields` ist kein Objekt | `400` | `… "fields": {"fields": ["Expected a dictionary of items but got type \"list\"."]}` |
| ungültiger Wert in `fields` | `400` | `… "fields": {"fields": {"travelers": ["The number of travellers must be at least 1."]}}` |
| `origin` und `destination` im selben Aufruf gleich | `400` | `… "fields": {"fields": {"destination": ["Origin and destination must be different places."]}}` |
| `return` in `fields` vor dem Hinflug | `400` | `… "fields": {"fields": {"return": ["The return must not be before the departure."]}}` |
| Datum in `fields` in der Vergangenheit oder nicht lesbar | `400` | `… "fields": {"fields": {"departure": ["The departure date must not be in the past."]}}` bzw. `["The departure date must be a date in the format YYYY-MM-DD."]` |
| unbekannter Wert für `trip_type` | `400` | `… "fields": {"fields": {"trip_type": ["The trip type must be one of round_trip, one_way."]}}` |
| unbekannter Feldname in `fields` | `400` | `… "fields": {"fields": {"hotel": ["Unknown field."]}}` |
| unbekannte UUID oder keine gültige UUID | `404` | `{"error": {"code": "not_found", "message": "The requested resource was not found."}}` |
| LLM antwortet nicht, Quota erschöpft oder Antwort unbrauchbar | `503` | `{"error": {"code": "service_unavailable", "message": "The language model is temporarily unavailable."}}` |
| Datenbank nicht erreichbar | `503` | `service_unavailable` wie oben |

Bei `400` und `503` wird nichts gespeichert, weder Nachrichten noch Reise-State. Dieselbe Nachricht kann erneut gesendet werden.

Kein Fehler ist ein einzelner Ort in `fields`, der dem jeweils anderen bekannten Wert gleicht: Der Ort wechselt die Rolle, siehe [oben](#post-apiv1planning-sessionsidmessages).

**Kein Fehlerstatus** ist ein Ausfall der Suche: Ist der Journey Planner nicht erreichbar oder meldet er selbst einen Fehler, antwortet der Endpunkt mit `201`. `reply.content` erklärt den Ausfall, `reply.result.status` ist `error`, und die Angaben bleiben im Reise-State gespeichert.

---

## `GET /api/v1/planning-sessions/{id}/messages/`

Liefert den Gesprächsverlauf einer Planungssitzung, älteste Nachricht zuerst. Die Liste ist seitenweise aufgebaut mit 20 Nachrichten pro Seite.

**Pfadparameter:** `id` ist die UUID der Sitzung.

**Query-Parameter**

| Parameter | Werte | Bedeutung |
| --- | --- | --- |
| `page` | Ganzzahl ≥ 1 | Seite, Standard 1 |

```sh
curl http://localhost:8000/api/v1/planning-sessions/d848ece2-0ccb-42a5-a799-41b7bf93b40e/messages/
```

`200 OK`

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {"id": "6f0f8a0e-5d0b-4c57-9a52-0c8f1c8f8a11", "role": "user", "content": "Hallo, ich will nach Lissabon", "created_at": "2026-11-15T17:30:02.114532Z", "result": null},
    {"id": "0b6c2b1e-3c1f-4c0e-8e58-7a1c5a0f4d22", "role": "assistant", "content": "Von wo möchtest du starten?", "created_at": "2026-11-15T17:30:02.120871Z", "result": null}
  ]
}
```

Die Felder einer Nachricht stehen oben beim `POST`. Antworten des Agenten mit Suchergebnis enthalten ihr vollständiges `result`. Eine Sitzung ohne Nachrichten ergibt `200` mit `"count": 0`. Der Reise-State ist nicht Teil dieser Antwort; ihn liefert [`GET …/trip-state/`](#get-apiv1planning-sessionsidtrip-state).

**Fehlerfälle**

| Fall | Status | Antwort |
| --- | --- | --- |
| unbekannte UUID oder keine gültige UUID | `404` | `{"error": {"code": "not_found", "message": "The requested resource was not found."}}` |
| Seite existiert nicht | `404` | `{"error": {"code": "not_found", "message": "Invalid page."}}` |
| `PUT`, `PATCH`, `DELETE` | `405` | `method_not_allowed` |
| Datenbank nicht erreichbar | `503` | `service_unavailable` |

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
