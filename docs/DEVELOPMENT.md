# Einrichtung und Betrieb

Wie man Traveller lokal einrichtet, startet, prüft und zurücksetzt. Wie das Projekt aufgebaut ist, beschreibt [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).

## Voraussetzungen

- **Docker** mit dem Compose-Plugin (`docker compose`, nicht das alte `docker-compose`).
- **Git**.
- Freie Ports **3000** (Frontend), **8000** (Backend) und **8001** (Journey Planner) auf `localhost`.
- Nur für die Arbeit außerhalb von Docker: Python 3.14 (3.13 geht auch) und Node.js 24 (22.12 oder neuer geht auch).

Der erste Build braucht Internet für die Images und Pakete, der laufende Betrieb nicht. Die Referenzdaten liegen im Repository.

## Erstes Einrichten

```sh
git clone https://github.com/li-minjian/Traveller.git
cd Traveller
cp .env.example .env                                                  # lokale Konfiguration
docker compose up --build -d                                          # bauen und starten
docker compose ps                                                     # nach ~30 s: alle vier "healthy"
docker compose exec backend python manage.py import_reference_cases   # Referenzdaten laden
```

Danach öffnet [http://localhost:3000](http://localhost:3000) die Traveller-Startseite. Der Workspace liegt unter `/chat`. Die Statusseite [http://localhost:3000/status](http://localhost:3000/status) zeigt „Connected“ und „1,225 cases imported“. Die Migrationen laufen beim Start des Backends automatisch.

| Service | Adresse | Inhalt |
| --- | --- | --- |
| `frontend` | [http://localhost:3000](http://localhost:3000) | Vite-Dev-Server mit Startseite `/`, Workspace `/chat`, API-Chat `/chat?view=classic` und Statusseite `/status`. Leitet `/api` an das Backend weiter. |
| `backend` | [http://localhost:8000/api/v1/health/](http://localhost:8000/api/v1/health/) | Django-Entwicklungsserver mit der REST-API, dem Main-Agent und dem Optimization Agent |
| `journey-planner` | [http://localhost:8001/health](http://localhost:8001/health) | Django-Entwicklungsserver des Journey Planners mit `POST /plan`; ohne Datenbank und ohne LLM, liefert erfundene Beispielflüge zwischen 30 europäischen Städten |
| `db` | kein Host-Port | PostgreSQL 18, nur im Compose-Netz unter dem Namen `db` erreichbar |

Das Backend startet erst, wenn `db` und `journey-planner` ihren Healthcheck bestehen. Die Pfade des Planners haben, anders als die der Backend-API, keinen Schrägstrich am Ende.

**Stand der Prüfung:** Das Compose-Setup mit allen vier Services wurde am 18.11.2026 unter Windows frisch gebaut und gestartet; alle Services wurden `healthy`, und ein Gespräch im Chat lief mit dem echten LLM bis zu den Flugvarianten durch. Diese Prüfung fand vor der Erweiterung um den Rückflug statt.

## Umgebungsvariablen

Alle Werte stehen in der `.env` im Repo-Root. [`.env.example`](../.env.example) enthält funktionierende, unkritische Werte für die lokale Entwicklung. Die `.env` wird nie eingecheckt, denn dort landen später auch echte Zugangsdaten, etwa für das LLM. Echte Umgebungsvariablen haben Vorrang vor der `.env`.

| Variable | Pflicht | Standard | Bedeutung |
| --- | --- | --- | --- |
| `DJANGO_SECRET_KEY` | ja | – | Geheimer Schlüssel von Django |
| `DJANGO_DEBUG` | nein | `false` | `true` nur lokal |
| `DJANGO_ALLOWED_HOSTS` | nein | `localhost,127.0.0.1` | Hostnamen, unter denen das Backend antwortet, kommagetrennt |
| `POSTGRES_DB` | ja | – | Name der Datenbank |
| `POSTGRES_USER` | ja | – | Datenbankbenutzer |
| `POSTGRES_PASSWORD` | ja | – | Passwort des Datenbankbenutzers |
| `POSTGRES_HOST` | nein | `localhost` | Host der Datenbank; Compose setzt für das Backend selbst `db` |
| `POSTGRES_PORT` | nein | `5432` | Port der Datenbank; Compose setzt `5432` |
| `LLM_PROVIDER` | nein | `offline` | `offline` (regelbasierter Ersatz, ohne Zugangsdaten und ohne Netz) oder `gemini` (echtes LLM) |
| `LLM_API_KEY` | bei `gemini` | – | API-Schlüssel für Gemini; nur in der eigenen `.env` |
| `LLM_MODEL` | nein | `gemini-3.6-flash` | Modellname bei `gemini`. Zur Wahl des Modells siehe [LLM-Zugang](#llm-zugang). |
| `LLM_ENDPOINT` | nein | `https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent` | Adresse des Gemini-Aufrufs mit dem Platzhalter `{model}`. Standard ist die Gemini-Plattform von Google Cloud. |
| `LLM_TIMEOUT_SECONDS` | nein | `20` | Timeout eines LLM-Aufrufs |
| `LLM_MAX_ATTEMPTS` | nein | `2` | Versuche pro Aufruf bei Timeout, Ausfall oder unbrauchbarer Antwort |
| `OPTIMIZATION_AGENT_ENABLED` | nein | `true` | `false` schaltet den Optimization Agent ab: keine Prüfung der Ergebnisse, keine gelockerte Suche bei „keine Treffer“ |
| `JOURNEY_PLANNER_URL` | nein | `http://localhost:8001` | Adresse des Journey Planners aus Sicht des Backends; Compose setzt `http://journey-planner:8001` |
| `JOURNEY_PLANNER_TIMEOUT_SECONDS` | nein | `10` | Timeout eines Aufrufs des Journey Planners |
| `FLIGHT_PROVIDER` | nein | `dummy` | Woher der Journey Planner Flüge bekommt. Bisher gibt es nur `dummy` (erfundene Beispielflüge). |
| `WATCH_POLLING` | nein | `false` | `true`, falls Dateiänderungen den Frontend-Container nicht erreichen. Unter Windows mit Docker ist das nötig, siehe [Häufige Fehler](#häufige-fehler). |
| `API_PROXY_TARGET` | nein | `http://localhost:8000` | Ziel des Vite-Proxys für `/api`; Compose setzt `http://backend:8000` |

Die Postgres-Variablen liest auch das offizielle `postgres`-Image, deshalb teilen sich Datenbank und Backend dieselbe `.env`.

`FLIGHT_PROVIDER` liest nur der Journey Planner. Er bekommt nicht die ganze `.env`, sondern nur die Variablen, die `compose.yaml` bei `journey-planner` unter `environment` nennt: `FLIGHT_PROVIDER` und `DJANGO_DEBUG`. Alle anderen Variablen der Tabelle außer `WATCH_POLLING` und `API_PROXY_TARGET` liest das Backend.

- **Fehlt eine Pflichtvariable** oder ist sie leer, bricht Django beim Start ab, zum Beispiel mit `Environment variable DJANGO_SECRET_KEY is not set.`
- **Ist eine optionale Variable leer**, gilt ihr Standardwert.
- **Ein unbekannter Wert** für `LLM_PROVIDER` oder `FLIGHT_PROVIDER` fällt erst beim ersten Aufruf auf, nicht beim Start, ebenso `LLM_PROVIDER=gemini` ohne `LLM_API_KEY`. Der Chat-Endpunkt antwortet dann mit `500`, beim Planner meldet der Chat einen Ausfall der Flugsuche. Die Ursache steht im Log des jeweiligen Service.
- **Neue Variablen** kommen mit unkritischem Beispielwert in `.env.example` und in diese Tabelle.

### LLM-Zugang

Ohne weitere Einstellung arbeitet das Backend mit `LLM_PROVIDER=offline`. Das ist kein LLM, sondern ein regelbasierter Ersatz in [`backend/llm/offline.py`](../backend/llm/offline.py): Er erkennt einige feste Muster in deutschen und englischen Sätzen, etwa „von Berlin nach Lissabon“, Datumsangaben wie „20. Mai“ oder „20.05.2027“, „2 Personen“, „300 € pro Person“ und „direkt“. Ein Datum nach „zurück“, „Rückflug“, „Rückreise“, „bis“, „return“ oder „back“ liest er als Rückflug, ebenso eine bloße Datumsangabe als Antwort auf die Frage nach dem Rückflug. „Nur Hinflug“, „ohne Rückflug“ oder „one way“ liest er als Reise ohne Rückflug. Eine Nachricht, die nur aus einer Zustimmung besteht („ja“, „passt“, „genau“, „ok“), liest er als Bestätigung. Als Antwort gibt er den deutschen Text aus, den der Agent ohne LLM sagen würde (`backend/agent/texts.py`); der Agent reicht ihn bei jedem Aufruf als `fallback` mit. Damit läuft der Chat ohne Zugangsdaten und ohne Netz. Freie Formulierungen versteht der Ersatz nicht, er rät keine Werte, erkennt keine Rücknahme wie „Budget ist mir egal“ und antwortet immer deutsch. Er stuft jede Nachricht als Reisedaten ein; deshalb sucht der Agent mit ihm nach jeder Nachricht erneut, sobald alle Pflichtangaben da sind.

Für das echte LLM in der eigenen `.env` `LLM_PROVIDER=gemini` und `LLM_API_KEY=…` setzen, danach `docker compose up -d`. Der Schlüssel gehört nie ins Repository. Mit Gemini liest das LLM jede Nachricht und schreibt die Antworten selbst, in der Sprache der Nachricht. Die Liste der Verbindungen hängt weiterhin der Code an.

**Modell:** Standard ist `gemini-3.6-flash`. Das kleinere `gemini-3.5-flash-lite` hat in echten Testgesprächen Eingaben wie „um Ostern rum“ oder „ja passt“ übergangen. Strukturierte Ausgaben fordert der Client mit `temperature: 0` an, damit dieselbe Nachricht möglichst gleich gelesen wird.

**Stand der Prüfung:** Am 16.11.2026 liefen acht festgelegte Testgespräche mit `gemini-3.6-flash` über einen Schlüssel der Gemini-Plattform, und das Modell hat alle acht bewältigt. Zusammen waren das 67 LLM-Aufrufe mit rund 76.000 Eingabe- und 4.000 Ausgabe-Tokens. Das war vor der Erweiterung um den Rückflug.

Am 18.11.2026 liefen mit `gemini-3.6-flash` acht festgelegte Gespräche, die auf Korrekturen zielen: ein Ort erst als Start und dann als Ziel, Start und Ziel getauscht, Rückflug vor dem Hinflug, Grenzen zurückgenommen, Hinflug hinter den Rückflug verschoben, Aufenthaltsdauer statt Rückflugdatum, eine vage Änderung über einem festen Wert. In keinem Schritt ging ein Wert verloren, den das LLM geliefert hat: Jeder stand danach im Reise-State oder war mit einem Grund abgelehnt, den der Agent genannt hat.

Die Gespräche sind nicht Teil der automatischen Tests; diese brauchen kein echtes LLM.

So entsteht der Zugang über das Guthaben in Google Cloud (AG01 #30):

1. In der Google-Cloud-Konsole ein eigenes Projekt anlegen und unter „Abrechnung“ mit dem Rechnungskonto verknüpfen, auf dem das Guthaben liegt.
2. Unter „Agent Platform“ → „API-Schlüssel abrufen“ zuerst „APIs aktivieren“, dann „Create API Key“. Google legt dabei ein Dienstkonto `vertex-express@<projekt>.iam.gserviceaccount.com` an.
3. Unter „IAM & Verwaltung“ → „IAM“ → „Zugriffsrechte erteilen“ diesem Dienstkonto die Rolle „Agent Platform User“ geben. Ohne sie antwortet Google mit `403 Permission 'aiplatform.endpoints.predict' denied`.
4. Den Schlüssel in der eigenen `.env` als `LLM_API_KEY` eintragen.

Ein Schlüssel der Gemini API aus AI Studio braucht eine andere Adresse: `LLM_ENDPOINT=https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`. Diese Variante ist nicht geprüft.

Das Fake-LLM mit festgelegten Antworten (`backend/llm/fake.py`) ist nur für Tests gedacht und lässt sich nicht über `LLM_PROVIDER` wählen.

## Starten, stoppen, Logs

| Aufgabe | Befehl |
| --- | --- |
| alles starten | `docker compose up -d` |
| nach Änderung an einer `requirements.txt` (`backend/`, `journey-planner/`) oder einem Dockerfile | `docker compose up --build -d` |
| Status ansehen | `docker compose ps` |
| Logs verfolgen | `docker compose logs -f backend`, ebenso für `frontend`, `journey-planner` und `db` |
| einen Service neu starten | `docker compose restart backend` |
| Django-Befehl ausführen | `docker compose exec backend python manage.py <befehl>` |
| Datenbank-Konsole | `docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'` |
| stoppen, Daten behalten | `docker compose stop` oder `docker compose down` |

Code in `frontend/`, `backend/` und `journey-planner/` ist in die Container eingebunden. Änderungen greifen sofort und ohne Rebuild: Django startet neu, Vite lädt den Browser neu. Die Vertragsbeispiele in `docs/contracts/` sind in Backend und Planner nur lesend unter `/docs/contracts` eingebunden, weil die Tests beider Services sie laden. Ändert sich `frontend/package-lock.json`, installiert der Frontend-Container beim nächsten Start (`docker compose restart frontend`) die Abhängigkeiten automatisch neu.

### Stoppen oder Daten löschen

| Befehl | Container | Datenbankdaten |
| --- | --- | --- |
| `docker compose stop` | angehalten | **bleiben** |
| `docker compose down` | entfernt | **bleiben** (Volume `postgres-data`) |
| `docker compose down -v` | entfernt | **gelöscht**, ebenso das Volume `frontend-node-modules` |

`down -v` löscht alle Planungssitzungen mit ihren Nachrichten und die importierten Referenzdaten unwiderruflich. Danach startet das Backend mit einer leeren Datenbank. Die Migrationen laufen beim Start automatisch, die Referenzdaten müssen neu importiert werden.

## Migrationen

- **Anwenden:** Beim Start wendet das Backend offene Migrationen automatisch an. Ohne Neustart geht es mit `docker compose exec backend python manage.py migrate`.
- **Erzeugen:** Nach einer Modelländerung erzeugt `docker compose exec backend python manage.py makemigrations` die Migration. Sie landet über den Bind-Mount in `backend/<app>/migrations/` und wird zusammen mit der Modelländerung eingecheckt.
- **Prüfen:** `docker compose exec backend python manage.py makemigrations --check --dry-run` zeigt, ob Modelländerungen ohne Migration vorliegen.

## Referenzdaten importieren

Der vollständige TravelPlanner-Datensatz liegt in [`backend/reference_data/data/travelplanner/`](../backend/reference_data/data/travelplanner/README.md). Dort stehen auch Herkunft und Lizenz. Er umfasst 1.225 Fälle: 45 in `train`, 180 in `validation` und 1.000 in `test`.

```sh
docker compose exec backend python manage.py import_reference_cases
```

```text
  train: 45 valid cases
  validation: 180 valid cases
  test: 1000 valid cases
Imported 1225 cases (1225 new, 0 updated, 0 unchanged), rejected 0.
```

- **Wiederholen ist gefahrlos.** Ein erneuter Import legt keine Duplikate an. Die Fälle werden über ihre stabile ID abgeglichen.
- **Ungültige Fälle** werden mit Datei, Zeile, ID und Feld abgewiesen, zum Beispiel `Rejected train.jsonl.gz:3 (…): people_number: Ensure this value is greater than or equal to 1.` Gültige Fälle werden trotzdem importiert, der Befehl endet dann mit Exit-Code 1.
- **Prüfsummen:** Passt eine Datendatei nicht zur Prüfsumme im Manifest, bricht der Import ab, bevor er etwas schreibt.
- **Optionen:**
  - `--split train` importiert nur einzelne Splits, die Option kann mehrfach angegeben werden.
  - `--dry-run` prüft nur und schreibt nichts.
  - Ein eigener Pfad zu einer `manifest.json` importiert andere Daten im selben Format.
- **Anwendungsdaten bleiben unberührt.** Der Import schreibt nur in die Tabellen von `reference_data`. Fälle, die aus einer Datei verschwunden sind, löscht er nicht.

## Tests, Typprüfung, Build

| Prüfung | Befehl |
| --- | --- |
| Backend-Tests | `docker compose exec backend python manage.py test` |
| einzelne App oder Klasse | `docker compose exec backend python manage.py test reference_data` |
| Tests des Journey Planners | `docker compose exec journey-planner python manage.py test` |
| Frontend-Typprüfung | `docker compose exec frontend npm run typecheck` |
| Frontend-Lint | `docker compose exec frontend npm run lint` |
| Frontend-Unit-Tests | `docker compose exec frontend npm test` |
| Frontend-Build | `docker compose exec frontend npm run build` |

Die Frontend-Befehle laufen im Container, Node.js wird auf dem eigenen Rechner nicht gebraucht. Wer Node installiert hat, kann sie auch nach `npm ci` in `frontend/` direkt ausführen.

**Backend-Tests:**

- **Eigene Testdatenbank:** Sie laufen gegen eine eigene Datenbank `test_traveller` auf demselben PostgreSQL-Server. Django legt sie vorher an und löscht sie danach, die Entwicklungsdaten bleiben unverändert.
- **Keine externen Dienste:** Die Tests brauchen weder Internet noch Reiseanbieter noch einen LLM-Zugang und auch keinen laufenden Journey Planner. Das LLM ist das Fake-LLM oder der Offline-Ersatz, der Planner ein Stub, der mit den Vertragsbeispielen aus `docs/contracts/search-v1/` antwortet. Für den Import erzeugen die Tests eigene kleine Testdateien.
- **Abgedeckt:**
  - Health, Fehlerformat und Umgebungsvariablen in `backend/config/tests.py`
  - Session-API in `backend/planning/tests.py`
  - Reise-State in `backend/planning/test_trip_state.py`, darunter Rückflug und Reiseart, nachsichtig gelesene Werte, „die letzte Aussage gewinnt“ und das Bestätigen geratener Werte
  - LLM-Client, Gemini-Client gegen nachgestellte Antworten, Fake-LLM und Offline-Ersatz in `backend/llm/tests.py`
  - Main-Agent (Angaben herauslesen, nächste Frage, Bestätigung geratener Werte, Korrekturen und zurückgenommene Angaben, Hin- und Rückflug, keine neue Suche ohne Änderung, Suche und Erklärung), Optimization Agent, Planner-Client und Chat-Endpunkt in `backend/agent/tests.py`
  - Import und Referenz-API in `backend/reference_data/tests/`

**Tests des Journey Planners**, derzeit 41, in `journey-planner/planner/tests.py`: Endpunkte `POST /plan` und `GET /health`, Validierung des Suchauftrags, Filter und Rangfolge, Hin- und Rückflug als Paar, „keine Treffer“ mit Grund und Richtung, der Ausfall eines Providers sowie die Beispielflüge des Dummy-Providers. Sie brauchen keine Datenbank und vergleichen die Antworten mit denselben Vertragsbeispielen wie die Backend-Tests.

**Frontend-Unit-Tests** prüfen den zentralen API-Client in `frontend/tests/api.test.ts`, darunter `sendMessage`, `listMessages` und `getTripState`, und den Entwurf des Reiseformulars in `frontend/tests/tripDraft.test.ts`. Komponententests für den API-Chat mit MSW und für den Workspace liegen in `frontend/tests/chat.test.tsx` und `frontend/tests/v1.test.tsx`.

**Stand der Prüfung:** Am 18.11.2026 liefen alle drei Testsuiten im Compose-Setup unter Windows, die Backend-Tests gegen PostgreSQL, alle grün. Das war vor der Erweiterung um den Rückflug. Danach liefen die 41 Tests des Journey Planners lokal ohne Docker, alle grün. Für Backend und Frontend gilt der jeweils letzte eigene Testlauf; eine Zahl steht hier bewusst nicht.

## Traveller Frontend V1

Mit `npm run dev` im Verzeichnis `frontend/` starten. Auf `/` „Berlin → Lisbon“
auswählen und im Workspace mit `yes` antworten. Der Workspace zeigt einen
Beispielflug aus der vorhandenen Fixture. Antworten und Änderungen im
Reisekontext bleiben im lokalen React-Zustand. „New journey“ setzt sie zurück.

`/chat?scenario=empty` und `/chat?scenario=api-error` zeigen nach derselben
Bestätigung den leeren bzw. den simulierten Fehlerzustand. Der Workspace
verwendet in jedem Build-Modus lokale Skripte. Die Anbindung des Workspace an
Django, Journey Planner und Agent ist ein separater Arbeitsschritt.

`/chat?view=classic` öffnet den bisherigen API-Chat. Dort und auf `/status`
verwendet der normale Modus Django und der Mock- oder Demo-Modus MSW.

## API-Chat ohne Backend

```bash
cd frontend
npm ci
npm run dev:mock
```

Öffne den [API-Chat im lokalen Mock-Modus](http://localhost:5174/chat?view=classic). Die Statuszeile
„Demo mode“ zeigt das aktive Szenario. Der Service Worker beantwortet
dieselben `/api/v1/`-Anfragen wie Django. Mock-Sitzungen und Verlauf bleiben
beim Neuladen im selben Browser-Tab verfügbar. Mit „New conversation“ beginnt
eine neue Sitzung. Port 5174 trennt die Mock-Sitzungen vom üblichen Real-Modus.

| Szenario | Ablauf |
| --- | --- |
| `/chat?view=classic` | Zuerst z. B. `I want to travel` senden, um eine Rückfrage zu sehen. Im Reiseformular Angaben ändern und mit „Apply changes“ übernehmen. Für einen Treffer `Berlin to Lissabon` senden und den angenommenen Zielort mit `yes` bestätigen. Der Beispieldatensatz enthält einen Direktflug am 20.05.2027. |
| `/chat?view=classic&scenario=empty` | Dieselbe Beispielroute bestätigen. Die Antwort meldet keine Treffer. |
| `/chat?view=classic&scenario=backend-error` | Eine Nachricht senden. Der Chat erhält HTTP 503. |
| `/chat?view=classic&scenario=api-error` | Eine Nachricht senden. Der Chat erhält einen Validierungsfehler mit HTTP 400. |

Die Demo verwendet festgelegte Antworten und eine Flug-Fixture aus dem
Suchvertrag. Weitere Orte, Daten, Rückflüge und freie Sprachinterpretation
können im Real-Modus mit der Backend-API ausprobiert werden. Für den Real-Modus
`npm run dev` starten und die angezeigte URL öffnen. Der Vite-Proxy nutzt lokal
standardmäßig Django auf Port 8000, unter Compose den Service `backend`. Der normale Produktionsbuild startet keinen Mock-Worker und enthält keine Mock-Handler. Nur ein ausdrücklich aktivierter Demo-Build enthält den Worker und die simulierten API-Antworten.

### Öffentliche Frontend-Demo auf Vercel

Die bestehende URL (z. B. `https://traveller-vs.vercel.app/chat`) kann
eine **ausdrücklich aktivierte Demo** ohne Django-Backend ausliefern. Sie verwendet
unter `/chat?view=classic` und `/status` dieselben MSW-Handler und den vorhandenen
API-Client wie der lokale Mock-Modus.
Alle Flüge, Preise, Agentenantworten und Sitzungen in diesem Modus sind simuliert;
das Banner `Demo mode · Simulated travel data` macht das sichtbar.
Es gibt keine echten Buchungen oder einen echten LLM-Aufruf.

Die Datei [`frontend/vercel.json`](../frontend/vercel.json) aktiviert den Demo-Modus
**explizit für Vercel** mit `buildCommand: npm run build:demo` und
`outputDirectory: dist`. Voraussetzung: Das Vercel-Projekt verwendet
`frontend` als Root Directory. Nach dem Merge nach `main` und dem
erfolgreichen Production-Deployment bleibt die URL unverändert,
beispielsweise `https://traveller-vs.vercel.app/chat`.

Für andere Hosting-Umgebungen ist der Demo-Build auch ohne `vercel.json`
möglich: entweder `npm run build:demo` ausführen oder bei `npm run build`
die Build-Umgebungsvariable `VITE_DEMO_MODE=true` setzen. Diese Variable
ist **kein Secret** und wird im Browser-Bundle sichtbar.

Im opt-in Demo-Build schreibt Vite den zu der installierten MSW-Version gehörenden
Worker nach `dist/mockServiceWorker.js` und lädt die Mock-Handler. Der Browser
registriert ihn unter `/mockServiceWorker.js` mit Gültigkeit für `/api/v1/`.
Der Worker muss unter dem Deployment-Host mit HTTP 200 als JavaScript erreichbar
sein; eine SPA-Rewrite-Regel darf diesen Pfad nicht auf `index.html` umleiten.
Für Service Worker ist HTTPS nötig; Vercel stellt HTTPS bereit.

**Lokal als gebautes Bundle testen (ohne Backend):**

```sh
cd frontend
npm ci
npm run build:demo
test -s dist/mockServiceWorker.js
npm run preview -- --host 127.0.0.1 --port 4173
```

Dann `http://127.0.0.1:4173/chat?view=classic` öffnen, `Berlin to Lissabon` senden
und `yes` bestätigen. Ein Beispielflug vom **20.05.2027** erscheint.
Weitere Szenarien lassen sich über `&scenario=empty`, `&scenario=backend-error`
oder `&scenario=api-error` auswählen. Demo-Nachrichten und -Sitzungen werden nur im
`sessionStorage` des Browser-Tabs gespeichert.

**Zur echten API zurückkehren:** In `frontend/vercel.json` den
`buildCommand` wieder auf `npm run build` setzen und sicherstellen,
dass kein `VITE_DEMO_MODE=true` im Vercel-Projekt aktiv ist. Danach ein neues
Deployment auslösen. Für den Real-Modus muss `/api/v1/` durch eine funktionierende
Backend-Route oder einen Reverse Proxy bedient werden. Ein normales
`npm run build` ohne Demo-Schalter enthält keine Mock-Handler und keine Datei
`mockServiceWorker.js`. Root Directory, Domain und Deployment-Status des
Vercel-Projekts sind unabhängig vom Repository zu überprüfen.

### Frontend-CI und Komponententests

Der Workflow [Frontend CI](../.github/workflows/frontend-ci.yml) läuft mit
Node 24 bei Pull Requests mit Änderungen unter `frontend/` oder am Workflow.
Lokal entsprechen die Schritte `npm ci`, `npm run typecheck`, `npm run lint`,
`npm test` und `npm run build` im Verzeichnis `frontend/` der CI.

Die bestehenden Unit-Tests und die React-Komponententests laufen ohne Dienste
und Zugangsdaten. Die Komponententests nutzen Vitest, jsdom, React Testing
Library, `user-event` und dieselben HTTP-Handler wie der Mock-Modus. Sie prüfen
Chat-Eingabe, Wartezustand, Rückfrage und Bestätigung, Formularänderungen,
Sitzungsverlauf, Flugkarten, keine Treffer und API-Fehler. Browserübergreifende
Layout- und Accessibility-Abnahme sowie produktbezogene Ende-zu-Ende-Flüsse
bleiben Teil von [F08 #20](https://github.com/li-minjian/Traveller/issues/20).

## Ohne Docker arbeiten

Für Debugging in der IDE kann das Backend direkt mit Python laufen. Die Compose-Datenbank hat keinen Host-Port, deshalb läuft PostgreSQL dafür als einzelner Container. Vorher `docker compose stop backend` ausführen, weil das Compose-Backend sonst Port 8000 belegt.

```sh
docker run -d --name traveller-db -p 127.0.0.1:5432:5432 --env-file .env postgres:18.6
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Django liest die `.env` im Repo-Root dabei selbst. `docker stop` und `docker start traveller-db` behalten die Daten, erst `docker rm -v traveller-db` löscht sie.

Für die Suche im Chat braucht das Backend den Journey Planner. Entweder läuft er weiter in Compose (Port 8001 ist an `localhost` gebunden), oder er startet in einem zweiten Terminal direkt. Er braucht keine Datenbank und keine `.env`:

```sh
cd journey-planner
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver 8001
```

Das Backend erreicht ihn über den Standardwert `JOURNEY_PLANNER_URL=http://localhost:8001`. Läuft kein Planner, funktioniert der Chat bis zur Suche und meldet dann, dass die Flugsuche nicht erreichbar ist.

Das Frontend lässt sich ebenso direkt starten: in `frontend/` erst `npm ci`, dann `npm run dev`. Es leitet `/api` an `http://localhost:8000` weiter.

## Häufige Fehler

| Symptom | Ursache | Lösung |
| --- | --- | --- |
| `required variable POSTGRES_DB is missing a value: missing - run cp .env.example .env` | Die `.env` fehlt | `cp .env.example .env` |
| `Bind for 127.0.0.1:3000 failed: port is already allocated` (oder `:8000`, `:8001`) | Ein anderes Programm belegt den Port, oft ein lokaler `npm run dev` oder `runserver` | Programm beenden oder in `compose.yaml` den linken Port ändern, z. B. `127.0.0.1:3001:3000` |
| Chat: „Die Flugsuche ist gerade nicht erreichbar.“ | Der Journey Planner läuft nicht, antwortet nicht rechtzeitig oder lehnt den Suchauftrag ab | `docker compose ps`, dann `docker compose logs journey-planner` und `docker compose logs backend` |
| Chat: „The language model or planner is temporarily unavailable.“ | Das Backend antwortet mit `503`: LLM nicht erreichbar, Quota erschöpft oder Datenbank gestoppt | `docker compose logs backend`; bei `LLM_PROVIDER=gemini` Schlüssel und Modell prüfen oder auf `offline` zurückstellen |
| Der Chat versteht eine Angabe nicht und fragt erneut | Mit `LLM_PROVIDER=offline` erkennt nur ein regelbasierter Ersatz feste Muster | Angabe einfacher formulieren, z. B. „von Berlin nach Lissabon am 20.05.2027 mit 2 Personen, zurück am 27.05.2027“, oder das echte LLM einstellen, siehe [LLM-Zugang](#llm-zugang) |
| Chat antwortet ohne neue Ergebnisse, mit dem echten LLM | Die Nachricht hat den Reise-State nicht geändert und enthält keine Reisedaten, deshalb sucht der Agent nicht noch einmal | Eine Angabe ändern, z. B. Datum, Budget oder Umstiege, im Chat oder im Formular |
| Chat fragt „Wann möchtest du zurückfliegen?“, obwohl nur der Hinflug gebraucht wird | Ohne andere Angabe plant der Agent Hin- und Rückflug | „nur Hinflug“ schreiben oder im Formular „One-way“ wählen |
| Chat: „… habe ich leider nichts gefunden. An diesen Tagen gibt es keine Verbindung auf dieser Strecke.“ | Der Dummy-Provider kennt nur 30 europäische Städte, und nicht jede Strecke wird täglich bedient | Zeitraum statt eines festen Datums angeben; die Städte stehen in `PLACES` in `journey-planner/planner/providers/dummy_flights.py` |
| Statusseite: „Backend unreachable“ | Backend-Container läuft nicht oder startet noch | `docker compose ps`, dann `docker compose logs backend`; meist hilft `docker compose up -d` |
| Statusseite: „Database unavailable“ | Datenbank gestoppt oder nicht bereit | `docker compose up -d`, danach „Check again“ |
| Backend bleibt `unhealthy` oder startet immer wieder neu | Migration schlägt fehl oder die Datenbank ist dauerhaft nicht erreichbar | `docker compose logs backend` zeigt den Fehler |
| Statusseite: „Not imported yet“ | Referenzdaten noch nicht importiert, z. B. nach `down -v` | `docker compose exec backend python manage.py import_reference_cases` |
| API antwortet `404` für `/api/v1/health` | Schrägstrich am Ende fehlt | Pfade immer mit `/` beenden, siehe [Konventionen](API_CONVENTIONS.md#1-adressen) |
| Frontend-Container beendet sich sofort, Log: `exec /usr/local/bin/dev-entrypoint: no such file or directory` | Unter Windows hat Git das Startskript `frontend/dev-entrypoint.sh` mit Windows-Zeilenenden ausgecheckt | Die `.gitattributes` im Repo verhindert das. In einem älteren Checkout: `git rm --cached -r . && git reset --hard` (**verwirft nicht eingecheckte Änderungen**) oder die Datei im Editor auf LF umstellen, dann `docker compose up --build -d` |
| Codeänderungen kommen im Frontend nicht an, der Browser zeigt den alten Stand | Das System liefert keine Datei-Events in den Container. Unter Windows mit dem Projekt außerhalb von WSL ist das der Normalfall: Der Vite-Dev-Server im Container bemerkt Änderungen dann nicht. | `WATCH_POLLING=true` in `.env`, dann `docker compose up -d` |
| Nach neuen Python-Paketen: `ModuleNotFoundError` | Das Image ist veraltet | `docker compose up --build -d` |
| Nach neuen npm-Paketen: Import-Fehler im Browser | Die Abhängigkeiten im Container sind veraltet | `docker compose restart frontend`, dabei installiert der Container automatisch neu |
| Tests fragen „Type 'yes' if you would like to try deleting the test database“ | Ein abgebrochener Lauf hat `test_traveller` hinterlassen | `… manage.py test --noinput` |
| Dateien aus dem Container gehören einem fremden Benutzer | Die eigene UID ist nicht 1000; die Container laufen mit UID 1000 | Dateien mit `sudo chown` übernehmen, betrifft z. B. neue Migrationen |
| Alles soll von vorn beginnen | – | `docker compose down -v`, dann `docker compose up --build -d` und neu importieren; **löscht alle Daten** |
