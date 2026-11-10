# Backend

Django 5.2 LTS mit Django REST Framework und PostgreSQL 18, Python 3.14. Stellt die REST-API unter `/api/v1/` bereit. Versionen und Datenhaltung: [docs/PROJECT_STRUCTURE.md](../docs/PROJECT_STRUCTURE.md).

## Aufbau

| Pfad | Inhalt |
| --- | --- |
| `config/` | Django-Projekt: Einstellungen aus Umgebungsvariablen, URL-Routing, Health-Endpunkt, einheitliche Fehlerbehandlung. |
| `planning/` | App für Anwendungsdaten. Enthält das Modell `PlanningSession` mit Serializer, Views und Migrationen. |
| `reference_data/` | App für Referenzdaten: historische TravelPlanner-Benchmark-Fälle mit Import-Kommando und nur lesbarer API. Die Daten liegen in `reference_data/data/travelplanner/`, Herkunft und Lizenz stehen in der [README dort](reference_data/data/travelplanner/README.md). |
| `requirements.txt` | Exakt gepinnte Abhängigkeiten, inklusive transitiver Pakete. |

## Umgebungsvariablen

Für die lokale Entwicklung stehen funktionierende Werte in [`.env.example`](../.env.example) im Repo-Root. Mit `cp .env.example .env` entsteht daraus die eigene `.env`. Django liest sie beim Start automatisch. Echte Umgebungsvariablen haben Vorrang, und die `.env` wird nie eingecheckt.

| Variable | Pflicht | Standard | Bedeutung |
| --- | --- | --- | --- |
| `DJANGO_SECRET_KEY` | ja | – | Geheimer Schlüssel von Django. |
| `DJANGO_DEBUG` | nein | `false` | `true` nur für die lokale Entwicklung. |
| `DJANGO_ALLOWED_HOSTS` | nein | `localhost,127.0.0.1` | Kommagetrennte Hostnamen, unter denen das Backend antwortet. |
| `POSTGRES_DB` | ja | – | Name der Datenbank. |
| `POSTGRES_USER` | ja | – | Datenbankbenutzer. |
| `POSTGRES_PASSWORD` | ja | – | Passwort des Datenbankbenutzers. |
| `POSTGRES_HOST` | nein | `localhost` | Host der Datenbank. |
| `POSTGRES_PORT` | nein | `5432` | Port der Datenbank. |

Fehlt eine Pflichtvariable oder ist sie leer, bricht Django beim Start mit einer klaren Meldung ab, zum Beispiel `Environment variable DJANGO_SECRET_KEY is not set.` Ist eine optionale Variable leer, gilt ihr Standardwert.

## Starten

