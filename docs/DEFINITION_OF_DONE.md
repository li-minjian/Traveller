# Gemeinsame Definition of Done

Gilt für jedes Ticket zusätzlich zu dessen eigener Definition of Done. Ein Ticket ist fertig, wenn alle Punkte erfüllt sind.

## Umsetzung

- [ ] Die Punkte der Definition of Done im Ticket sind erfüllt und im Issue abgehakt.
- [ ] Die Änderungen sind über einen Pull Request nach `main` gekommen. Der PR beschreibt Änderungen und Prüfung, verknüpft das Issue mit `Closes #<nr>` und wurde geprüft.
- [ ] Der Stand startet frisch mit `cp .env.example .env` und `docker compose up --build -d`, und alle Services werden `healthy`.

## Tests

- [ ] Neue oder geänderte Backend-Logik hat Tests. `docker compose exec backend python manage.py test` ist grün.
- [ ] Frontend: `npm run typecheck`, `npm run lint`, `npm test` und `npm run build` sind grün.
- [ ] Tests brauchen kein Netz, keine Zugangsdaten und keine externen Dienste.

## API und Daten

- [ ] Neue oder geänderte Endpunkte halten die [API-Konventionen](API_CONVENTIONS.md) ein. Abweichungen sind begründet und dort ergänzt.
- [ ] Modelländerungen haben eine eingecheckte Migration.
- [ ] Es gibt keine Zugangsdaten oder Secrets im Repository. Neue Variablen stehen mit unkritischem Beispielwert in `.env.example`.

## Dokumentation (im selben Pull Request)

- [ ] Jeder neue oder geänderte Endpunkt steht in [API.md](API.md) mit Methode, URL, Parametern, Validierung, Beispielantwort und Fehlerfällen.
- [ ] Änderungen an Einrichtung, Befehlen oder Umgebungsvariablen stehen in [DEVELOPMENT.md](DEVELOPMENT.md).
- [ ] Änderungen am Aufbau oder an der Datenhaltung stehen in [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).
- [ ] Was noch nicht umgesetzt ist, ist ausdrücklich als **geplant** markiert.
- [ ] Die Doku stimmt mit dem umgesetzten Stand überein, Beispiele stammen aus der laufenden Anwendung.

Die [PR-Vorlage](../.github/pull_request_template.md) enthält diese Punkte als Checkliste.
