# Frontend-Anforderungen und Umsetzungsstand

Stand 18.11.2026. Grundlage der Bestandsaufnahme ist `main` nach [PR #59](https://github.com/li-minjian/Traveller/pull/59). Die Einstufungen beschreiben die technische Abdeckung im Prototyp. Die Abnahme der User Stories bleibt beim Team.

## Kurskontext

Traveller entsteht im Bachelorprojekt Verteilte Systeme der TU Berlin. Das Team entwickelt und betreibt eine verteilte, LLM-gestützte Multi-Agenten-Anwendung für die Reiseplanung und nutzt agile Projektplanung und Open-Source-Entwicklungspraktiken. Der Projektkontext legt den konkreten Funktionsumfang der Demo und des Produkts noch nicht fest. Siehe [Projektbeschreibung](../README.md) und [Projektaufbau](PROJECT_STRUCTURE.md).

## Technischer Prototyp

- React, TypeScript und Vite stellen Chat, Reiseformular und Systemstatus bereit. Ein zentraler Client spricht über `/api/v1/` mit Django. Planungssitzungen, Gesprächsverlauf und Trip State liegen im Backend mit PostgreSQL.
- Der Main-Agent verarbeitet Freitext, fragt fehlende Reiseangaben ab und lässt erschlossene Pflichtangaben bestätigen. Das Formular zeigt den Trip State an und übermittelt Änderungen über denselben Chat-Endpunkt.
- Der Journey Planner liefert strukturierte Beispiele für Hin- und Rückflüge sowie einfache Flüge aus einem Dummy-Datensatz. Die Oberfläche zeigt Verbindungen, Preise und gegebenenfalls Alternativen. Der Optimization Agent prüft Ergebnisse, kennzeichnet Empfehlungen und kann bei fehlenden Treffern begrenzte Alternativsuchen auslösen.
- Docker Compose startet Frontend, Backend, Journey Planner und PostgreSQL lokal. Der Offline-LLM-Ersatz erlaubt Backend-Entwicklung ohne LLM-Zugangsdaten. Die im Infrastruktur-PR ergänzte Mock API erlaubt die Entwicklung der Oberfläche ohne diese Dienste.

Quellen: [API](API.md), [Prototyp-Architektur](ARCHITECTURE_PROTOTYPE.md), [Entwicklung](DEVELOPMENT.md), [Chat](../frontend/src/features/Chat.tsx), [Reiseformular](../frontend/src/features/chat/TripForm.tsx), [Ergebniskarten](../frontend/src/features/chat/Results.tsx).

## Vorgeschlagene Produktfunktionen

Landing Page, Discovery, Explore, Compare, ein erweiterter Travel Context, Ergebnisauswahl, Karten und weitere Planungsinteraktionen sind Vorschläge im [Frontend-Epic #2](https://github.com/li-minjian/Traveller/issues/2) und seinen Product-Backlog-Issues. Zielgruppe, Umfang und Interaktion benötigen eine Teamentscheidung, bevor sie als MVP-Anforderungen gelten.

| Issue | Technischer Status auf `main` | Offener Abnahmeumfang |
| --- | --- | --- |
| [F01 #13](https://github.com/li-minjian/Traveller/issues/13) | Teilweise umgesetzt. Responsiver Chat-Workspace mit Reiseformular und Ergebnissen. | Abgestimmter MVP-Nutzerfluss und Wireframes für Einstieg, Workspace und Ergebnis. |
| [F02 #14](https://github.com/li-minjian/Traveller/issues/14) | Teilweise umgesetzt. Freitext, Sitzungsbezug, Eingabe- und Wartezustand sind im Chat vorhanden. | Vorgesehener Einstieg und Übergang von Startansicht zum Workspace. |
| [F03 #15](https://github.com/li-minjian/Traveller/issues/15) | Teilweise umgesetzt. Verlauf, Rückfragen, Antwort, Warte- und Fehleranzeige sind vorhanden. | Differenzierter Agentenfortschritt, optionales Überspringen und Feedback. Feedback ist noch nicht integriert und braucht einen API-Vertrag. |
| [F04 #16](https://github.com/li-minjian/Traveller/issues/16) | Teilweise umgesetzt. Das Reiseformular zeigt und ändert Flugparameter einschließlich Herkunft und fehlender Werte. | Produktumfang des Travel Context und Umgang mit älteren Ergebnissen bei Änderungen. |
| [F05 #17](https://github.com/li-minjian/Traveller/issues/17) | Teilweise umgesetzt. Strukturierte Flugkarten, Empfehlungen, Warnungen und Alternativen. | Auswahl mit Folgeschritt, Quellennachweise, Zeitstand, Teilantworten und breiteres Ergebnisformat. |
| [F06 #18](https://github.com/li-minjian/Traveller/issues/18) | Nicht umgesetzt. | Vergleich und Detailansicht hängen von auswählbaren Optionen und vergleichbaren Daten ab. |
| [F07 #19](https://github.com/li-minjian/Traveller/issues/19) | Optional. | Teamentscheidung über Nutzen, Datenquelle und Lizenz für eine Karte. |
| [F08 #20](https://github.com/li-minjian/Traveller/issues/20) | Teilweise umgesetzt. Unit-Tests für Client, Ortsdaten und Reiseentwurf sind vorhanden. | [FE-INFRA-03 #62](https://github.com/li-minjian/Traveller/issues/62) ergänzt die Komponentenbasis. Produktfluss, Ergebnisauswahl, responsive Darstellung, Tastatur und Fokus bleiben Gegenstand von F08. |
| [F09 #50](https://github.com/li-minjian/Traveller/issues/50) | Durch offene Anforderungen blockiert. | Die UI-Dokumentation für Landing Page, Discovery, Explore und Compare setzt abgestimmte Seiten und Interaktionen voraus. |

[G03 #7](https://github.com/li-minjian/Traveller/issues/7) liefert Frontend und Backend-Anbindung. [G06 #10](https://github.com/li-minjian/Traveller/issues/10) deckt Basisintegration ab. Darauf bauen [CI #60](https://github.com/li-minjian/Traveller/issues/60), [Mock API #61](https://github.com/li-minjian/Traveller/issues/61) und [Komponententests #62](https://github.com/li-minjian/Traveller/issues/62) auf.

## Offene Teamentscheidungen

- Wer ist die Zielgruppe? Geht es um akademische Dienstreisen oder allgemeine Reiseplanung?
- Wie sieht der vollständige MVP-Nutzerfluss aus? Sind Flugoptionen das Ergebnis oder soll ein vollständiger Reiseplan entstehen?
- Welche Verkehrsmittel und Unterkünfte gehören dazu? Welche externen Datenquellen müssen echte Daten liefern?
- Wie werden Alternativen ausgewählt, verglichen und gegebenenfalls weiterverwendet?
- Welche Aufgaben übernimmt die Oberfläche und welche übernimmt der Agent im Backend? Welche Produktfunktionen benötigen bestätigte API-Verträge?
- Welche Funktionen muss die Kursdemo zeigen und in welcher Umgebung soll Traveller bereitgestellt werden?

## Anforderungen und Planung

Produktanforderungen bestimmen die Prioritäten im Product Backlog. Das Team verfeinert die Einträge, sobald Anforderungen klarer werden, und übernimmt Aufgaben erst im Sprint Planning verbindlich in den Sprint Backlog. Es kann Einträge nach gemeinsamer Prüfung ändern, aufteilen, neu priorisieren oder zurückstellen.

Das Frontend-Team kann fehlende Backend-Funktionen über Issues und API-Vertragsdiskussionen vorschlagen. Änderungen an gemeinsamen Verträgen werden mit den zuständigen Teams abgestimmt.
