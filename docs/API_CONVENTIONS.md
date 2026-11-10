# API-Konventionen

**Verbindlich** für alle Endpunkte des Backends. Neue Endpunkte halten sich daran. Wer begründet abweichen muss, ergänzt diese Seite im selben Pull Request. Die Referenz aller vorhandenen Endpunkte steht in [API.md](API.md), die Beispiele hier stammen aus der laufenden API.

Mit **„noch nicht verwendet“** markierte Regeln gelten für künftige Endpunkte. Bisher setzt sie noch kein Endpunkt um.

## 1. Adressen

- Alle Pfade beginnen mit `/api/v1/`. Inkompatible Änderungen bekommen eine neue Version `/api/v2/`, etwa wenn ein Feld entfernt oder umbenannt wird oder sich seine Bedeutung ändert. Neue optionale Felder sind kompatibel und brauchen keine neue Version.
- Ressourcen stehen im **Plural**, in Kleinbuchstaben und mit Bindestrich: `/api/v1/planning-sessions/`, `/api/v1/reference-cases/`.
- Eine einzelne Ressource liegt unter `/<ressource>/{id}/`, Unterressourcen darunter, etwa `/api/v1/planning-sessions/{id}/messages/` (geplant, AG08 #37).
- **Jeder Pfad endet mit `/`.** Ohne Schrägstrich antwortet die API mit `404`. Es gibt bewusst keine Weiterleitung, weil dabei die Daten eines POST verloren gingen.
- Filter und Seiten sind Query-Parameter in `snake_case`: `/api/v1/reference-cases/?split=train&page=2`.

## 2. Methoden

| Methode | Verwendung | Ändert Daten | Erfolg |
| --- | --- | --- | --- |
| `GET` | Liste oder einzelne Ressource lesen | **nie** | `200` |
| `POST` | Ressource anlegen; Aktionen, die in keine andere Methode passen | ja | `201` mit der angelegten Ressource, bei Aktionen `200` |
| `PATCH` | einzelne Felder einer Ressource ändern (noch nicht verwendet) | ja | `200` mit der geänderten Ressource |
| `DELETE` | Ressource löschen (noch nicht verwendet) | ja | `204` ohne Inhalt |

`PUT` (ganze Ressource ersetzen) wird nicht verwendet, Änderungen laufen über `PATCH`. Eine Methode, die ein Pfad nicht anbietet, beantwortet die API mit `405` und dem Header `Allow`, der die erlaubten Methoden nennt.

## 3. Statuscodes

| Code | Bedeutung | `error.code` | Beispiel |
| --- | --- | --- | --- |
| `200` | erfolgreiche Abfrage oder Änderung | – | Session abrufen |
| `201` | Ressource angelegt | – | Session anlegen |
| `204` | erfolgreich, ohne Antwortinhalt (noch nicht verwendet) | – | Ressource löschen |
| `400` | ungültige Eingabe | `validation_error`, `parse_error` | leerer Titel, kaputtes JSON, ungültiger Filter |
| `404` | nicht gefunden | `not_found` | unbekannte ID, ungültige ID, unbekannter Pfad, nicht existierende Seite |
| `405` | Methode nicht angeboten | `method_not_allowed` | `POST` auf Referenzfälle |
| `409` | Zustandskonflikt: Die Anfrage ist gültig, passt aber nicht zum aktuellen Zustand (noch nicht verwendet) | `conflict` | Suche starten, obwohl Pflichtangaben fehlen |
| `415` | Anfrage nicht als JSON | `unsupported_media_type` | `Content-Type: text/plain` |
| `500` | unerwarteter Fehler | `internal_error` | Programmfehler |
| `503` | vorübergehend nicht verfügbar | `service_unavailable` | Datenbank gestoppt, später auch LLM oder Anbieter |

Im Code wirft ein View dafür Exceptions und baut keine eigenen Fehlerantworten:

- `serializers.ValidationError` führt zu `400`.
- `NotFound` aus `rest_framework.exceptions` sowie Djangos `Http404` führen zu `404`.
- `Conflict` und `ServiceUnavailable` aus [`config/exceptions.py`](../backend/config/exceptions.py) führen zu `409` und `503`.

Unerwartete Exceptions und Datenbankausfälle fängt der zentrale Handler ab.

## 4. Fehlerformat

Jeder Fehler hat dieselbe Struktur, auch ein `404` für einen unbekannten Pfad:

```json
{"error": {"code": "validation_error", "message": "The input is invalid.", "fields": {"title": ["This field is required."]}}}
```

| Feld | Regel |
| --- | --- |
| `code` | Stabiler, maschinenlesbarer Code in `snake_case`. Das Frontend entscheidet anhand von `code` und HTTP-Status, nie anhand von `message`. |
| `message` | Englische Beschreibung für Entwicklerinnen und Entwickler. Sie kann sich ändern, deshalb zeigt die Oberfläche eigene Texte. |
| `fields` | Gibt es nur bei `validation_error`. Feldname → Liste von Meldungen. Fehler ohne Feldbezug stehen unter `non_field_errors`, Fehler in Listen unter dem Index, z. B. `{"date": {"0": ["…"]}}`. |

**Keine internen Details:** Antworten enthalten keine Tracebacks, SQL-Befehle, Hostnamen oder Zugangsdaten, auch nicht bei `DJANGO_DEBUG=true`. Diese Details stehen nur im Server-Log.

Vorhandene Codes: `validation_error`, `parse_error`, `unsupported_media_type`, `not_found`, `method_not_allowed`, `conflict`, `service_unavailable`, `internal_error`. Ein neuer Code kommt mit einer kurzen Erklärung in diese Liste.

## 5. Feldnamen und Werte

- **Feldnamen** sind englisch und in `snake_case`: `created_at`, `has_annotated_plan`. Die einzige Ausnahme sind die Referenzdaten, sie behalten die Originalnamen des TravelPlanner-Datensatzes (`org`, `dest`, `people_number`), damit sie mit dem Paper vergleichbar bleiben.
- **IDs** stehen immer im Feld `id` und sind immer Strings. Anwendungsdaten haben UUIDs (`"d848ece2-0ccb-42a5-a799-41b7bf93b40e"`), Referenzdaten stabile, lesbare Kennungen (`"travelplanner-train-0000"`). Fortlaufende Datenbank-IDs werden nicht nach außen gegeben.
- **Wahrheitswerte** beginnen mit `is_` oder `has_`.
- **Aufzählungen** sind kleingeschriebene Strings (`"train"`, `"easy"`). Die erlaubten Werte stehen beim Endpunkt in [API.md](API.md).
- **Fehlende oder unbekannte Werte:** Ein dokumentiertes Feld ist in Antworten **immer vorhanden**. Ist ein Wert unbekannt oder passt er nicht, steht dort `null`, z. B. `budget` im Split `test`. Leere Strings oder `0` sind kein Platzhalter. Eine leere Liste `[]` bedeutet „bekanntermaßen leer“.
- **Eingaben:**
  - Unbekannte Felder und schreibgeschützte Felder wie `id` und `created_at` werden ignoriert.
  - Fehlt ein Pflichtfeld, gibt es `400`. `null` ist nur erlaubt, wo es dokumentiert ist.
  - Texte werden am Anfang und Ende von Leerzeichen befreit, ein Text nur aus Leerzeichen gilt daher als leer.
- **Reihenfolge:** Die Reihenfolge der Schlüssel in JSON-Objekten ist nicht festgelegt, PostgreSQL ordnet sie beim Speichern neu.

## 6. Datum und Zeit

- **Zeitpunkte** folgen ISO 8601 mit Zeitzone. Antworten verwenden UTC mit `Z`: `"2026-11-10T12:12:15.800785Z"`.
- **Eingaben** sollen eine Zeitzone enthalten (`Z` oder `+01:00`). Ohne Angabe behandelt das Backend den Wert als UTC.
- **Kalenderdaten** ohne Uhrzeit haben das Format `YYYY-MM-DD`, z. B. Reisedaten wie `"2022-03-16"`.
- **Ortszeiten** wie Abfahrt oder Ankunft kommen mit dem Offset des Ortes: `"2026-12-15T08:00:00+01:00"` (noch nicht verwendet, vgl. DS1 #21).
- **Dauern** tragen ihre Einheit im Feldnamen: `days`, `duration_minutes`.

## 7. Geldbeträge

Ein Geldbetrag ist immer ein Objekt mit Betrag, Währung und Preisbasis:

```json
{"amount": 1700, "currency": "USD", "basis": "trip_total"}
```

| Feld | Regel |
| --- | --- |
| `amount` | JSON-Zahl in der Hauptwährungseinheit mit höchstens zwei Nachkommastellen, z. B. `251.5` für 251,50. Im Backend als `Decimal` mit `coerce_to_string=False` ausgeben. |
| `currency` | Währungscode nach ISO 4217, immer angegeben, auch bei EUR. |
| `basis` | Wofür der Betrag gilt: `trip_total` (ganze Reise, alle Reisenden), `per_person` (pro Person, noch nicht verwendet), `per_night` (pro Nacht, noch nicht verwendet). Eine neue Basis wird hier ergänzt. |

Ist ein Preis unbekannt, ist das **ganze Objekt `null`**, nie `amount: 0`. Währungen rechnet das Backend bisher nicht um.

## 8. Listen und Seiten

Jede Liste antwortet seitenweise im selben Format:

```json
{"count": 45, "next": "http://localhost:8000/api/v1/reference-cases/?page=2&split=train", "previous": null, "results": [ … ]}
```

- `count` ist die Gesamtzahl aller Treffer, `next` und `previous` sind vollständige URLs oder `null`.
- **Seiten** über `?page=N`, die Zählung beginnt bei 1, 20 Einträge pro Seite (Einstellung `PAGE_SIZE`). Eine Seite, die es nicht gibt, ergibt `404 not_found`.
- **Filter** sind Query-Parameter. Ein ungültiger Wert ergibt `400 validation_error` mit `fields`.
- **Reihenfolge:** Jede Liste hat eine feste, beim Endpunkt dokumentierte Reihenfolge.
- **Große Felder** dürfen in der Liste fehlen. Die Detailansicht liefert sie, so wie bei `reference_information`.
- Es gibt keine Liste ohne Seiten.

## 9. Anfragen und Antworten

- **Formate:** Anfragen mit Inhalt senden JSON mit `Content-Type: application/json`, sonst gibt es `415`. Antworten sind JSON in UTF-8.
- **Zugriff:** Bisher gibt es keine Anmeldung, alle Endpunkte sind offen und nur über `localhost` erreichbar. Accounts sind nicht Teil des Grundgerüsts.
- **Frontend:** Es ruft die API nur über [`frontend/src/api/client.ts`](../frontend/src/api/client.ts) mit relativen Pfaden auf. So stehen keine Adressen in einzelnen Komponenten.

## 10. Dokumentationspflicht

Jeder neue oder geänderte Endpunkt wird **im selben Pull Request** in [API.md](API.md) beschrieben. Dazu gehören Methode, URL, Parameter, Validierung, eine Beispielantwort und die Fehlerfälle mit Beispiel, außerdem Tests. Die Schritte zeigt [EXTENDING.md](EXTENDING.md), die gemeinsame Definition of Done steht in [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md).
