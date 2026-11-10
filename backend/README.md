# Backend

Django 5.2 LTS mit Django REST Framework und PostgreSQL 18, Python 3.14. Stellt die REST-API unter `/api/v1/` bereit und ist die einzige Komponente mit Zugriff auf die Datenbank.

## Aufbau

| Pfad | Inhalt |
| --- | --- |
| `config/` | Django-Projekt: Einstellungen aus Umgebungsvariablen (`settings.py`), URL-Routing (`urls.py`), Health-Endpunkt und JSON-404/500 (`views.py`), einheitliches Fehlerformat (`errors.py`, `exceptions.py`), Tests (`tests.py`) |
| `planning/` | App für Anwendungsdaten: Modell `PlanningSession`, Serializer, Views, URLs, Migrationen, Tests |
| `reference_data/` | App für Referenzdaten: Modelle `BenchmarkDataset` und `BenchmarkCase`, Import-Logik (`importer.py`), Management-Kommando `import_reference_cases`, nur lesbare API, Tests (`tests/`). Die Daten liegen in `data/travelplanner/`, Herkunft und Lizenz stehen in der [README dort](reference_data/data/travelplanner/README.md). |
| `requirements.txt` | exakt gepinnte Abhängigkeiten, inklusive transitiver Pakete |
| `Dockerfile` | Image für die Entwicklung; Compose bindet den Quellcode ein |

## Häufige Befehle

Alle Befehle laufen im Compose-Setup aus dem Repo-Root:

| Aufgabe | Befehl |
| --- | --- |
| Tests | `docker compose exec backend python manage.py test` |
| Migration erzeugen | `docker compose exec backend python manage.py makemigrations` |
| Migrationen anwenden | `docker compose exec backend python manage.py migrate` (läuft auch beim Start automatisch) |
| Referenzdaten importieren | `docker compose exec backend python manage.py import_reference_cases` |
| Django-Shell | `docker compose exec backend python manage.py shell` |

## Weiterführend

- [Einrichtung und Betrieb](../docs/DEVELOPMENT.md): Umgebungsvariablen, Start und Stopp, Import, Tests, Arbeit ohne Docker, häufige Fehler
- [API-Referenz](../docs/API.md): alle Endpunkte mit Beispielen und Fehlerfällen
- [API-Konventionen](../docs/API_CONVENTIONS.md): verbindliche Regeln für neue Endpunkte
- [Neuen Endpunkt ergänzen](../docs/EXTENDING.md): Modell, Migration, Serializer, View, URL, Test und Frontend
