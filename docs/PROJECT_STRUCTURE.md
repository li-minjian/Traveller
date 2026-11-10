# Projektaufbau und Datenhaltung

Stand: Grundgerüst, Tickets G01–G07 (#5–#11). Was hier als **geplant** markiert ist, existiert noch nicht.

## Überblick

```text
Browser
  │  http://localhost:3000
  ▼
frontend  (Vite-Dev-Server, React + TypeScript)
  │  /api/…  wird weitergeleitet (Vite-Proxy)
  ▼
backend   (Django 5.2 + Django REST Framework, Port 8000)
  │  SQL über den Servicenamen "db"
  ▼
db        (PostgreSQL 18, ohne Host-Port, Volume postgres-data)
```

Alle drei Teile laufen lokal als Docker-Compose-Services, siehe [DEVELOPMENT.md](DEVELOPMENT.md).

## Zusammenspiel

1. Der Browser lädt die Oberfläche vom Vite-Dev-Server auf Port 3000.
2. Die Oberfläche ruft die API mit relativen Pfaden wie `/api/v1/health/` auf, ausschließlich über [`frontend/src/api/client.ts`](../frontend/src/api/client.ts). Vite leitet alles unter `/api` an das Backend weiter. Im Container ist das Ziel `http://backend:8000`, gesetzt über `API_PROXY_TARGET`. Für den Browser liegen Oberfläche und API damit unter derselben Adresse, eine CORS-Konfiguration ist nicht nötig.
3. Django beantwortet die Anfrage und ist die einzige Komponente mit Zugriff auf PostgreSQL. Die Datenbank ist nur im internen Compose-Netz unter dem Namen `db` erreichbar.
4. Fehler kommen immer im [einheitlichen Fehlerformat](API_CONVENTIONS.md#4-fehlerformat) zurück. Der Client ordnet sie ein:
   - **nicht erreichbar:** keine Antwort oder 5xx vom Proxy
   - **vorübergehend nicht verfügbar:** `503`
   - **abgelehnt:** andere Statuscodes, bei Validierungsfehlern mit den betroffenen Feldern

Die Oberfläche zeigt dazu verständliche Meldungen.

Startreihenfolge: Das Backend startet erst, wenn die Datenbank ihren Healthcheck besteht. Ist sie beim Start trotzdem nicht erreichbar, etwa bei `docker compose restart`, startet Docker das Backend neu, bis es klappt (`restart: on-failure`). Vor dem Entwicklungsserver wendet das Backend offene Migrationen an.

## Verzeichnisse und Apps

| Pfad | Zuständigkeit |
| --- | --- |
| `backend/config/` | Django-Projekt: Einstellungen aus Umgebungsvariablen, URL-Routing, Health-Endpunkt, einheitliche Fehlerbehandlung (`errors.py`, `exceptions.py`) |
| `backend/planning/` | App für **Anwendungsdaten**: Modell `PlanningSession` mit API und Tests |
| `backend/reference_data/` | App für **Referenzdaten**: historische TravelPlanner-Fälle, Import-Kommando, nur lesbare API, Tests. Die Daten liegen in `data/travelplanner/`. |
| `backend/requirements.txt` | exakt gepinnte Python-Abhängigkeiten |
| `frontend/src/api/` | zentraler API-Client mit allen API-Pfaden, Typen und Fehlerklassen |
| `frontend/src/features/` | Seiten; bisher die Statusseite `SystemStatus.tsx` |
| `frontend/src/app/`, `frontend/src/components/` | Routing, Layout und gemeinsame Bausteine |
| `frontend/tests/` | Unit-Tests (Vitest) |
| `docs/` | Projekt- und Entwicklerdokumentation |
| `compose.yaml` | lokale Entwicklungsumgebung mit `frontend`, `backend` und `db` |
| `.env.example` | lokale Beispielkonfiguration; die eigene `.env` wird nicht eingecheckt |

**Geplant:** Die Services des Prototyps kommen als eigene Verzeichnisse auf oberster Ebene und als weitere Compose-Services hinzu (IN01 #29, IN02 #42). Dazu gehören der Journey Planner (JP01 #38) und der Flight Service mit Mock-Adapter (DS6 #41).

## Gewählte Versionen

| Komponente | Version | Begründung |
| --- | --- | --- |
| Python | 3.14 | Seit Oktober 2025 stabil, Support bis Oktober 2030; von Django 5.2, DRF und psycopg unterstützt. |
| Django | 5.2 LTS | Long-Term-Support mit Sicherheitsupdates bis April 2028; deckt die Projektlaufzeit sicher ab. |
| Django REST Framework | 3.18 | Aktuelle Version, offiziell kompatibel mit Django 5.2. |
| psycopg | 3.3 | PostgreSQL-Treiber für Django (psycopg 3). |
| PostgreSQL | 18 | Aktuelle Hauptversion, Support bis November 2030. |
| Node.js | 24 LTS | Grundlage des Frontends; Support bis April 2028. |
| React / TypeScript / Vite | 19.2 / 5.9 / 8.3 | Siehe `frontend/package.json`. |

Die exakten Versionen stehen dort, wo installiert wird:
- `backend/requirements.txt` (pip, exakt gepinnt)
- `frontend/package-lock.json` (npm)
- die Image-Tags in den Dockerfiles und in `compose.yaml`: `python:3.14.10-slim`, `node:24.22.2-alpine`, `postgres:18.6`, `nginx:1.30.6-alpine`

Bewusst nicht gewählt: Python 3.15 und Node.js 26 waren zum Projektstart erst wenige Wochen alt, Django 6.x hat kürzere Supportzeiträume als 5.2 LTS.

## Datenhaltung

Es gibt **eine gemeinsame PostgreSQL-Datenbank**. Die Datenarten sind darin logisch über getrennte Django-Apps und damit getrennte Tabellen voneinander abgegrenzt:

| Datenart | Wo | Eigenschaften |
| --- | --- | --- |
| Anwendungsdaten | App `planning` | Von Nutzerinnen und Nutzern erzeugt, z. B. Planungssitzungen. Über die API les- und schreibbar. |
| Referenzdaten | App `reference_data` | Historische TravelPlanner-Benchmark-Fälle: vollständiger Datensatz, 1.225 Fälle, im Repository unter `backend/reference_data/data/travelplanner/`. Nur per Management-Kommando `import_reference_cases` importierbar, über die API ausschließlich lesbar. Ein Import verändert keine Anwendungsdaten. |
| Testdaten | eigene Datenbank `test_traveller` | Django legt sie für jeden Testlauf an und löscht sie danach. Die Tests erzeugen ihre Daten selbst, auch eigene kleine Importdateien. Entwicklungsdaten bleiben unberührt. |

Die Entwicklungsdaten liegen im Docker-Volume `postgres-data` und überstehen `docker compose down`. Erst `docker compose down -v` löscht sie.

Getrennte PostgreSQL-Schemas wurden verworfen: Django unterstützt sie nur über Umwege (`search_path`, manuelle Tabellennamen), ohne dass der Prototyp davon profitiert.

## Lokale Konfiguration

Zugangsdaten und lokale Einstellungen liegen in der `.env` im Repo-Root, die nicht eingecheckt wird. Eingecheckt ist nur [`.env.example`](../.env.example) mit funktionierenden, unkritischen Werten. Abhängigkeiten (`node_modules/`, `.venv/`), Build-Ausgaben und Testberichte sind über `.gitignore` ausgeschlossen. Alle Variablen erklärt [DEVELOPMENT.md](DEVELOPMENT.md#umgebungsvariablen).

## Grenzen des Grundgerüsts

Das Grundgerüst ist eine lokale Entwicklungsumgebung und kein auslieferbares System.

- **Nur Entwicklungsbetrieb:** Es laufen Djangos Entwicklungsserver und der Vite-Dev-Server. Für ein Deployment fehlen ein Produktions-Webserver (z. B. gunicorn), HTTPS und ein Reverse Proxy für `/api`. Das Nginx-Image des Frontends (`docker build frontend`) enthält nur die statische Oberfläche und leitet `/api` nicht weiter.
- **Keine Accounts:** Alle Endpunkte sind ohne Anmeldung erreichbar, die Ports sind nur an `localhost` gebunden.
- **Fachlich minimal:** Eine Planungssitzung hat nur einen Titel. Es gibt noch keine Reisedaten, keinen Chat, keine Agenten, kein LLM, keine Reiseanbieter und keine Suche.
- **Referenzdaten nur lesend:** Sie werden nicht normalisiert, die strukturierte Fassung der Referenzinformationen (`*_ref_info.jsonl`) ist nicht enthalten, und ein Import löscht keine verschwundenen Fälle.
- **Tests:** Es gibt Backend-Tests und Frontend-Unit-Tests, aber keine Browser- oder End-to-End-Tests. Es gibt keine automatische Prüfung (CI) bei Pull Requests, die Tests laufen lokal.
- **Englische Meldungen:** Fehlermeldungen der API und Texte der Oberfläche sind englisch, die Doku ist deutsch.

## Geplant (nicht Teil des Grundgerüsts)

Der 2-Wochen-Prototyp (#44) baut auf diesem Grundgerüst auf:
- **Main-Agent im Backend** (AG01–AG08): LLM-Anbindung, Reise-State pro Planungssitzung, Chat-Endpoint `/api/v1/planning-sessions/{id}/messages/`
- **Journey Planner** als eigener Service (JP01–JP03)
- **Flight Service** mit Mock-Adapter (DS6)

Compose wird dafür erweitert (IN02). Die Architektur dazu legt IN01 (#29) fest.
