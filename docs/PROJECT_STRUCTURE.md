# Projektaufbau und Datenhaltung

Stand: Grundgerüst, Tickets G01–G07 (#5–#11), und der erste Durchstich des Prototyps (#44): Chat → Main-Agent → Journey Planner → Beispielflüge. Was hier als **geplant** markiert ist, existiert noch nicht.

## Überblick

```text
Browser
  │  http://localhost:3000
  ▼
frontend         (Vite-Dev-Server, React + TypeScript)
  │  /api/…  wird weitergeleitet (Vite-Proxy)
  ▼
backend          (Django 5.2 + Django REST Framework, Port 8000)
  │              REST-API, Main-Agent, Optimization Agent, LLM-Client
  │
  ├── SQL über den Servicenamen "db" ──▶ db  (PostgreSQL 18, ohne Host-Port, Volume postgres-data)
  │
  │  POST /plan  Suchauftrag, siehe SEARCH_CONTRACT.md
  ▼
journey-planner  (Django 5.2 + Django REST Framework, Port 8001, ohne Datenbank, ohne LLM)
  │  Provider-Schnittstelle im selben Prozess
  ▼
Dummy-Provider   (erfundene Beispielflüge; geplant: Flight Service als eigener Service)
```

Alle vier Services laufen lokal über Docker Compose, siehe [DEVELOPMENT.md](DEVELOPMENT.md). Die Entscheidungen dahinter stehen in [ARCHITECTURE_PROTOTYPE.md](ARCHITECTURE_PROTOTYPE.md).

## Zusammenspiel

1. Der Browser lädt die Oberfläche vom Vite-Dev-Server auf Port 3000.
2. Die Oberfläche ruft die API mit relativen Pfaden wie `/api/v1/health/` auf, ausschließlich über [`frontend/src/api/client.ts`](../frontend/src/api/client.ts). Vite leitet alles unter `/api` an das Backend weiter. Im Container ist das Ziel `http://backend:8000`, gesetzt über `API_PROXY_TARGET`. Für den Browser liegen Oberfläche und API damit unter derselben Adresse, eine CORS-Konfiguration ist nicht nötig.
3. Django beantwortet die Anfrage und ist die einzige Komponente mit Zugriff auf PostgreSQL. Die Datenbank ist nur im internen Compose-Netz unter dem Namen `db` erreichbar.
4. Eine Chat-Nachricht (`POST /api/v1/planning-sessions/{id}/messages/`) verarbeitet der Main-Agent im Backend:
   - Das LLM liest die Reisedaten aus dem Text, der Code prüft jeden Wert und schreibt ihn in den Reise-State der Sitzung. Widerspricht eine neue Angabe einer älteren, gewinnt die letzte Aussage: Die ältere wird gelöscht und wieder abgefragt.
   - Fehlt eine Pflichtangabe, fragt der Agent danach, in der Reihenfolge Start, Ziel, Hinflug, Rückflug, Zahl der Reisenden. Der Rückflug entfällt bei „nur Hinflug“.
   - Ist eine Pflichtangabe nur geraten, lässt der Agent sie einmal bestätigen, bevor er sucht.
   - Hat sich seit der letzten Suche nichts geändert und enthält die Nachricht keine Reisedaten, antwortet der Agent, ohne noch einmal zu suchen.
   - Sonst schickt das Backend einen Suchauftrag an den Journey Planner (`JOURNEY_PLANNER_URL`, im Compose-Netz `http://journey-planner:8001`). Der Planner fragt seine Provider ab, filtert und sortiert. Bei Hin- und Rückflug sucht er beide Richtungen und antwortet mit Paaren aus Hin- und Rückflug.
   - Der Optimization Agent prüft die Treffer. Gibt es keine, sucht er mit einem gelockerten Kriterium noch einmal.
   - Den Antworttext schreibt das LLM aus den Fakten des Codes. Die Liste der Verbindungen mit Preisen und Zeiten hängt der Code an.
   - Nachricht, Antwort und Suchergebnis werden gespeichert.
5. Das Reiseformular der Oberfläche sendet seine geänderten Felder über denselben Endpunkt als `fields`, ohne Text. Nach dem Neuladen holt die Oberfläche den Reise-State mit `GET /api/v1/planning-sessions/{id}/trip-state/`.
6. Fehler kommen immer im [einheitlichen Fehlerformat](API_CONVENTIONS.md#4-fehlerformat) zurück. Der Client ordnet sie ein:
   - **nicht erreichbar:** keine Antwort oder 5xx vom Proxy
   - **vorübergehend nicht verfügbar:** `503`
   - **abgelehnt:** andere Statuscodes, bei Validierungsfehlern mit den betroffenen Feldern

Die Oberfläche zeigt dazu verständliche Meldungen.

Ein nicht erreichbarer Journey Planner ist für das Frontend kein Fehlerstatus: Der Agent antwortet mit einer Erklärung und dem Suchergebnis-Status `error`, siehe [API.md](API.md#post-apiv1planning-sessionsidmessages).

Startreihenfolge: Das Backend startet erst, wenn die Datenbank und der Journey Planner ihren Healthcheck bestehen. Ist sie beim Start trotzdem nicht erreichbar, etwa bei `docker compose restart`, startet Docker das Backend neu, bis es klappt (`restart: on-failure`). Vor dem Entwicklungsserver wendet das Backend offene Migrationen an.

## Verzeichnisse und Apps

| Pfad | Zuständigkeit |
| --- | --- |
| `backend/config/` | Django-Projekt: Einstellungen aus Umgebungsvariablen, URL-Routing, Health-Endpunkt, einheitliche Fehlerbehandlung (`errors.py`, `exceptions.py`) |
| `backend/planning/` | App für **Anwendungsdaten**: Modelle `PlanningSession` und `Message` mit API und Tests; Reise-State pro Sitzung mit Validierung und der Regel „die letzte Aussage gewinnt“ (`trip_state.py`); Chat-Endpunkt `…/messages/` und Reise-State-Endpunkt `…/trip-state/` |
| `backend/agent/` | **Main-Agent** (`main_agent.py`, ein Gesprächsschritt), **Optimization Agent** (`optimizer.py`), Prompts (`prompts.py`), deutsche Antworttexte aus den Daten für die Liste der Verbindungen und als Antwort ohne LLM (`texts.py`), HTTP-Client für den Journey Planner (`planner_client.py`), Tests |
| `backend/llm/` | einzige Stelle für LLM-Aufrufe: gemeinsame Schnittstelle, Gemini-Client, regelbasierter Offline-Ersatz (Standard), Fake-LLM für Tests, Tests |
| `backend/reference_data/` | App für **Referenzdaten**: historische TravelPlanner-Fälle, Import-Kommando, nur lesbare API, Tests. Die Daten liegen in `data/travelplanner/`. |
| `backend/requirements.txt` | exakt gepinnte Python-Abhängigkeiten |
| `journey-planner/` | **Journey Planner** als eigener Service (JP01 #38), siehe [README dort](../journey-planner/README.md): Suchauftrag prüfen (`planner/contract.py`), Provider abfragen, filtern, sortieren und bei Hin- und Rückflug Paare bilden (`planner/service.py`), Endpunkte `POST /plan` und `GET /health` (`planner/views.py`), Tests |
| `journey-planner/planner/providers/` | Provider-Schnittstelle `TransportProvider` (`base.py`), Dummy-Provider mit erfundenen Beispielflügen zwischen 30 europäischen Städten (`dummy_flights.py`), Auswahl über `FLIGHT_PROVIDER` (`__init__.py`). Hier wird der echte Flight Service angebunden. |
| `frontend/src/api/` | zentraler API-Client mit allen API-Pfaden, Typen und Fehlerklassen |
| `frontend/src/features/` | Seiten: V1-Startseite `/` und Workspace `/chat` in `v1/`, API-Chat `Chat.tsx` unter `/chat?view=classic` und Systemstatus unter `/status` |
| `frontend/src/features/chat/` | Bausteine der Chat-Seite: Reiseformular (`TripForm.tsx`), Ergebniskarten mit Hin- und Rückflug (`Results.tsx`), Entwurf des Formulars und Abgleich mit dem Reise-State (`tripDraft.ts`), Formatierung (`format.ts`) |
| `frontend/src/app/`, `frontend/src/components/` | Routing, Layout und gemeinsame Bausteine |
| `frontend/src/mocks/` | Entwicklungs-Mock für `/api/v1/` mit Service Worker und deterministischen Szenarien, siehe [Frontend ohne Backend](DEVELOPMENT.md#frontend-ohne-backend) |
| `frontend/tests/` | Unit- und React-Komponententests (Vitest), mit denselben Mock-Handlern wie im Entwicklungsmodus |
| `journey-planner/domain_services/` | DS1-Vertrag zu den Transportservices (DS1 #21): Python-Paket `domain_services` und `openapi.yaml`, generischer Aufrufer, Mock-Services für Flug, Bahn und Taxi, Tests in `journey-planner/tests/`. Siehe [DS1_CONTRACT.md](../journey-planner/docs/DS1_CONTRACT.md). Der Planner nutzt ihn noch nicht. |
| `docs/` | Projekt- und Entwicklerdokumentation |
| `docs/contracts/search-v1/` | Beispiele für den Suchauftrag und seine Antworten, für nur den Hinflug und für Hin- und Rückflug; die Tests von Backend und Journey Planner laden genau diese Dateien |
| `compose.yaml` | lokale Entwicklungsumgebung mit `frontend`, `backend`, `journey-planner` und `db` |
| `.env.example` | lokale Beispielkonfiguration; die eigene `.env` wird nicht eingecheckt |

**Geplant:** Weitere Services des Prototyps kommen wie der Journey Planner als eigene Verzeichnisse auf oberster Ebene und als weitere Compose-Services hinzu (IN01 #29, IN02 #42). Der nächste ist der Flight Service mit Mock-Adapter (DS6 #41).

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
- `backend/requirements.txt` und `journey-planner/requirements.txt` (pip, exakt gepinnt; der Planner nutzt dieselben Versionen von Django und DRF wie das Backend)
- `frontend/package-lock.json` (npm)
- die Image-Tags in den Dockerfiles und in `compose.yaml`: `python:3.14.10-slim`, `node:24.22.2-alpine`, `postgres:18.6`, `nginx:1.30.6-alpine`

Bewusst nicht gewählt: Python 3.15 und Node.js 26 waren zum Projektstart erst wenige Wochen alt, Django 6.x hat kürzere Supportzeiträume als 5.2 LTS.

## Datenhaltung

Es gibt **eine gemeinsame PostgreSQL-Datenbank**, auf die nur das Backend zugreift. Der Journey Planner speichert nichts. Die Datenarten sind darin logisch über getrennte Django-Apps und damit getrennte Tabellen voneinander abgegrenzt:

| Datenart | Wo | Eigenschaften |
| --- | --- | --- |
| Anwendungsdaten | App `planning` | Von Nutzerinnen und Nutzern erzeugt: Planungssitzungen mit ihrem Reise-State (JSON-Feld `trip_state`) und die Chat-Nachrichten samt Suchergebnis (Modell `Message`). Über die API les- und schreibbar. |
| Referenzdaten | App `reference_data` | Historische TravelPlanner-Benchmark-Fälle: vollständiger Datensatz, 1.225 Fälle, im Repository unter `backend/reference_data/data/travelplanner/`. Nur per Management-Kommando `import_reference_cases` importierbar, über die API ausschließlich lesbar. Ein Import verändert keine Anwendungsdaten. |
| Testdaten | eigene Datenbank `test_traveller` | Django legt sie für jeden Testlauf an und löscht sie danach. Die Tests erzeugen ihre Daten selbst, auch eigene kleine Importdateien. Entwicklungsdaten bleiben unberührt. |

Die Entwicklungsdaten liegen im Docker-Volume `postgres-data` und überstehen `docker compose down`. Erst `docker compose down -v` löscht sie.

Getrennte PostgreSQL-Schemas wurden verworfen: Django unterstützt sie nur über Umwege (`search_path`, manuelle Tabellennamen), ohne dass der Prototyp davon profitiert.

## Lokale Konfiguration

Zugangsdaten und lokale Einstellungen liegen in der `.env` im Repo-Root, die nicht eingecheckt wird. Eingecheckt ist nur [`.env.example`](../.env.example) mit funktionierenden, unkritischen Werten. Abhängigkeiten (`node_modules/`, `.venv/`), Build-Ausgaben und Testberichte sind über `.gitignore` ausgeschlossen. Alle Variablen erklärt [DEVELOPMENT.md](DEVELOPMENT.md#umgebungsvariablen).

## Grenzen des Grundgerüsts

Das Grundgerüst mit dem ersten Durchstich ist eine lokale Entwicklungsumgebung und kein auslieferbares System.

- **Nur Entwicklungsbetrieb:** Es laufen Djangos Entwicklungsserver (Backend und Journey Planner) und der Vite-Dev-Server. Für ein Deployment fehlen ein Produktions-Webserver (z. B. gunicorn), HTTPS und ein Reverse Proxy für `/api`. Das Nginx-Image des Frontends (`docker build frontend`) enthält nur die statische Oberfläche und leitet `/api` nicht weiter.
- **Keine Accounts:** Alle Endpunkte sind ohne Anmeldung erreichbar, die Ports sind nur an `localhost` gebunden.
- **Fachlich ein schmaler Durchstich:** Der Chat fragt Start, Ziel, Hinflug, Rückflug und Zahl der Reisenden ab, optional Budget und Umstiege, und sucht dann Flüge: Hin- und Rückflug als Paar oder nur den Hinflug. Mehr kann er nicht. Auf Fragen nach Hotels, Bahn, Bus, Mietwagen, Buchung oder Wetter soll der Agent mit dem echten LLM sagen, dass er das nicht kann.
- **Nur Europa, keine echten Flugdaten:** Der Journey Planner liefert erfundene Beispielflüge zwischen 30 europäischen Städten; andere Orte lehnt der Agent mit Begründung ab. Die Liste steht unter `GET /api/v1/places/`. Vier Strecken ab Berlin (Lissabon, Barcelona, Rom, London) sind von Hand festgelegt, alle anderen werden nach festen Regeln erzeugt; dieselbe Anfrage ergibt immer dieselben Flüge. Es gibt keinen Reiseanbieter und keinen Flight Service.
- **Standardmäßig kein echtes LLM:** Mit `LLM_PROVIDER=offline` erkennt ein regelbasierter Ersatz nur feste Satzmuster und antwortet mit festen deutschen Texten. Der Gemini-Client ist vorhanden; mit `gemini-3.6-flash` sind acht Testgespräche über die Gemini-Plattform geführt worden. Einrichtung und Stand der Prüfung stehen in [DEVELOPMENT.md](DEVELOPMENT.md#llm-zugang).
- **API-Planungsoberfläche.** `/chat?view=classic` zeigt zwei Spalten, links den Chat, rechts die Reisedaten als Formular: Start, Ziel, Hinflug, Rückflug, „One-way“, Reisende, Budget und Umstiege. Felder tragen die Kennzeichen „needed“ (fehlt für die Suche), „assumed“ (vom Agenten angenommen) und „unsaved“ (noch nicht übernommen). „Apply changes“ sendet alle geänderten Felder in einem Aufruf. Die Ergebniskarten zeigen Hin- und Rückflug. Die Sitzung merkt sich der Browser, nach dem Neuladen erscheinen Verlauf und Reisedaten wieder; nicht übernommene Änderungen im Formular gehen dabei verloren. Eine Liste früherer Sitzungen gibt es nicht.
- **Referenzdaten nur lesend:** Sie werden nicht normalisiert, die strukturierte Fassung der Referenzinformationen (`*_ref_info.jsonl`) ist nicht enthalten, und ein Import löscht keine verschwundenen Fälle.
- **Tests:** Es gibt Tests für Backend und Journey Planner und Frontend-Unit-Tests, aber keine Browser- oder End-to-End-Tests. Es gibt keine automatische Prüfung (CI) bei Pull Requests, die Tests laufen lokal. Was bisher wie geprüft wurde, steht in [DEVELOPMENT.md](DEVELOPMENT.md#tests-typprüfung-build).
- **Sprachen:** Fehlermeldungen der API und Texte der Oberfläche sind englisch. Die Liste der Verbindungen, die Hinweise des Optimization Agent und die Antworten ohne LLM sind deutsch, die Doku ebenfalls. Mit dem echten LLM antwortet der Agent in der Sprache der Nachricht.

## Umgesetzt aus dem Prototyp

Vom 2-Wochen-Prototyp (#44) steht der erste Durchstich:
- **LLM-Client** mit Gemini-Client, Offline-Ersatz und Fake-LLM für Tests (AG02 #31)
- **Reise-State** pro Planungssitzung (AG03 #32)
- **Suchauftrag** Main-Agent → Journey Planner (AG04 #33), siehe [SEARCH_CONTRACT.md](SEARCH_CONTRACT.md)
- **Main-Agent** im Backend mit dem Chat-Endpunkt `/api/v1/planning-sessions/{id}/messages/` (AG08 #37): fragt nach, lässt geratene Pflichtangaben bestätigen, sucht und erklärt
- **Optimization Agent** in kleiner Form: prüft Ergebnisse und sucht bei „keine Treffer“ mit einem gelockerten Kriterium erneut
- **Journey Planner** als eigener Service mit Provider-Schnittstelle und Dummy-Provider für 30 europäische Städte (JP01 #38)
- **Compose** mit dem Service `journey-planner` (IN02 #42), gebaut und gestartet geprüft
- **Hin- und Rückflug** durch alle Schichten: Reise-State, Agent, Suchauftrag, Journey Planner und Oberfläche
- **API-Chat** im Frontend unter `/chat?view=classic` mit Chat und Reiseformular

Die Architektur beschreibt [ARCHITECTURE_PROTOTYPE.md](ARCHITECTURE_PROTOTYPE.md) (IN01 #29).

## Geplant

Noch nicht vorhanden:
- **Flight Service** als eigener Service (DS6 #41) und die Anbindung des Planners an den DS1-Vertrag (#21, liegt in `journey-planner/domain_services/`). Zuständig für die Services ist die Seite der Domain-Services. Die Anbindung an den Planner beschreibt die [README des Planners](../journey-planner/README.md#einen-echten-verkehrs-service-anbinden) (JP02 #39).
- **Echte Anbieter-APIs** hinter den Verkehrs-Services
- **Weitere Verkehrsmittel** wie Bahn, Bus, Auto und Fähre
- **Hotels**
- **Mehrere Reiseziele**
