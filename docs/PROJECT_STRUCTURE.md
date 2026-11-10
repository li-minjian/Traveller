# Projektstruktur und technische Grundlagen

Stand: Grundgerüst (G01, #5). Was hier als **geplant** markiert ist, existiert noch nicht.

## Verzeichnisse

| Pfad | Zuständigkeit |
| --- | --- |
| `backend/` | Django-Projekt mit Django REST Framework. Stellt die REST-API unter `/api/v1/` bereit und ist die einzige Komponente mit Zugriff auf PostgreSQL. Details: [backend/README.md](../backend/README.md). |
| `frontend/` | React-Anwendung mit TypeScript und Vite. Spricht das Backend ausschließlich über relative Pfade unter `/api/` an (im Entwicklungsbetrieb über den Vite-Proxy). |
| `docs/` | Projekt- und Entwicklerdokumentation: Aufbau, Einrichtung, API-Konventionen, Entscheidungen. |
| `compose.yaml` | Lokale Entwicklungsumgebung für Frontend, Backend und PostgreSQL. **Ausbau zu drei Services in G04 (#8).** |

Weitere Services des Prototyps (z. B. Journey Planner, Flight Service) kommen später als eigene Verzeichnisse auf oberster Ebene hinzu (IN01 #29, IN02 #42). Sie gehören nicht zum Grundgerüst.

## Gewählte Versionen

| Komponente | Version | Begründung |
| --- | --- | --- |
| Python | 3.14 | Seit Oktober 2025 stabil, Support bis Oktober 2030; von Django 5.2, DRF und psycopg unterstützt. |
| Django | 5.2 LTS | Long-Term-Support mit Sicherheitsupdates bis April 2028; deckt die Projektlaufzeit sicher ab. |
| Django REST Framework | 3.18 | Aktuelle Version, offiziell kompatibel mit Django 5.2. |
| psycopg | 3.3 | PostgreSQL-Treiber für Django (psycopg 3). |
| PostgreSQL | 18 | Aktuelle Hauptversion, Support bis November 2030. |
| Node.js | 24 LTS | Bereits Grundlage des Frontends; Support bis April 2028. |
| React / TypeScript / Vite | 19.2 / 5.9 / 8.3 | Siehe `frontend/package.json`. |

Exakte Patch-Versionen werden dort festgehalten, wo sie installiert werden: `backend/requirements.txt` (pip, exakt gepinnt), `frontend/package-lock.json` (npm) und die Image-Tags in `compose.yaml` bzw. den Dockerfiles.

Bewusst nicht gewählt: Python 3.15 und Node.js 26 sind erst seit wenigen Wochen verfügbar; Django 6.x hat kürzere Supportzeiträume als 5.2 LTS.

## Datenhaltung

Es gibt **eine gemeinsame PostgreSQL-Datenbank**. Anwendungs- und Referenzdaten sind darin logisch über getrennte Django-Apps und damit getrennte Tabellen voneinander abgegrenzt:

| Datenart | Django-App | Eigenschaften |
| --- | --- | --- |
| Anwendungsdaten | `planning` | Von Nutzerinnen und Nutzern erzeugt (z. B. Planungssitzungen). Über die API les- und schreibbar. |
| Referenzdaten | `reference_data` | Historische TravelPlanner-Benchmark-Fälle. Nur per Management-Kommando importierbar, über die API ausschließlich lesbar. Ein Import verändert keine Anwendungsdaten. **Geplant ab G05 (#9).** |
| Testdaten | – | Django legt für Tests automatisch eine separate Datenbank (`test_<name>`) an und löscht sie danach. Entwicklungsdaten bleiben unberührt. |

Getrennte PostgreSQL-Schemas wurden verworfen: Django unterstützt sie nur über Umwege (`search_path`, manuelle Tabellennamen), ohne dass der Prototyp davon profitiert.

## Lokale Konfiguration

Zugangsdaten und lokale Einstellungen liegen in `.env`-Dateien und werden nicht eingecheckt. Eingecheckt wird nur `.env.example` mit unkritischen Beispielwerten (ab G04). Abhängigkeiten (`node_modules/`, `.venv/`), Build-Ausgaben und Testberichte sind über `.gitignore` ausgeschlossen.
