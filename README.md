# Traveller

Prototyp für das Projekt VS an der TU Berlin. Geplant ist ein verteiltes, LLM-basiertes Multi-Agenten-System, das Reisen unter Randbedingungen plant.

Bisher stehen das **Grundgerüst** und ein erster Durchstich vom Chat bis zur Flugvariante:
- React-Frontend mit Chat, Reiseformular und einer technischen Statusseite
- Django-Backend mit REST-API, Main-Agent und einem kleinen Optimization Agent
- Journey Planner als eigener Service für Hin- und Rückflug oder nur den Hinflug, bisher mit erfundenen Beispielflügen zwischen 30 europäischen Städten statt echter Flugdaten
- LLM-Anbindung für Gemini (`gemini-3.6-flash`); Standard ist ein regelbasierter Ersatz ohne Zugangsdaten
- PostgreSQL
- historische TravelPlanner-Benchmark-Fälle als Referenzdaten

## Schnellstart

Voraussetzungen sind Docker mit Compose und freie Ports 3000, 8000 und 8001.

```sh
cp .env.example .env
docker compose up --build -d
docker compose exec backend python manage.py import_reference_cases
```

| Was | Adresse |
| --- | --- |
| Oberfläche mit Chat und Reiseformular | [http://localhost:3000](http://localhost:3000) |
| Statusseite | [http://localhost:3000/status](http://localhost:3000/status) |
| Backend-API | [http://localhost:8000/api/v1/health/](http://localhost:8000/api/v1/health/) |
| Journey Planner | [http://localhost:8001/health](http://localhost:8001/health) |

Im Chat fragt der Main-Agent die Reisedaten ab und zeigt dann Flugvarianten für Hin- und Rückflug, zum Beispiel für „Ich will am 20. Mai zu zweit von Berlin nach Lissabon, zurück am 27. Mai“. Wer nur den Hinflug braucht, schreibt „nur Hinflug“. Die Reisedaten stehen neben dem Chat in einem Formular und lassen sich dort ändern. Eine Angabe, die der Agent nur raten konnte, lässt er sich vor der Suche bestätigen; widerspricht eine neue Angabe einer älteren, gilt die neue. Die Statusseite prüft Backend und Datenbank, legt Planungssitzungen an, lädt sie und zeigt die importierten Referenzdaten. Stoppen mit `docker compose down`, die Daten bleiben dabei erhalten.

## Dokumentation

| Dokument | Inhalt |
| --- | --- |
| [Einrichtung und Betrieb](docs/DEVELOPMENT.md) | Voraussetzungen, Umgebungsvariablen, Start, Stopp, Logs, Migrationen, Datenimport, Tests, Typprüfung, Build, häufige Fehler, Unterschied zwischen Stoppen und Löschen |
| [Projektaufbau und Datenhaltung](docs/PROJECT_STRUCTURE.md) | Verzeichnisse und Apps, Zusammenspiel von React, Django und PostgreSQL, Anwendungs-, Referenz- und Testdaten, Versionen, Grenzen des Grundgerüsts, Geplantes |
| [API-Konventionen](docs/API_CONVENTIONS.md) | verbindliche Regeln: Pfade, Methoden, Statuscodes, Fehlerformat, Feldnamen, Datum, Geld, Listen |
| [API-Referenz](docs/API.md) | alle vorhandenen Endpunkte mit Beispielen und Fehlerfällen |
| [Neuen Endpunkt ergänzen](docs/EXTENDING.md) | Schritt für Schritt von Modell bis Frontend |
| [Definition of Done](docs/DEFINITION_OF_DONE.md) | gemeinsame Kriterien für jedes Ticket, Doku im selben Pull Request |
| [Architektur des Prototyps](docs/ARCHITECTURE_PROTOTYPE.md) | Services, Kommunikation, Aufteilung zwischen Code und LLM, offene Punkte |
| [Suchauftrag](docs/SEARCH_CONTRACT.md) | Format zwischen Main-Agent und Journey Planner mit Beispielen |
| [Backend](backend/README.md) | Aufbau des Backends und häufige Befehle |
| [Journey Planner](journey-planner/README.md) | Aufbau des Planners, Endpunkt, Anbindung eines echten Verkehrs-Service |
| [TravelPlanner-Daten](backend/reference_data/data/travelplanner/README.md) | Herkunft, Version, Lizenz und Format der Referenzdaten |
