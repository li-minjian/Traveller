# Journey Planner

Eigener Service mit Django 5.2 LTS und Django REST Framework, Python 3.14, Port 8001. Er nimmt den Suchauftrag des Main-Agent entgegen, fragt seine Provider nach Verbindungen, filtert nach den harten Kriterien, sortiert und antwortet mit höchstens fünf Varianten. Nennt der Auftrag einen Zeitraum für den Rückflug, sucht er beide Richtungen und antwortet mit Paaren aus Hin- und Rückflug. Er hat **keine Datenbank und kein LLM**, dieselbe Anfrage ergibt immer dieselbe Antwort.

Das Format von Auftrag und Antwort steht in [docs/SEARCH_CONTRACT.md](../docs/SEARCH_CONTRACT.md), die Einordnung in [docs/ARCHITECTURE_PROTOTYPE.md](../docs/ARCHITECTURE_PROTOTYPE.md).

**Stand:** Flüge kommen bisher aus einem Dummy-Provider mit erfundenen Beispielflügen zwischen 30 europäischen Städten. Der echte Flight Service (DS6 #41) und der Vertrag DS1 (#21) fehlen noch. Wie man ihn anbindet, steht unten unter [Einen echten Verkehrs-Service anbinden](#einen-echten-verkehrs-service-anbinden). Die 41 Tests laufen lokal ohne Docker, zuletzt am 18.11.2026, alle grün. Das Docker-Image und der Compose-Service `journey-planner` wurden am 18.11.2026 unter Windows gebaut und gestartet; das war vor der Erweiterung um den Rückflug.

## Aufbau

| Pfad | Inhalt |
| --- | --- |
| `config/` | Django-Projekt: Einstellungen aus Umgebungsvariablen (`settings.py`), URL-Routing (`urls.py`). Keine Datenbank (`DATABASES = {}`). |
| `planner/contract.py` | Prüfung des Suchauftrags mit DRF-Serializern (`SearchRequestSerializer`), darunter `return` als Zeitraum oder `null` |
| `planner/service.py` | `plan(request, providers)`: Provider abfragen, abgeleitete Felder ergänzen, filtern, bei Hin- und Rückflug Paare bilden, sortieren, Antwort im Format des Suchauftrags bauen |
| `planner/providers/base.py` | Schnittstelle `TransportProvider` und der Fehler `ProviderError`. **Hier docken die Verkehrs-Services an.** |
| `planner/providers/dummy_flights.py` | `DummyFlightProvider`: erfundene Beispielflüge zwischen 30 europäischen Städten |
| `planner/providers/__init__.py` | `get_providers()`: wählt die Provider nach der Einstellung `FLIGHT_PROVIDER` |
| `planner/views.py` | Endpunkte `POST /plan` und `GET /health`, JSON-404 und -500 |
| `planner/errors.py` | einheitliches Fehlerformat wie im Backend, siehe [API-Konventionen](../docs/API_CONVENTIONS.md#4-fehlerformat) |
| `planner/testing.py` | Test-Runner ohne Datenbank |
| `planner/tests.py` | Tests für Endpunkte, Filter, Rangfolge, Hin- und Rückflug, Provider-Ausfall und die Beispielflüge |
| `requirements.txt` | exakt gepinnte Abhängigkeiten, dieselben Versionen von Django und DRF wie im Backend |
| `Dockerfile` | Image für die Entwicklung; Compose bindet den Quellcode ein |

## Häufige Befehle

Im Compose-Setup aus dem Repo-Root:

| Aufgabe | Befehl |
| --- | --- |
| Tests | `docker compose exec journey-planner python manage.py test` |
| Logs verfolgen | `docker compose logs -f journey-planner` |
| neu starten | `docker compose restart journey-planner` |
| Beispielauftrag senden | `curl -X POST http://localhost:8001/plan -H 'Content-Type: application/json' -d @docs/contracts/search-v1/request.json` (nur Hinflug) oder `-d @docs/contracts/search-v1/request_round_trip.json` (Hin- und Rückflug) |

Ohne Docker, der Planner braucht weder Datenbank noch `.env`:

```sh
cd journey-planner
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python manage.py test
python manage.py runserver 8001
```

Die Tests laden die Vertragsbeispiele aus `docs/contracts/search-v1/`. Im Repository finden sie den Ordner über den relativen Pfad, im Container ist er unter `/docs/contracts` eingebunden.

## Endpunkte

Die Pfade haben, anders als die der Backend-API, keinen Schrägstrich am Ende.

| Methode | Pfad | Zweck |
| --- | --- | --- |
| `GET` | `/health` | antwortet mit `200` und `{"status": "ok"}`; nutzt der Healthcheck in `compose.yaml` |
| `POST` | `/plan` | Suchauftrag beantworten |

`POST /plan` beschreibt [docs/SEARCH_CONTRACT.md](../docs/SEARCH_CONTRACT.md) vollständig. Kurz:

- Ein gültiger Auftrag ergibt immer `200` mit `status`, `journeys`, `no_results` und `error`. `status` ist `ok`, `no_results` oder `error`.
- Ein ungültiger Auftrag ergibt `400` mit `validation_error` und den betroffenen Feldern.
- Unbekannte Pfade ergeben `404`, andere Methoden `405`, unerwartete Fehler `500`, alle im einheitlichen Fehlerformat.

Beispiele für Auftrag und Antworten liegen in [`docs/contracts/search-v1/`](../docs/contracts/search-v1/). `response_ok.json` ist genau die Antwort des Planners auf `request.json` (nur Hinflug), `response_round_trip.json` die auf `request_round_trip.json` (Hin- und Rückflug).

Aufgerufen wird der Planner nur vom Backend (`backend/agent/planner_client.py`), nie vom Frontend.

## Umgebungsvariablen

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `FLIGHT_PROVIDER` | `dummy` | Woher die Flüge kommen. Bisher gibt es nur `dummy`. Ein unbekannter Wert fällt erst beim ersten `POST /plan` auf: Der Planner antwortet mit `500`, `/health` bleibt `ok`. |
| `DJANGO_DEBUG` | `false` | `true` nur lokal |
| `PLANNER_ALLOWED_HOSTS` | `localhost,127.0.0.1,journey-planner` | Hostnamen, unter denen der Planner antwortet, kommagetrennt |
| `DJANGO_SECRET_KEY` | unkritischer Entwicklungswert | Der Planner hat keine Sitzungen und keine Anmeldung. |

In Compose bekommt der Planner nicht die ganze `.env`, sondern nur die Variablen, die `compose.yaml` unter `journey-planner` → `environment` nennt. Das sind bisher `FLIGHT_PROVIDER` und `DJANGO_DEBUG`. Jede neue Variable muss dort eingetragen werden.

### `GET /places`

Liefert alle Orte, die die Provider kennen: `{"places": [{"name", "country", "aliases"}, …]}`, sortiert nach Land und Name. Ein Provider meldet seine Orte über die optionale Methode `places()`; der Planner vereinigt die Listen. Das Backend nutzt sie für die Vorschläge im Formular und um Ortsnamen zu prüfen (`backend/agent/places.py`). Ein neuer Provider sollte `places()` anbieten, sonst kann man seine Orte im Formular nicht auswählen und der Agent kann sie nicht prüfen.

## Was der Planner selbst erledigt

Diese Schritte stehen in `planner/service.py` und gelten für alle Provider. **Ein Provider darf sie nicht noch einmal umsetzen.**

1. **Provider auswählen:** Gefragt werden nur Provider, deren `mode` im Auftrag unter `modes` steht.
2. **Beide Richtungen abfragen:** Enthält der Auftrag einen Zeitraum in `return`, ruft der Planner jeden Provider ein zweites Mal auf, mit vertauschtem Start und Ziel und dem Zeitraum des Rückflugs als `departure`. Findet schon der Hinflug nichts, entfällt der zweite Aufruf.
3. **Abgeleitete Felder ergänzen:** je Flug `duration_minutes` (erste Abfahrt bis letzte Ankunft), `stops` (Abschnitte minus 1) und `price` (günstigstes Angebot oder `null`).
4. **Nach Zeitraum filtern:** Das Datum der ersten Abfahrt in Ortszeit muss zwischen `departure.earliest` und `departure.latest` liegen, beim Rückflug im Zeitraum `return`.
5. **Nach Umstiegen filtern:** `stops` höchstens `max_stops`, falls gesetzt, für jede Richtung einzeln.
6. **Paare bilden:** Bei Hin- und Rückflug wird jeder Hinflug mit jedem Rückflug kombiniert, der nach der Landung des Hinflugs startet. Der Rückflug steht in `inbound`, die `id` des Paars ist `<id des Hinflugs>+<id des Rückflugs>`. `total_price` ist die Summe beider Preise, oder `null`, wenn ein Preis fehlt oder sich Währung oder Preisbasis unterscheiden. Ohne Rückflug ist `inbound` `null` und `total_price` gleich `price`.
7. **Nach Budget filtern:** `total_price` höchstens `max_price`, falls gesetzt. Das Budget gilt also für beide Flüge zusammen. Unterscheiden sich die Preisbasen (`per_person`, `trip_total`), rechnet der Planner über `travelers` um. Varianten ohne Gesamtpreis oder in einer anderen Währung fallen heraus, Währungen werden nicht umgerechnet.
8. **Sortieren:** günstigster Gesamtpreis zuerst, bei gleichem Preis die kürzere Dauer (bei Paaren die Summe beider Flüge), danach die `id`.
9. **Kürzen:** höchstens fünf Varianten (`MAX_JOURNEYS`). Bei Paaren kommt derselbe Flug in höchstens zwei Varianten vor (`MAX_REUSE`), damit die Liste nicht aus einem Hinflug mit fünf Rückflügen besteht.
10. **„Keine Treffer“ begründen:** `no_connection`, `max_stops` oder `budget`, in dieser Reihenfolge geprüft, mit der nächstbesten Variante. Bei Hin- und Rückflug nennt `direction` die Richtung, an der es liegt (`outbound` oder `inbound`), außer bei `budget`.
11. **Ausfälle einordnen:** Wirft ein Provider `ProviderError` und liefert kein anderer Provider Verbindungen im Zeitraum, ist die Antwort `error` mit `provider_unavailable`. Liefert ein anderer Provider Verbindungen, zählen dessen Ergebnisse, und der Ausfall steht nur im Log.

Die Provider werden nacheinander und synchron abgefragt, bei Hin- und Rückflug je Richtung einmal.

## Der Dummy-Provider

`planner/providers/dummy_flights.py` liefert erfundene Flüge der Linie „Example Air“. Er ist ein Platzhalter und zugleich die Quelle der Vertragsbeispiele. Die Daten sind deterministisch: Dieselbe Anfrage ergibt immer dieselben Flüge, es gibt keinen Zufall zur Laufzeit.

- **Orte:** 30 europäische Städte (`PLACES`), von Berlin, Hamburg und München über Paris, London und Madrid bis Athen, Istanbul und Oslo. Ein unbekannter Ort ergibt eine leere Liste und damit `no_connection`, ebenso derselbe Ort als Start und Ziel.
- **Ortsnamen:** Groß- und Kleinschreibung und Leerzeichen am Rand sind egal, einige weitere Namen wie `Lisbon`, `Rome`, `Munich` oder `BER` werden erkannt.
- **Von Hand festgelegte Strecken** (`ROUTES`): Berlin nach Lissabon, Barcelona, Rom und London, nur in dieser Richtung. Die Vertragsbeispiele beruhen auf Berlin–Lissabon. Rom wird nur montags, mittwochs, freitags und samstags bedient, die anderen drei Ziele täglich.
- **Erzeugte Strecken:** Jedes andere Städtepaar, auch die Rückrichtungen nach Berlin, bekommt Flüge nach festen Regeln aus der Entfernung der Städte und einer Prüfsumme ihrer Namen (`_generated`):
  - ein bis drei Direktflüge. Flüge von oder zu einem Drehkreuz (`HUBS`) und ab Berlin gehen täglich, andere zum Teil nur an einzelnen Wochentagen. So kann ein festes Datum auch nichts oder weniger ergeben.
  - bis zu drei Verbindungen mit einem Umstieg an den Drehkreuzen mit dem kleinsten Umweg, täglich. Ein Drehkreuz mit mehr als dem 2,2-Fachen der direkten Strecke entfällt.
  - auf Strecken über 1.100 km zusätzlich eine besonders günstige Verbindung mit zwei Umstiegen, täglich.
  - Flugzeit und Grundpreis folgen aus der Entfernung.
- **Preise:** in EUR pro Person. Dienstag und Mittwoch sind 15 % günstiger, Freitag und Sonntag 25 % teurer, damit sich ein flexibler Zeitraum lohnen kann.
- **Absichtlich zu knapp:** Die Verbindung Berlin–Lissabon über Frankfurt hat nur 25 Minuten Umsteigezeit. Bei den erzeugten Verbindungen mit einem Umstieg hat etwa jede zwölfte nur 30 Minuten, die übrigen 55 bis 170 Minuten. Daran zeigt sich die Prüfung des Optimization Agent im Backend, der unter 45 Minuten warnt.
- **Zeitraum:** höchstens 31 Tage ab `departure.earliest`.

## Einen echten Verkehrs-Service anbinden

Der Planner kennt nur die Schnittstelle `TransportProvider`. Ein Verkehrs-Service wie der Flight Service wird als weiterer Provider angebunden, der den Service über HTTP aufruft. Der Rest des Planners bleibt unverändert.

### Die Schnittstelle

Aus `planner/providers/base.py`, gekürzt:

```python
class ProviderError(Exception):
    """The provider could not answer (unreachable, timeout, invalid answer)."""


class TransportProvider(Protocol):
    mode: str   # Verkehrsmittel, z. B. "flight"
    name: str   # erscheint als offers[].provider

    def search(self, request: dict) -> list[dict]: ...
```

`search` bekommt den bereits geprüften Suchauftrag mit den Feldern aus [SEARCH_CONTRACT.md](../docs/SEARCH_CONTRACT.md#request). Zwei Dinge weichen vom JSON ab: Die Daten in `departure` und `return` sind `datetime.date`-Objekte, und `max_price.currency` ist bereits großgeschrieben.

**Ein Provider liefert immer einzelne Flüge einer Richtung**, von `origin` nach `destination` im Zeitraum `departure`. Für Hin- und Rückflug ruft der Planner `search` zweimal auf; beim zweiten Mal sind `origin` und `destination` vertauscht, und `departure` enthält den Zeitraum des Rückflugs. Das Feld `return` braucht der Provider nicht auszuwerten. Paare, `inbound` und `total_price` bildet der Planner.

`search` gibt eine Liste von Verbindungen zurück. Jede ist ein Dict mit genau diesen drei Feldern im Aufbau der [Journey](../docs/SEARCH_CONTRACT.md#journey-vorläufig-wird-an-ds1-angeglichen):

```json
{
  "id": "dummy-berlin-lissabon-2027-05-20-direct-early",
  "legs": [
    {
      "mode": "flight",
      "origin": "Berlin",
      "destination": "Lissabon",
      "departure": "2027-05-20T06:40:00+02:00",
      "arrival": "2027-05-20T09:35:00+01:00",
      "carrier": "Example Air",
      "number": "EX 1201"
    }
  ],
  "offers": [
    {
      "id": "dummy-berlin-lissabon-2027-05-20-direct-early-a",
      "provider": "dummy",
      "price": {"amount": 189.0, "currency": "EUR", "basis": "per_person"}
    }
  ]
}
```

Regeln für das Ergebnis:

- **`id`** ist stabil und eindeutig über alle Provider und enthält kein `+`: Der Planner setzt die Kennung eines Paars mit `+` aus beiden Flügen zusammen und trennt sie daran wieder. Das Backend ordnet seine Prüfhinweise über diese Kennung zu.
- **`legs`** hat mindestens einen Abschnitt, in Reisereihenfolge. `departure` und `arrival` sind ISO-8601-Ortszeiten **mit Offset**.
- **`offers`** darf leer sein, wenn kein Preis bekannt ist. Jeder Preis ist ein [Geldbetrag](../docs/API_CONVENTIONS.md#7-geldbeträge) mit `amount`, `currency` und `basis`.
- **Nichts gefunden** ist eine leere Liste `[]`, kein Fehler.
- **`ProviderError`** werfen, wenn der Service nicht erreichbar ist, nicht rechtzeitig antwortet oder etwas Unverwertbares schickt. Nie für „nichts gefunden“.
- **`duration_minutes`, `stops`, `price`, `inbound` und `total_price`** nicht liefern, der Planner ergänzt sie.
- **Nicht filtern und nicht sortieren** nach Preis oder Umstiegen, siehe [oben](#was-der-planner-selbst-erledigt). Der Provider liefert alle Verbindungen der Strecke im Zeitraum. Sonst kann der Planner bei „keine Treffer“ weder den Grund noch die nächstbeste Variante nennen.
- **Antwort des Service prüfen:** Der Planner prüft das Ergebnis eines Providers nicht. Eine Verbindung ohne `legs` oder mit einer Zeit ohne Offset führt zu einem `500` statt zu einer sauberen Fehlerantwort. Deshalb im Provider prüfen und im Zweifel `ProviderError` werfen.

### Schritte

1. **Provider-Klasse anlegen.** Eine neue Datei in `planner/providers/`, zum Beispiel `flight_service.py`, mit einer Klasse, die `TransportProvider` erfüllt: `mode`, `name` und `search(request) -> list[dict]`. Sie übersetzt den Suchauftrag in den DS1-Request, ruft den Service mit einem Timeout auf und übersetzt die DS1-Antwort in Verbindungen mit `id`, `legs` und `offers`. Eine Skizze steht [unten](#skizze-eines-providers).
2. **Registrieren und konfigurieren.**
   - In `planner/providers/__init__.py` in `get_providers()` einen weiteren Wert für `FLIGHT_PROVIDER` ergänzen, der den neuen Provider zurückgibt, und die Fehlermeldung für unbekannte Werte anpassen.
   - Die Adresse des Service als Umgebungsvariable in `config/settings.py` aufnehmen, zum Beispiel `FLIGHT_SERVICE_URL`, dazu ein Timeout.
   - Dieselbe Variable in `compose.yaml` bei `journey-planner` unter `environment` eintragen (im Compose-Netz mit dem Servicenamen als Host) und mit unkritischem Beispielwert in `.env.example`.
   - Die Tabelle in [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md#umgebungsvariablen) und die Tabelle [oben](#umgebungsvariablen) ergänzen.
3. **Service in Compose aufnehmen.** Den Verkehrs-Service in `compose.yaml` als eigenen Service eintragen, nach dem Muster von `journey-planner`: `build`, Port nur an `127.0.0.1` gebunden, Healthcheck auf seinen Health-Endpunkt. Soll der Planner auf ihn warten, bekommt `journey-planner` ein `depends_on` mit `condition: service_healthy`. Das Backend wartet bereits auf den Planner.
4. **Tests schreiben.** In `planner/tests.py` stehen die Muster:
   - `FixedProvider` gibt feste Verbindungen zurück. Damit lässt sich prüfen, dass der Planner Ergebnisse im Format des neuen Providers richtig filtert und sortiert. `RoundTripTests` zeigt dasselbe für Hin- und Rückflug.
   - `FailingProvider` und `ProviderFailureTests` zeigen, dass ein Ausfall `error` ergibt und nie „keine Treffer“.
   - Für den neuen Provider selbst: den HTTP-Aufruf durch eine feste DS1-Antwort ersetzen und prüfen, dass daraus die erwarteten Verbindungen werden und dass Timeout, Verbindungsfehler und eine unverwertbare Antwort jeweils `ProviderError` ergeben. So macht es das Backend für seinen Planner-Client in `backend/agent/tests.py` (`PlannerClientTests`). Kein Test braucht einen laufenden Service.
   - Die Vertragsbeispiele in `docs/contracts/search-v1/` stammen aus dem Dummy-Provider. Die Tests dazu laufen weiter mit `DummyFlightProvider`, unabhängig von `FLIGHT_PROVIDER`.
5. **Sonst nichts ändern.** Solange die Verbindungen dem Journey-Aufbau aus [SEARCH_CONTRACT.md](../docs/SEARCH_CONTRACT.md) folgen, müssen weder der Main-Agent noch der Optimization Agent noch das Frontend angepasst werden. Ändert DS1 dagegen das Journey-/Leg-/Offer-Modell selbst, betrifft das den Vertrag: `SEARCH_CONTRACT.md`, die Beispieldateien und die Tests beider Seiten.

### Skizze eines Providers

Nur eine Skizze. Pfad, Feldnamen und Antwortformat von DS1 stehen noch nicht fest und sind hier Platzhalter, ebenso die Einstellungen `FLIGHT_SERVICE_URL` und `FLIGHT_SERVICE_TIMEOUT_SECONDS`. Der Aufruf nutzt wie der Planner-Client des Backends nur die Standardbibliothek.

```python
"""Flight Service nach DS1 (#21). Skizze: die DS1-Felder sind Platzhalter."""

import json
import urllib.request

from django.conf import settings

from planner.providers.base import ProviderError


class FlightServiceProvider:
    mode = "flight"
    name = "flight-service"

    def search(self, request: dict) -> list[dict]:
        # 1. Suchauftrag -> DS1-Request (Feldnamen noch offen)
        ds1_request = {
            "origin": request["origin"],
            "destination": request["destination"],
            "earliest": request["departure"]["earliest"].isoformat(),
            "latest": request["departure"]["latest"].isoformat(),
            "travelers": request["travelers"],
        }
        http_request = urllib.request.Request(
            settings.FLIGHT_SERVICE_URL.rstrip("/") + "/search",  # Pfad noch offen
            data=json.dumps(ds1_request).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )

        # 2. Aufruf mit Timeout; jeder Ausfall wird zu ProviderError
        try:
            with urllib.request.urlopen(
                http_request, timeout=settings.FLIGHT_SERVICE_TIMEOUT_SECONDS
            ) as response:
                answer = json.loads(response.read())
        except (OSError, ValueError) as error:
            # Timeouts, Verbindungsfehler und HTTP-Fehler sind OSErrors,
            # kaputtes JSON ist ein ValueError.
            raise ProviderError(type(error).__name__) from None

        # 3. DS1-Antwort -> Verbindungen; "nichts gefunden" ist eine leere Liste
        try:
            return [self._journey(item) for item in answer["journeys"]]
        except (KeyError, TypeError) as error:
            raise ProviderError(f"invalid answer: {type(error).__name__}") from None

    def _journey(self, item: dict) -> dict:
        return {
            "id": f"{self.name}-{item['id']}",
            "legs": [
                {
                    "mode": "flight",
                    "origin": leg["origin"],
                    "destination": leg["destination"],
                    "departure": leg["departure"],  # Ortszeit mit Offset
                    "arrival": leg["arrival"],
                    "carrier": leg.get("carrier"),
                    "number": leg.get("number"),
                }
                for leg in item["legs"]
            ],
            "offers": [
                {
                    "id": offer["id"],
                    "provider": self.name,
                    "price": {
                        "amount": offer["amount"],
                        "currency": offer["currency"],
                        "basis": "per_person",
                    },
                }
                for offer in item["offers"]
            ],
        }
```

Die Registrierung in `planner/providers/__init__.py` sieht dann etwa so aus:

```python
def get_providers() -> list[TransportProvider]:
    if settings.FLIGHT_PROVIDER == "dummy":
        return [DummyFlightProvider()]
    if settings.FLIGHT_PROVIDER == "flight-service":
        return [FlightServiceProvider()]
    raise ImproperlyConfigured(f"Unknown FLIGHT_PROVIDER {settings.FLIGHT_PROVIDER!r}.")
```

### Worauf man achten muss

- **Timeout:** Das Backend wartet höchstens `JOURNEY_PLANNER_TIMEOUT_SECONDS` (Standard 10 Sekunden) auf den Planner. Die Provider werden nacheinander abgefragt, bei Hin- und Rückflug jeder zweimal. Die Summe ihrer Timeouts muss also auch dann darunter bleiben. Sonst meldet der Chat einen nicht erreichbaren Planner statt `provider_unavailable`.
- **Orte:** Der Auftrag enthält Ortsnamen so, wie der Agent sie aus dem Gespräch gelesen hat, etwa „Berlin“ oder „Lissabon“. Wer daraus die Orts-IDs von DS1 macht, ist offen, siehe [ARCHITECTURE_PROTOTYPE.md](../docs/ARCHITECTURE_PROTOTYPE.md#5-offene-punkte). Kennt der Provider einen Ort nicht, liefert er `[]`.
- **Budget und Umstiege** darf der Provider an den Service weitergeben, wenn DS1 das vorsieht, um weniger Daten zu holen. Verlassen darf er sich darauf nicht, und der Grund für „keine Treffer“ wird dann ungenauer. Bei Hin- und Rückflug gilt `max_price` für beide Flüge zusammen und nicht für den einzelnen Flug.
- **Weitere Verkehrsmittel:** Ein Provider mit anderem `mode` wird erst gefragt, wenn der Auftrag dieses Verkehrsmittel nennt. Dafür müssen `SUPPORTED_MODES` in `planner/contract.py`, `SEARCH_CONTRACT.md` und der Agent (`modes` in `backend/agent/main_agent.py`) erweitert werden. Das ist dann mehr als ein neuer Provider.