Standard ist Docker Compose aus dem Repo-Root, siehe [README](../README.md#run-with-docker):

```sh
cp .env.example .env
docker compose up --build -d
```

Beim Start wendet das Backend offene Migrationen automatisch an. Weitere Django-Befehle laufen mit `docker compose exec backend python manage.py <befehl>`.

Nach einer Modelländerung erzeugt `docker compose exec backend python manage.py makemigrations` die Migration. Sie landet über den Bind-Mount direkt in `backend/` und wird zusammen mit der Änderung eingecheckt. Anwenden lässt sie sich sofort mit `… migrate` oder beim nächsten Neustart mit `docker compose restart backend`.

### Ohne Docker für das Backend

Zum Debuggen in der IDE kann das Backend auch direkt mit Python 3.14 laufen, Python 3.13 funktioniert ebenfalls. Weil die Compose-Datenbank keinen Host-Port hat, läuft PostgreSQL dafür als einzelner Container. Ein laufendes Compose-Backend blockiert Port 8000, deshalb vorher `docker compose stop backend` ausführen.

```sh
# Im Repo-Root: lokale Konfiguration anlegen
cp .env.example .env

# PostgreSQL 18 als lokaler Container, nur an localhost gebunden,
# mit Datenbankname, Benutzer und Passwort aus der .env
docker run -d --name traveller-db -p 127.0.0.1:5432:5432 --env-file .env postgres:18

cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py runserver
```

Danach antwortet `http://localhost:8000/api/v1/health/`. Mit `docker stop traveller-db` bzw. `docker start traveller-db` bleiben die Daten erhalten. Erst `docker rm -v traveller-db` löscht sie.

## Referenzdaten importieren

Der vollständige TravelPlanner-Datensatz liegt im Repository, der Import braucht also keinen Download. Er umfasst 1.225 Fälle: 45 in `train`, 180 in `validation` und 1.000 in `test`.

```sh
docker compose exec backend python manage.py import_reference_cases
```

```text
  train: 45 valid cases
  validation: 180 valid cases
  test: 1000 valid cases
Imported 1225 cases (1225 new, 0 updated, 0 unchanged), rejected 0.
```

- **Wiederholen:** Ein erneuter Import legt keine Duplikate an. Die Fälle werden über ihre stabile ID abgeglichen, die Ausgabe nennt neue, geänderte und unveränderte Fälle.
- **Ungültige Datensätze:** Sie werden mit Datei, Zeile, ID und Feld abgewiesen, zum Beispiel `Rejected train.jsonl.gz:3 (…): people_number: Ensure this value is greater than or equal to 1.` Gültige Fälle werden trotzdem importiert, der Befehl endet dann mit Exit-Code 1.
- **Geänderte Dateien:** Stimmt die Prüfsumme einer Datendatei nicht mit dem Manifest überein, bricht der Import ab, bevor etwas geschrieben wird.
- **Optionen:** `--split train` importiert nur einzelne Splits und kann mehrfach angegeben werden. `--dry-run` prüft und vergleicht, ohne zu schreiben. Statt des Standarddatensatzes kann ein eigener Pfad zu einer `manifest.json` übergeben werden.
- **Anwendungsdaten bleiben unberührt:** Der Import schreibt nur in die Tabellen von `reference_data`, Planungssitzungen ändert er nicht. Fälle, die aus einer Datei verschwinden, löscht er ebenfalls nicht.

## Endpunkte

Alle Pfade enden mit einem Schrägstrich. Ohne Schrägstrich antwortet die API mit 404. Anfragen und Antworten verwenden JSON, Zeitstempel sind ISO 8601 in UTC.

| Methode | Pfad | Erfolg | Fehler |
| --- | --- | --- | --- |
| `GET` | `/api/v1/health/` | `200` `{"status":"ok","database":"ok"}` | `503` Datenbank nicht erreichbar |
| `POST` | `/api/v1/planning-sessions/` | `201` mit der angelegten Session | `400` ungültige Eingabe, `415` kein JSON |
| `GET` | `/api/v1/planning-sessions/{id}/` | `200` mit der Session | `404` unbekannte oder ungültige ID |
| `GET` | `/api/v1/reference-cases/` | `200` Seite mit Benchmark-Fällen | `400` ungültiger Filter, `404` Seite existiert nicht |
| `GET` | `/api/v1/reference-cases/{id}/` | `200` mit Referenzinformationen und annotiertem Plan | `404` unbekannte ID |

### Planungssitzungen

```sh
curl -X POST http://localhost:8000/api/v1/planning-sessions/ \
  -H 'Content-Type: application/json' -d '{"title": "Wochenende in Leipzig"}'
```

```json
{"id": "b0d98159-b5f4-484d-895a-8061d5184305", "title": "Wochenende in Leipzig", "created_at": "2026-11-10T10:58:14.639761Z"}
```

`title` ist Pflicht. Es darf nicht leer sein und höchstens 200 Zeichen haben. `id` und `created_at` vergibt der Server.

### Referenzfälle (nur lesend)

Die Liste ist seitenweise aufgebaut, mit 20 Fällen pro Seite in der Reihenfolge train, validation, test. Filter gibt es für `split` (`train`, `validation`, `test`), `level` (`easy`, `medium`, `hard`) und `days`. Schreibende Methoden liefern `405`.

```sh
curl 'http://localhost:8000/api/v1/reference-cases/?split=validation&level=hard&page=2'
```

```json
{
  "count": 60,
  "next": "http://localhost:8000/api/v1/reference-cases/?level=hard&page=3&split=validation",
  "previous": "http://localhost:8000/api/v1/reference-cases/?level=hard&split=validation",
  "results": [
    {
      "id": "travelplanner-validation-0140",
      "data_kind": "historical_benchmark",
      "dataset": {"slug": "travelplanner", "name": "TravelPlanner", "version": "8736504e…", "license": "CC BY 4.0", "notice": "Historical benchmark data: …", "…": "…"},
      "split": "validation", "level": "hard",
      "query": "Could you assist with a 5-day travel plan for a duo beginning from Las Vegas and proceeding …",
      "org": "Las Vegas", "dest": "Texas", "days": 5, "visiting_city_number": 2,
      "date": ["2022-03-13", "2022-03-14", "2022-03-15", "2022-03-16", "2022-03-17"], "people_number": 2,
      "local_constraint": {"cuisine": ["American", "Indian", "Mediterranean", "Mexican"], "room type": "not shared room", "house rule": "pets", "transportation": null},
      "budget": {"amount": 3700, "currency": "USD", "basis": "trip_total"},
      "has_annotated_plan": false
    }
  ]
}
```

Jeder Fall ist mit `data_kind: "historical_benchmark"` gekennzeichnet, der Hinweis in `dataset.notice` beschreibt die Daten als historisch. In der Liste fehlen die großen Felder `reference_information` und `annotated_plan`, die liefert erst die Detailansicht `/api/v1/reference-cases/{id}/`. Im Split `test` sind `visiting_city_number`, `people_number`, `local_constraint`, `budget` und `annotated_plan` immer `null`, so wie im Original.

## Fehlerformat

Jeder Fehler hat dieselbe Struktur. `fields` gibt es nur bei Validierungsfehlern.

```json
{"error": {"code": "validation_error", "message": "The input is invalid.", "fields": {"title": ["This field is required."]}}}
```

Codes: `validation_error`, `parse_error`, `unsupported_media_type`, `not_found`, `method_not_allowed`, `service_unavailable`, `internal_error`. Listen antworten immer im Format `{"count", "next", "previous", "results"}`. Unerwartete Fehler werden mit Traceback geloggt. Der Client erhält davon nichts, auch nicht bei `DJANGO_DEBUG=true`.
