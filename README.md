# Traveller

Prototyp für das Projekt VS an der TU Berlin. Geplant ist ein verteiltes, LLM-basiertes Multi-Agenten-System, das Reisen unter Randbedingungen plant.

Bisher steht das **Grundgerüst** mit diesen Teilen:
- React-Frontend mit einer technischen Statusseite
- Django-Backend mit REST-API
- PostgreSQL
- historische TravelPlanner-Benchmark-Fälle als Referenzdaten

## Schnellstart

Voraussetzungen sind Docker mit Compose und freie Ports 3000 und 8000.

```sh
cp .env.example .env
docker compose up --build -d
docker compose exec backend python manage.py import_reference_cases
```

| Was | Adresse |
| --- | --- |
| Oberfläche mit Statusseite | [http://localhost:3000](http://localhost:3000) |
| Backend-API | [http://localhost:8000/api/v1/health/](http://localhost:8000/api/v1/health/) |

Die Statusseite prüft Backend und Datenbank, legt Planungssitzungen an, lädt sie und zeigt die importierten Referenzdaten. Stoppen mit `docker compose down`, die Daten bleiben dabei erhalten.

## Dokumentation

| Dokument | Inhalt |
| --- | --- |
| [Einrichtung und Betrieb](docs/DEVELOPMENT.md) | Voraussetzungen, Umgebungsvariablen, Start, Stopp, Logs, Migrationen, Datenimport, Tests, Typprüfung, Build, häufige Fehler, Unterschied zwischen Stoppen und Löschen |
| [Projektaufbau und Datenhaltung](docs/PROJECT_STRUCTURE.md) | Verzeichnisse und Apps, Zusammenspiel von React, Django und PostgreSQL, Anwendungs-, Referenz- und Testdaten, Versionen, Grenzen des Grundgerüsts, Geplantes |
| [API-Konventionen](docs/API_CONVENTIONS.md) | verbindliche Regeln: Pfade, Methoden, Statuscodes, Fehlerformat, Feldnamen, Datum, Geld, Listen |
| [API-Referenz](docs/API.md) | alle vorhandenen Endpunkte mit Beispielen und Fehlerfällen |
| [Neuen Endpunkt ergänzen](docs/EXTENDING.md) | Schritt für Schritt von Modell bis Frontend |
| [Definition of Done](docs/DEFINITION_OF_DONE.md) | gemeinsame Kriterien für jedes Ticket, Doku im selben Pull Request |
| [Backend](backend/README.md) | Aufbau des Backends und häufige Befehle |
| [TravelPlanner-Daten](backend/reference_data/data/travelplanner/README.md) | Herkunft, Version, Lizenz und Format der Referenzdaten |
