# Einrichtung und Betrieb

Wie man Traveller lokal einrichtet, startet, prüft und zurücksetzt. Wie das Projekt aufgebaut ist, beschreibt [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).

## Voraussetzungen

- **Docker** mit dem Compose-Plugin (`docker compose`, nicht das alte `docker-compose`).
- **Git**.
- Freie Ports **3000** (Frontend) und **8000** (Backend) auf `localhost`.
- Nur für die Arbeit außerhalb von Docker: Python 3.14 (3.13 geht auch) und Node.js 24 (22.12 oder neuer geht auch).

Der erste Build braucht Internet für die Images und Pakete, der laufende Betrieb nicht. Die Referenzdaten liegen im Repository.

## Erstes Einrichten

```sh
git clone https://github.com/li-minjian/Traveller.git
cd Traveller
cp .env.example .env                                                  # lokale Konfiguration
docker compose up --build -d                                          # bauen und starten
docker compose ps                                                     # nach ~30 s: alle drei "healthy"
docker compose exec backend python manage.py import_reference_cases   # Referenzdaten laden
```

Danach zeigt [http://localhost:3000](http://localhost:3000) die Statusseite mit „Connected“ und „1,225 cases imported“. Die Migrationen laufen beim Start des Backends automatisch.

| Service | Adresse | Inhalt |
| --- | --- | --- |
| `frontend` | [http://localhost:3000](http://localhost:3000) | Vite-Dev-Server mit Statusseite `/status`, leitet `/api` an das Backend weiter |
| `backend` | [http://localhost:8000/api/v1/health/](http://localhost:8000/api/v1/health/) | Django-Entwicklungsserver mit der REST-API |
| `db` | kein Host-Port | PostgreSQL 18, nur im Compose-Netz unter dem Namen `db` erreichbar |

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
| `WATCH_POLLING` | nein | `false` | `true`, falls Dateiänderungen den Frontend-Container nicht erreichen |
| `API_PROXY_TARGET` | nein | `http://localhost:8000` | Ziel des Vite-Proxys für `/api`; Compose setzt `http://backend:8000` |

Die Postgres-Variablen liest auch das offizielle `postgres`-Image, deshalb teilen sich Datenbank und Backend dieselbe `.env`.

- **Fehlt eine Pflichtvariable** oder ist sie leer, bricht Django beim Start ab, zum Beispiel mit `Environment variable DJANGO_SECRET_KEY is not set.`
- **Ist eine optionale Variable leer**, gilt ihr Standardwert.
- **Neue Variablen** kommen mit unkritischem Beispielwert in `.env.example` und in diese Tabelle.

## Starten, stoppen, Logs

| Aufgabe | Befehl |
| --- | --- |
| alles starten | `docker compose up -d` |
| nach Änderung an `backend/requirements.txt` oder einem Dockerfile | `docker compose up --build -d` |
| Status ansehen | `docker compose ps` |
| Logs verfolgen | `docker compose logs -f backend`, ebenso für `frontend` und `db` |
| einen Service neu starten | `docker compose restart backend` |
| Django-Befehl ausführen | `docker compose exec backend python manage.py <befehl>` |
| Datenbank-Konsole | `docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'` |
| stoppen, Daten behalten | `docker compose stop` oder `docker compose down` |

Code in `frontend/` und `backend/` ist in die Container eingebunden. Änderungen greifen sofort und ohne Rebuild: Django startet neu, Vite lädt den Browser neu. Ändert sich `frontend/package-lock.json`, installiert der Frontend-Container beim nächsten Start (`docker compose restart frontend`) die Abhängigkeiten automatisch neu.

### Stoppen oder Daten löschen

| Befehl | Container | Datenbankdaten |
| --- | --- | --- |
| `docker compose stop` | angehalten | **bleiben** |
| `docker compose down` | entfernt | **bleiben** (Volume `postgres-data`) |
| `docker compose down -v` | entfernt | **gelöscht**, ebenso das Volume `frontend-node-modules` |

`down -v` löscht alle Planungssitzungen und importierten Referenzdaten unwiderruflich. Danach startet das Backend mit einer leeren Datenbank. Die Migrationen laufen beim Start automatisch, die Referenzdaten müssen neu importiert werden.

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
| Frontend-Typprüfung | `docker compose exec frontend npm run typecheck` |
| Frontend-Lint | `docker compose exec frontend npm run lint` |
| Frontend-Unit-Tests | `docker compose exec frontend npm test` |
| Frontend-Build | `docker compose exec frontend npm run build` |

Die Frontend-Befehle laufen im Container, Node.js wird auf dem eigenen Rechner nicht gebraucht. Wer Node installiert hat, kann sie auch nach `npm ci` in `frontend/` direkt ausführen.

**Backend-Tests**, derzeit 39 in etwa 1,5 s:

- **Eigene Testdatenbank:** Sie laufen gegen eine eigene Datenbank `test_traveller` auf demselben PostgreSQL-Server. Django legt sie vorher an und löscht sie danach, die Entwicklungsdaten bleiben unverändert.
- **Keine externen Dienste:** Die Tests brauchen weder Internet noch Reiseanbieter noch einen LLM-Zugang. Für den Import erzeugen sie eigene kleine Testdateien.
- **Abgedeckt:**
  - Health, Fehlerformat und Umgebungsvariablen in `backend/config/tests.py`
  - Session-API in `backend/planning/tests.py`
  - Import und Referenz-API in `backend/reference_data/tests/`

**Frontend-Unit-Tests** prüfen den zentralen API-Client in `frontend/tests/api.test.ts`. Browser- und End-to-End-Tests gibt es im Grundgerüst nicht.

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

Das Frontend lässt sich ebenso direkt starten: in `frontend/` erst `npm ci`, dann `npm run dev`. Es leitet `/api` an `http://localhost:8000` weiter.

## Häufige Fehler

| Symptom | Ursache | Lösung |
| --- | --- | --- |
| `required variable POSTGRES_DB is missing a value: missing - run cp .env.example .env` | Die `.env` fehlt | `cp .env.example .env` |
| `Bind for 127.0.0.1:3000 failed: port is already allocated` (oder `:8000`) | Ein anderes Programm belegt den Port, oft ein lokaler `npm run dev` oder `runserver` | Programm beenden oder in `compose.yaml` den linken Port ändern, z. B. `127.0.0.1:3001:3000` |
| Statusseite: „Backend unreachable“ | Backend-Container läuft nicht oder startet noch | `docker compose ps`, dann `docker compose logs backend`; meist hilft `docker compose up -d` |
| Statusseite: „Database unavailable“ | Datenbank gestoppt oder nicht bereit | `docker compose up -d`, danach „Check again“ |
| Backend bleibt `unhealthy` oder startet immer wieder neu | Migration schlägt fehl oder die Datenbank ist dauerhaft nicht erreichbar | `docker compose logs backend` zeigt den Fehler |
| Statusseite: „Not imported yet“ | Referenzdaten noch nicht importiert, z. B. nach `down -v` | `docker compose exec backend python manage.py import_reference_cases` |
| API antwortet `404` für `/api/v1/health` | Schrägstrich am Ende fehlt | Pfade immer mit `/` beenden, siehe [Konventionen](API_CONVENTIONS.md#1-adressen) |
| Codeänderungen kommen im Frontend nicht an | Das System liefert keine Datei-Events in den Container, häufig unter Windows mit dem Projekt außerhalb von WSL | `WATCH_POLLING=true` in `.env`, dann `docker compose up -d` |
| Nach neuen Python-Paketen: `ModuleNotFoundError` | Das Image ist veraltet | `docker compose up --build -d` |
| Nach neuen npm-Paketen: Import-Fehler im Browser | Die Abhängigkeiten im Container sind veraltet | `docker compose restart frontend`, dabei installiert der Container automatisch neu |
| Tests fragen „Type 'yes' if you would like to try deleting the test database“ | Ein abgebrochener Lauf hat `test_traveller` hinterlassen | `… manage.py test --noinput` |
| Dateien aus dem Container gehören einem fremden Benutzer | Die eigene UID ist nicht 1000; die Container laufen mit UID 1000 | Dateien mit `sudo chown` übernehmen, betrifft z. B. neue Migrationen |
| Alles soll von vorn beginnen | – | `docker compose down -v`, dann `docker compose up --build -d` und neu importieren; **löscht alle Daten** |
