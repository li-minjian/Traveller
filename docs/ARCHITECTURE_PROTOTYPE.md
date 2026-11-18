# Architektur-Entscheidungen für den Prototyp

**Status: entschieden (IN01 #29).** Bezieht sich auf den 2-Wochen-Prototyp (#44). Der erste Durchstich ist nach diesen Entscheidungen umgesetzt, mit erfundenen Beispielflügen statt eines Flight Service.

## 1. Umfang

Der Prototyp zeigt einen Durchstich: Chat → Main-Agent → Journey Planner → Flugvarianten.

| Dabei | Bewusst nicht dabei |
| --- | --- |
| Nur Flüge | Bahn, Bus, Auto, Fähre, Hotel |
| Main-Agent und ein kleiner Optimization Agent: prüft die Ergebnisse und sucht bei „keine Treffer“ mit einem gelockerten Kriterium erneut | Optimization Agent, der das Budget verändert, eigene Suchstrategien entwirft oder beliebig oft nachbessert |
| Hin- und Rückflug oder nur der Hinflug | Mehrere Reiseziele, Gabelflüge |
| Erfundene Beispieldaten für 30 europäische Städte | Echte Flug-API, Caching |

## 2. Services

| Service | Verzeichnis | Aufgabe | LLM | Datenbank |
| --- | --- | --- | --- | --- |
| `frontend` | `frontend/` | Oberfläche; spricht nur mit dem Backend | nein | nein |
| `backend` | `backend/` | REST-API für das Frontend, Main-Agent, Optimization Agent, LLM-Client, Reise-State | ja | PostgreSQL |
| `journey-planner` | `journey-planner/` (JP01 #38) | Suchauftrag annehmen, Provider abfragen, filtern, ranken | nein | nein |
| `flight-service` | geplant, DS6 #41 | Flugdaten im DS1-Format liefern, zunächst aus einem Mock-Adapter | nein | nein |
| `db` | – | PostgreSQL, nur vom Backend erreichbar | – | – |

Der Main-Agent ist **kein eigener Service**. Er läuft im Django-Backend, weil er den Reise-State und den Gesprächsverlauf aus der Datenbank braucht. Dasselbe gilt für den Optimization Agent: Er ist ein Modul neben dem Main-Agent (`backend/agent/optimizer.py`) und lässt sich mit `OPTIMIZATION_AGENT_ENABLED=false` abschalten.

Der Journey Planner ist ein **eigener Service ohne LLM und ohne Datenbank**. Umgesetzt ist er mit Django und Django REST Framework, nicht mit FastAPI: So nutzt er dieselben gepinnten Abhängigkeiten und dieselben Konventionen wie das Backend (Fehlerformat, Serializer für die Prüfung des Suchauftrags, Test-Runner), und es kommt keine neue Abhängigkeit ins Projekt.

Solange es den Flight Service nicht gibt, liefert ein Dummy-Provider im Planner erfundene Beispielflüge zwischen 30 europäischen Städten (`FLIGHT_PROVIDER=dummy`). Dieselbe Anfrage ergibt immer dieselben Flüge.

## 3. Kommunikation

Alle Services sprechen synchron über HTTP mit JSON.

```text
frontend ──/api/v1/…──▶ backend (Main-Agent, Optimization Agent)
                           │  POST /plan      Suchauftrag, siehe SEARCH_CONTRACT.md (AG04 #33)
                           ▼
                      journey-planner
                           │  Provider-Schnittstelle (im Prozess)
                           ├── Dummy-Provider: erfundene Beispielflüge      vorhanden
                           └── Provider für den Flight Service              geplant (JP02 #39)
                                  │  DS1-Request  (DS1 #21)
                                  ▼
                             flight-service                                 geplant (DS6 #41)
```

- Das Frontend ruft nur das Backend auf, nie den Planner oder einen Verkehrs-Service.
- Das Backend ruft nur den Planner auf, nie einen Verkehrs-Service.
- Die Adressen der Services stehen in Umgebungsvariablen (IN02 #42), im Compose-Netz sind es die Servicenamen. Für den Planner ist das `JOURNEY_PLANNER_URL`.
- Jeder Aufruf hat ein Timeout (`JOURNEY_PLANNER_TIMEOUT_SECONDS`, `LLM_TIMEOUT_SECONDS`). Ein nicht erreichbarer Service ist ein eigener Fehlerfall und nie „keine Treffer“.
- Jeder Service hat einen Health-Endpunkt: `/api/v1/health/` im Backend, `/health` im Planner.

## 4. Was der Code entscheidet und was das LLM

| Aufgabe | Wer |
| --- | --- |
| Nachricht lesen: Reisedaten samt Rückflug und „nur Hinflug“, was davon nur geraten ist (`inferred`), was bestätigt wurde (`confirmed`), was zurückgenommen wurde (`cleared`), Art der Nachricht (`intent`) und ein Hinweis für die Antwort (`note`) | LLM, als strukturierte Ausgabe |
| Jeden Wert prüfen, bevor er in den Reise-State kommt | Code |
| Was gilt, wenn eine neue Angabe einer älteren widerspricht | Code: Die letzte Aussage gewinnt, siehe unten |
| Was in einem Gesprächsschritt geschieht: nachfragen, bestätigen lassen, ohne neue Suche antworten oder suchen | Code |
| Welche Angabe als Nächstes fehlt | Code, in fester Reihenfolge |
| Ob eine Pflichtangabe nur geraten ist und vor der Suche bestätigt werden muss | Code, anhand der Herkunft `inferred`; gefragt wird nur einmal |
| Ob neu gesucht wird | Code: nicht, wenn es schon eine Suche gab, die Nachricht den Reise-State nicht ändert und sie laut `intent` keine Reisedaten enthält |
| Fragen und Antworttexte formulieren | LLM, aus einer Aufgabe und Fakten des Codes, in der Sprache der Nutzerin oder des Nutzers |
| Flüge suchen, filtern, sortieren; bei Hin- und Rückflug Paare bilden und das Budget auf beide Flüge zusammen anwenden | Code (Journey Planner) |
| Preise, Zeiten, Umstiege in der Liste der Verbindungen | Code: Die Liste wird an den Text des LLM angehängt und läuft nie durch das LLM. |
| Ergebnisse prüfen: plausible Zeiten, Umsteigezeit, fehlender Preis | Code (Optimization Agent) |
| Günstigste, schnellste und empfohlene Variante markieren | Code (Optimization Agent) |
| Welche Lockerungen bei „keine Treffer“ erlaubt sind | Code: Zeitraum von Hin- und Rückflug um drei Tage erweitern oder einen Umstieg mehr zulassen, höchstens zwei weitere Suchen, **nie das Budget** |
| Welche der erlaubten Lockerungen zuerst versucht wird | LLM, als Auswahl aus der festen Liste; ohne LLM gilt die feste Reihenfolge |

Der Optimization Agent des Prototyps ist damit bewusst klein. Die Prüfung der Ergebnisse ist deterministisch, weil ein LLM Daten nicht prüfen kann, für die es keine zweite Quelle hat. Eine gefundene Alternative wird zusätzlich zur Auskunft „keine Treffer“ gezeigt und ändert den Reise-State nicht.

**Die letzte Aussage gewinnt** (`backend/planning/trip_state.py`). Der Code lehnt einen Wert nur ab, wenn er für sich ungültig ist, etwa ein Datum in der Vergangenheit oder null Reisende. Widerspricht ein gültiger Wert einer älteren Angabe, wird die ältere gelöscht und der Agent fragt wieder danach:

- Ein Ort, der bisher Ziel war, wird als Start genannt (oder umgekehrt): Er wechselt die Rolle, das andere Feld ist wieder offen.
- Der Hinflug rückt hinter den bekannten Rückflug: Der Rückflug ist wieder offen.
- „Nur Hinflug“ löscht den Rückflug, ein Rückflugdatum macht die Reise wieder zu Hin- und Rückflug.
- Eine geratene Angabe ersetzt auch eine bestätigte; der Agent lässt sie dann bestätigen.

Offensichtliche Versehen korrigiert der Code, statt sie abzulehnen: Ein verdrehter Zeitraum wird getauscht, ein Zeitraum, der schon begonnen hat, beginnt heute. Ein Rückflug vor dem Hinflug wird dagegen abgelehnt, und der Agent sagt das. Angaben lassen sich auch zurücknehmen, etwa mit „Budget ist mir egal“.

**Nichts geht still verloren.** Der Agent übernimmt alles, was eine Nachricht sagt, in einem Schritt. Jeder Wert, den das LLM gelesen hat, steht danach im Reise-State oder ist mit einem Grund abgelehnt, den die Nutzerin oder der Nutzer erfährt. `Reading.dropped` in `main_agent.py` listet Werte, für die beides nicht gilt; die Liste muss immer leer sein. Ein Eintrag wäre ein Fehler im Code, nicht im LLM.

Ein Gesprächsschritt des Main-Agent (`backend/agent/main_agent.py`) hat damit vier Ausgänge, zwischen denen der Code entscheidet:

1. **Nachfragen:** Eine Pflichtangabe fehlt. Der Agent fragt nach der ersten fehlenden.
2. **Bestätigen lassen:** Alle Pflichtangaben sind da, aber mindestens eine ist nur geraten, etwa der Zeitraum bei „um Ostern rum“. Der Agent nennt seine Annahme und sucht noch nicht. Er fragt nur einmal: Macht die Nutzerin oder der Nutzer danach mit anderen Reisedaten weiter, ohne die Annahme zu korrigieren, gilt sie als bestätigt.
3. **Antworten ohne neue Suche:** Es gab in der Sitzung schon eine Suche, die Nachricht ändert den Reise-State nicht und enthält keine Reisedaten, etwa „Danke“ oder eine Frage.
4. **Suchen:** in allen anderen Fällen.

Die Antworttexte schreibt das LLM aus einer Aufgabe und den Fakten dazu (`reply_instruction` und `TASK_*` in `backend/agent/prompts.py`). Die Persona im Prompt nennt, was der Agent kann und was nicht: Flüge zwischen europäischen Städten als Hin- und Rückflug oder nur als Hinflug, aber keine Hotels, Bahn, Busse, Mietwagen, Buchung oder Wetterdaten. Zu jeder Antwort baut der Code außerdem einen deutschen Text aus den Daten (`backend/agent/texts.py`) und gibt ihn dem LLM-Client als `fallback` mit. Ein echtes LLM bekommt ihn nicht zu sehen; der Offline-Ersatz gibt genau diesen Text aus. Die Liste der Verbindungen mit Preisen und Zeiten hängt in beiden Fällen der Code an. Meldungen über einen Ausfall der Flugsuche sind feste deutsche Texte ohne LLM. Ändert jemand Reisedaten nur im Formular der Oberfläche, bekommt das LLM einen Hinweis, welche Felder geändert wurden. Die Prompts sind versioniert (`PROMPT_VERSION`, derzeit `v4`).

Alle LLM-Aufrufe laufen über das Paket `backend/llm/` (AG02 #31). Standard ist `LLM_PROVIDER=offline`: ein regelbasierter Ersatz, der feste Satzmuster erkennt und die deutschen Texte des Codes unverändert ausgibt. Damit funktionieren Chat und lokale Entwicklung ohne Zugangsdaten und ohne Netz. Die Tests verwenden zusätzlich ein Fake-LLM mit festgelegten Antworten. Das echte LLM ist Gemini (`LLM_PROVIDER=gemini`), aufgerufen über die Gemini-Plattform von Google Cloud. Mit dem Modell `gemini-3.6-flash` sind am 18.11.2026 acht festgelegte Gespräche mit Korrekturen geführt worden; in keinem Schritt ging ein Wert verloren, den das LLM geliefert hat, siehe [DEVELOPMENT.md](DEVELOPMENT.md#llm-zugang).

## 5. Offene Punkte

- **Ortsauflösung:** Der Agent liefert Ortsnamen wie „Berlin“. Das Beispiel in DS1 (#21) verwendet Orts-IDs (`origin_id`). Wer aus dem Namen die ID macht und welches Format die IDs haben, ist noch nicht festgelegt. Bis dahin reicht der Suchauftrag Namen durch. Der Dummy-Provider gleicht sie mit einer eigenen Liste von 30 Städten ab.
- **Journey-/Leg-/Offer-Modell:** Das Antwortformat des Planners übernimmt das Modell aus DS1, sobald es feststeht.
- **Übergabe JP02 (#39):** Die Provider-Schnittstelle des Planners ist vorhanden: `TransportProvider` in `journey-planner/planner/providers/base.py` mit `mode`, `name` und `search(request)`. `search` liefert einzelne Flüge einer Richtung mit `id`, `legs` und `offers`, eine leere Liste für „nichts gefunden“ und wirft `ProviderError`, wenn der Service nicht antwortet. Für Hin- und Rückflug ruft der Planner `search` zweimal auf und bildet die Paare selbst. Bisher implementiert sie nur der Dummy-Provider mit erfundenen Flügen. Offen ist ein Provider, der den Suchauftrag in den DS1-Request übersetzt, den Flight Service über HTTP aufruft und die Antwort zurückübersetzt. Die Schritte stehen in der [README des Planners](../journey-planner/README.md#einen-echten-verkehrs-service-anbinden).
