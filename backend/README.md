# Backend

Django 5.2 LTS mit Django REST Framework und PostgreSQL 18, Python 3.14. Stellt die REST-API unter `/api/v1/` bereit und ist die einzige Komponente mit Zugriff auf die Datenbank. Im Backend laufen auch der Main-Agent und der Optimization Agent. Für die Flugsuche ruft es den [Journey Planner](../journey-planner/README.md) über HTTP auf.

## Aufbau

| Pfad | Inhalt |
| --- | --- |
| `config/` | Django-Projekt: Einstellungen aus Umgebungsvariablen (`settings.py`), URL-Routing (`urls.py`), Health-Endpunkt und JSON-404/500 (`views.py`), einheitliches Fehlerformat (`errors.py`, `exceptions.py`), Tests (`tests.py`) |
| `planning/` | App für Anwendungsdaten: Modelle `PlanningSession` (mit `trip_state`) und `Message`, Serializer, Views, URLs, Migrationen, Tests; Reise-State mit Validierung, Herkunft der Werte (`confirmed`, `inferred`), Rückflug und Reiseart (`return`, `trip_type`) und der Regel „die letzte Aussage gewinnt“ in `trip_state.py`; Chat-Endpunkt `GET`/`POST /api/v1/planning-sessions/{id}/messages/` und `GET /api/v1/planning-sessions/{id}/trip-state/` in `views.py` |
| `agent/` | Main-Agent und Optimization Agent, keine Django-App und ohne eigene Modelle: ein Gesprächsschritt in `main_agent.py` (alle Angaben einer Nachricht in einem Schritt übernehmen, auch Korrekturen und zurückgenommene Angaben, dann nächste Frage, Bestätigung einer geratenen Angabe, Antwort ohne neue Suche oder Suche und Erklärung), Prüfung der Ergebnisse von Hin- und Rückflug und gelockerte Suche in `optimizer.py`, versionierte Prompts in `prompts.py`, deutsche Texte aus den Daten in `texts.py` (Liste der Verbindungen und die Antworten ohne LLM), HTTP-Client für den Journey Planner in `planner_client.py`, Tests (`tests.py`) |
| `llm/` | alle LLM-Aufrufe: `get_llm_client()` liefert je nach `LLM_PROVIDER` den regelbasierten Offline-Ersatz (`offline`, Standard, ohne Zugangsdaten) oder den Gemini-Client (`gemini`); gemeinsame Schnittstelle `chat`/`structured` mit Wiederholungen und Logging in `base.py`, `chat` nimmt mit `fallback` den Text entgegen, den der Offline-Ersatz ausgibt; definierte Fehler für Timeout, Quota, Ausfall und ungültige Antwort; Fake-LLM mit festgelegten Antworten nur für Tests (`fake.py`) |
| `reference_data/` | App für Referenzdaten: Modelle `BenchmarkDataset` und `BenchmarkCase`, Import-Logik (`importer.py`), Management-Kommando `import_reference_cases`, nur lesbare API, Tests (`tests/`). Die Daten liegen in `data/travelplanner/`, Herkunft und Lizenz stehen in der [README dort](reference_data/data/travelplanner/README.md). |
| `requirements.txt` | exakt gepinnte Abhängigkeiten, inklusive transitiver Pakete |
| `Dockerfile` | Image für die Entwicklung; Compose bindet den Quellcode ein |

## Häufige Befehle

Alle Befehle laufen im Compose-Setup aus dem Repo-Root:

| Aufgabe | Befehl |
| --- | --- |
| Tests | `docker compose exec backend python manage.py test` |
| nur die Tests des Agenten | `docker compose exec backend python manage.py test agent` |
| Migration erzeugen | `docker compose exec backend python manage.py makemigrations` |
| Migrationen anwenden | `docker compose exec backend python manage.py migrate` (läuft auch beim Start automatisch) |
| Referenzdaten importieren | `docker compose exec backend python manage.py import_reference_cases` |
| Django-Shell | `docker compose exec backend python manage.py shell` |

## Weiterführend

- [Einrichtung und Betrieb](../docs/DEVELOPMENT.md): Umgebungsvariablen, Start und Stopp, Import, Tests, Arbeit ohne Docker, häufige Fehler
- [API-Referenz](../docs/API.md): alle Endpunkte mit Beispielen und Fehlerfällen, darunter der Chat-Endpunkt
- [Architektur des Prototyps](../docs/ARCHITECTURE_PROTOTYPE.md): Services, Kommunikation, Aufteilung zwischen Code und LLM
- [Suchauftrag](../docs/SEARCH_CONTRACT.md): Format zwischen Main-Agent und Journey Planner
- [API-Konventionen](../docs/API_CONVENTIONS.md): verbindliche Regeln für neue Endpunkte
- [Neuen Endpunkt ergänzen](../docs/EXTENDING.md): Modell, Migration, Serializer, View, URL, Test und Frontend
