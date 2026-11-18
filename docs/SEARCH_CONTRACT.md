# Suchauftrag: Main-Agent → Journey Planner

**Status: umgesetzt (AG04 #33, JP01 #38), Antwortmodell vorläufig.** Der Main-Agent im Backend sendet dieses Format, der Journey Planner in [`journey-planner/`](../journey-planner/README.md) beantwortet es. Das Journey-/Leg-/Offer-Modell in der Antwort ist vorläufig und wird an DS1 (#21) angeglichen, sobald DS1 feststeht. Diese Abstimmung steht noch aus.

Dieses Format regelt die Ebene **Agent → Planner**. Wie der Planner mit den Verkehrs-Services spricht, regelt DS1.

Die Beispiele liegen als Dateien in [`contracts/search-v1/`](contracts/search-v1/). Die Antwortbeispiele sind aus dem Dummy-Provider des Planners erzeugt, der feste Beispielflüge liefert. Die Tests beider Seiten laden genau diese Dateien: [`journey-planner/planner/tests.py`](../journey-planner/planner/tests.py) prüft, dass der Planner sie erzeugt, [`backend/agent/tests.py`](../backend/agent/tests.py) lässt den Agenten damit arbeiten. Wer das Format ändert, ändert die Dateien und sieht in beiden Testläufen, was nicht mehr passt.

## Aufruf

`POST /plan` am Journey Planner, Body und Antwort sind JSON. Der Pfad hat keinen Schrägstrich am Ende. Feldnamen, Datumsformate und Geldbeträge folgen den [API-Konventionen](API_CONVENTIONS.md).

Lokal ist der Planner unter `http://localhost:8001` erreichbar, im Compose-Netz unter `http://journey-planner:8001`. Das Backend liest die Adresse aus `JOURNEY_PLANNER_URL`.

## Request

Beispiele: [`request.json`](contracts/search-v1/request.json) (nur Hinflug), [`request_round_trip.json`](contracts/search-v1/request_round_trip.json) (Hin- und Rückflug)

| Feld | Typ | Pflicht | Regel |
| --- | --- | --- | --- |
| `origin` | String | ja | Startort als Name, 1–100 Zeichen |
| `destination` | String | ja | Zielort als Name, 1–100 Zeichen |
| `departure` | Objekt | ja | `earliest` und `latest` als `YYYY-MM-DD`. Ein festes Datum hat zweimal denselben Wert. `earliest` liegt nicht nach `latest`. |
| `return` | Objekt oder `null` | ja | Zeitraum des Rückflugs, Aufbau wie `departure`. Mit einem Zeitraum sucht der Planner Hin- und Rückflug, `null` bedeutet nur Hinflug. `return.latest` liegt nicht vor `departure.earliest`. |
| `travelers` | Ganzzahl | ja | mindestens 1 |
| `max_price` | Geldbetrag oder `null` | ja | Obergrenze für die ganze Reise, bei Hin- und Rückflug also für beide Flüge zusammen. `basis` ist `per_person` oder `trip_total`. `null` bedeutet keine Grenze. |
| `max_stops` | Ganzzahl oder `null` | ja | höchste Zahl an Umstiegen je Richtung, mindestens 0. `null` bedeutet keine Grenze. |
| `modes` | Liste von Strings | ja | Verkehrsmittel, mindestens eines; im Prototyp nur `["flight"]` |

`return`, `max_price` und `max_stops` müssen immer gesendet werden, auch wenn sie `null` sind.

Ein ungültiger Auftrag ergibt `400` im [einheitlichen Fehlerformat](API_CONVENTIONS.md#4-fehlerformat) mit `fields`. Das Backend behandelt ein `400` wie einen nicht erreichbaren Planner, denn ein ungültiger Auftrag ist ein Fehler im Agenten und keine Eingabe der Nutzerin oder des Nutzers.

## Response

Jede fachliche Antwort hat den HTTP-Status `200` und dieselben vier Felder. Welches gefüllt ist, bestimmt `status`:

| `status` | Bedeutung | `journeys` | `no_results` | `error` |
| --- | --- | --- | --- | --- |
| `ok` | Treffer gefunden | 1–5 Varianten, beste zuerst | `null` | `null` |
| `no_results` | Suche hat funktioniert, aber nichts passt | `[]` | Grund und nächstbeste Variante | `null` |
| `error` | Suche konnte nicht ausgeführt werden | `[]` | `null` | Code und Meldung |

Beispiele: [`response_ok.json`](contracts/search-v1/response_ok.json), [`response_round_trip.json`](contracts/search-v1/response_round_trip.json), [`response_no_results.json`](contracts/search-v1/response_no_results.json), [`response_error.json`](contracts/search-v1/response_error.json)

- `response_ok.json` ist die Antwort auf `request.json`: Berlin nach Lissabon am 20.05.2027, nur Hinflug.
- `response_round_trip.json` ist die Antwort auf `request_round_trip.json`: dieselbe Strecke mit Rückflug am 27.05.2027 und einem Höchstpreis von 400 € pro Person für beide Flüge. Die günstigste Variante kostet zusammen 200,67 € pro Person.
- `response_no_results.json` gehört zum Auftrag `request.json` mit einem Höchstpreis von 50 € pro Person; die günstigste gefundene Variante kostet 98 €.
- `response_error.json` entsteht, wenn der einzige Provider ausfällt.

**Ein Fehler ist nie „keine Treffer“.** Antwortet ein Verkehrs-Service nicht, ist der Status `error`.

„Beste zuerst“ heißt: günstigster Gesamtpreis (`total_price`), bei gleichem Preis kürzere Dauer. Varianten ohne Preis stehen am Ende. Der Planner prüft die Kriterien in dieser Reihenfolge: Zeitraum, Umstiege, Höchstpreis. Haben Gesamtpreis und Höchstpreis verschiedene Preisbasen, rechnet der Planner den Gesamtpreis über `travelers` um. Währungen rechnet der Planner nicht um: Eine Variante in einer anderen Währung als `max_price` gilt als nicht im Budget, ebenso eine Variante ohne Gesamtpreis.

### Hin- und Rückflug

Enthält der Auftrag einen Zeitraum in `return`, sucht der Planner in beiden Richtungen und antwortet mit Paaren: Jede Variante ist ein Hinflug mit einem passenden Rückflug in `inbound`.

- **Rückrichtung:** Für den Rückflug sind Start und Ziel vertauscht, und das Datum der ersten Abfahrt muss in `return` liegen.
- **Reihenfolge:** Der Rückflug startet erst, nachdem der Hinflug gelandet ist. Der Planner bildet jedes Paar, das diese Bedingung erfüllt.
- **Umstiege:** `max_stops` gilt für jede Richtung einzeln.
- **Budget:** `max_price` gilt für `total_price`, also für beide Flüge zusammen.
- **Rangfolge:** nach `total_price`, bei gleichem Preis nach der Summe der beiden Flugdauern.
- **Auswahl:** Derselbe Flug kommt in höchstens zwei der zurückgegebenen Varianten vor (`MAX_REUSE` in `journey-planner/planner/service.py`). So besteht die Liste nicht aus einem Hinflug mit fünf Rückflügen.

### Journey (vorläufig, wird an DS1 angeglichen)

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `id` | String | stabile Kennung der Variante |
| `legs` | Liste | Reiseabschnitte in Reihenfolge, mindestens einer |
| `legs[].mode` | String | Verkehrsmittel, im Prototyp `flight` |
| `legs[].origin`, `legs[].destination` | String | Orte des Abschnitts |
| `legs[].departure`, `legs[].arrival` | String | Ortszeit mit Offset, z. B. `2027-05-20T06:40:00+02:00` |
| `legs[].carrier`, `legs[].number` | String oder `null` | Anbieter und Verbindungsnummer |
| `offers` | Liste | konkrete Angebote; kann leer sein, wenn kein Preis bekannt ist |
| `offers[].id`, `offers[].provider` | String | Kennung und Herkunft des Angebots |
| `offers[].price` | Geldbetrag | Preis des Angebots |
| `duration_minutes` | Ganzzahl | Gesamtdauer von der ersten Abfahrt bis zur letzten Ankunft |
| `stops` | Ganzzahl | Zahl der Umstiege, also Abschnitte minus 1 |
| `price` | Geldbetrag oder `null` | günstigstes Angebot; `null`, wenn kein Preis bekannt ist |
| `inbound` | Objekt oder `null` | der Rückflug; `null` bei einer Suche nur für den Hinflug |
| `total_price` | Geldbetrag oder `null` | Preis der ganzen Reise. Ohne Rückflug gleich `price`, mit Rückflug die Summe beider `price`. `null`, wenn ein Preis fehlt oder sich Währung oder Preisbasis der beiden Flüge unterscheiden. |

Bei Hin- und Rückflug beschreiben `legs`, `offers`, `duration_minutes`, `stops` und `price` den Hinflug. `inbound` hat dieselben Felder für den Rückflug, dazu seine eigene `id`, aber weder `inbound` noch `total_price`. Die `id` der Variante ist dann aus beiden Kennungen zusammengesetzt: `<id des Hinflugs>+<id des Rückflugs>`.

`id`, `legs` und `offers` eines Flugs kommen vom Provider. `duration_minutes`, `stops`, `price`, `inbound` und `total_price` ergänzt der Planner.

### `no_results`

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `reason` | String | `budget` (alles über dem Höchstpreis), `max_stops` (alles mit zu vielen Umstiegen), `no_connection` (keine Verbindung im Zeitraum gefunden) |
| `direction` | String oder `null` | bei Hin- und Rückflug die Richtung, an der es liegt: `outbound` (Hinflug) oder `inbound` (Rückflug). Immer `null` bei `budget` und bei einer Suche nur für den Hinflug. |
| `closest_journey` | Journey oder `null` | die nächstbeste Variante, die das Kriterium verletzt: bei `budget` die günstigste mit erlaubter Zahl an Umstiegen, bei `max_stops` die mit den wenigsten Umstiegen. `null` bei `no_connection`. |

Auch ein unbekannter Ort ergibt `no_connection`, denn die Suche hat funktioniert und nichts gefunden.

Bei Hin- und Rückflug gilt zusätzlich:

- `no_connection` mit `outbound`: kein Hinflug im Zeitraum. Der Rückflug wird dann nicht mehr gesucht.
- `no_connection` mit `inbound`: kein Rückflug im Zeitraum, oder kein Rückflug startet nach der Landung eines Hinflugs.
- `max_stops`: `direction` nennt die Richtung, in der jede Verbindung zu viele Umstiege hat; trifft das auf beide zu, steht dort `outbound`. `closest_journey` ist das Paar mit den wenigsten Umstiegen in beiden Richtungen zusammen, oder `null`, wenn sich kein Paar bilden lässt.
- `budget`: `closest_journey` ist das Paar mit dem günstigsten `total_price`.

### `error`

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `code` | String | `provider_unavailable`: Ein Verkehrs-Service war nicht erreichbar, hat nicht rechtzeitig oder nicht verwertbar geantwortet, und kein anderer hat Verbindungen im Zeitraum geliefert. |
| `message` | String | englische Beschreibung für Entwicklerinnen und Entwickler, hier `"A transport service could not be reached."` |

Fällt ein Provider aus und ein anderer liefert Verbindungen im Zeitraum, ist der Status nicht `error`. Der Planner antwortet dann mit den Ergebnissen der übrigen Provider.

Ein unerwarteter Fehler im Planner selbst ist keine fachliche Antwort: Er ergibt den HTTP-Status `500` im einheitlichen Fehlerformat mit dem Code `internal_error`. Das Backend behandelt ihn wie einen nicht erreichbaren Planner.

## Offene Punkte

- **Orte:** Der Auftrag enthält Ortsnamen. Ob der Planner sie in Orts-IDs für DS1 umsetzt, ist offen, siehe [ARCHITECTURE_PROTOTYPE.md](ARCHITECTURE_PROTOTYPE.md#5-offene-punkte).
- **Mehrere Reiseziele** und Gabelflüge sind nicht Teil des Prototyps. Der Rückflug führt immer vom Ziel zurück zum Start.
- **Abstimmung mit DS1** steht aus. Bis dahin ist das Journey-Modell oben das Format, das Provider im Planner liefern müssen.
