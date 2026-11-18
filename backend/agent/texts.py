"""German wording the agent builds from data, without an LLM.

All numbers in the agent's answers come from here, i.e. straight from the
data. A real LLM writes its replies from facts and never sees these drafts;
they are what the agent says without one (the `fallback` of llm.chat). Lists of
connections are always appended by the code.
"""

import datetime

QUESTIONS = {
    "origin": "Von wo möchtest du starten?",
    "destination": "Wohin soll die Reise gehen?",
    "departure": "Wann möchtest du losfliegen? Ein Datum oder ein Zeitraum reicht.",
    "return": "Wann möchtest du zurückfliegen? Wenn du nur den Hinflug brauchst, sag es einfach.",
    "travelers": "Wie viele Personen reisen mit?",
}

FIELD_LABELS = {
    "origin": "Startort",
    "destination": "Ziel",
    "departure": "Reisedatum",
    "return": "Rückflug",
    "travelers": "Anzahl der Reisenden",
    "budget": "Budget",
    "max_stops": "Umstiege",
    "trip_type": "Reiseart",
}

# English names of the fields, for the instructions to the LLM.
FIELD_LABELS_EN = {
    "origin": "city the trip starts in",
    "destination": "destination city",
    "departure": "departure date or period",
    "return": "date or period of the return flight, or whether the user only needs a one-way flight",
    "travelers": "number of travellers",
}

PLANNER_UNAVAILABLE = (
    "Die Flugsuche ist gerade nicht erreichbar. Deine Angaben sind gespeichert, "
    "bitte versuch es gleich noch einmal."
)
SEARCH_FAILED = (
    "Bei der Flugsuche ist ein Fehler aufgetreten, deshalb kann ich gerade keine "
    "Verbindungen zeigen. Deine Angaben sind gespeichert, bitte versuch es gleich noch einmal."
)

TAG_LABELS = {"cheapest": "günstigste", "fastest": "schnellste", "recommended": "Empfehlung"}


def money(price: dict | None) -> str:
    if price is None:
        return "Preis unbekannt"
    amount = f"{price['amount']:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    symbol = "€" if price["currency"] == "EUR" else price["currency"]
    basis = "pro Person" if price["basis"] == "per_person" else "insgesamt"
    return f"{amount} {symbol} {basis}"


def duration(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest:02d} min" if hours else f"{rest} min"


def date(iso: str) -> str:
    return datetime.date.fromisoformat(iso[:10]).strftime("%d.%m.%Y")


def window(departure: dict) -> str:
    if departure["earliest"] == departure["latest"]:
        return f"am {date(departure['earliest'])}"
    return f"zwischen {date(departure['earliest'])} und {date(departure['latest'])}"


def people(count: int) -> str:
    return "1 Person" if count == 1 else f"{count} Personen"


def stops(journey: dict) -> str:
    if journey["stops"] == 0:
        return "direkt"
    via = ", ".join(leg["destination"] for leg in journey["legs"][:-1])
    word = "Umstieg" if journey["stops"] == 1 else "Umstiege"
    return f"{journey['stops']} {word} ({via})"


def total_price(journey: dict) -> dict | None:
    """Price of the whole trip: both flights for a round trip."""
    return journey.get("total_price") or journey["price"]


def flight_line(part: dict) -> str:
    start = part["legs"][0]["departure"]
    return (
        f"{money(part['price'])} · {duration(part['duration_minutes'])} · "
        f"{stops(part)} · ab {date(start)} {start[11:16]} Uhr"
    )


def journey_line(number: int, journey: dict, review: dict) -> str:
    notes = review.get(journey["id"], {})
    tags = [TAG_LABELS[tag] for tag in notes.get("tags", [])]
    inbound = journey.get("inbound")
    if inbound:
        line = f"{number}. {money(total_price(journey))} für Hin- und Rückflug"
    else:
        line = f"{number}. {flight_line(journey)}"
    if tags:
        line += f" · {', '.join(tags)}"
    if inbound:
        line += f"\n   Hin: {flight_line(journey)}\n   Zurück: {flight_line(inbound)}"
    for warning in notes.get("warnings", []):
        line += f"\n   Achtung: {warning}"
    return line


def journey_list(journeys: list[dict], review: dict) -> str:
    return "\n".join(
        journey_line(number, journey, review) for number, journey in enumerate(journeys, start=1)
    )


def summary(request: dict) -> str:
    text = f"{request['origin']} nach {request['destination']} {window(request['departure'])}"
    if request.get("return"):
        text += f", zurück {window(request['return'])},"
    text += f" für {people(request['travelers'])}"
    if request["max_price"]:
        text += f", höchstens {money(request['max_price'])}"
    if request["max_stops"] is not None:
        text += ", nur direkt" if request["max_stops"] == 0 else (
            f", höchstens {request['max_stops']} Umstieg"
            + ("" if request["max_stops"] == 1 else "e")
        )
    return text


def results_intro(request: dict, journeys: list[dict]) -> str:
    count = "eine Verbindung" if len(journeys) == 1 else f"{len(journeys)} Verbindungen"
    return (
        f"Ich habe alles, was ich brauche: {summary(request)}. "
        f"Dafür habe ich {count} gefunden:"
    )


def confirmation(state, guessed: list[str]) -> str:
    """Ask the user to confirm the required values the agent only guessed."""
    parts = []
    for name in guessed:
        value = state.value(name)
        if name == "departure":
            parts.append(f"Abflug {window(value)}")
        elif name == "return":
            parts.append(f"Rückflug {window(value)}")
        elif name == "travelers":
            parts.append(people(value))
        else:
            parts.append(f"{FIELD_LABELS[name]} {value}")
    return (
        f"Ich habe das so verstanden: {', '.join(parts)}. "
        "Passt das, oder möchtest du es genauer angeben?"
    )


def nothing_changed(request: dict) -> str:
    return (
        f"Deine Suche steht weiterhin: {summary(request)}. "
        "Sag mir einfach, was ich ändern soll, zum Beispiel Datum, Budget oder Umstiege."
    )


def no_results(request: dict, details: dict) -> str:
    closest = details["closest_journey"]
    way = {"outbound": " für den Hinflug", "inbound": " für den Rückflug"}.get(
        details.get("direction"), ""
    )
    text = f"Für {summary(request)} habe ich leider nichts gefunden. "
    if details["reason"] == "budget":
        text += "Alle Verbindungen liegen über deinem Budget."
        if closest:
            text += f" Die günstigste kostet {money(total_price(closest))}."
        text += " Du könntest das Budget erhöhen oder beim Datum flexibler sein."
    elif details["reason"] == "max_stops":
        text += f"Es gibt{way} keine Verbindung mit so wenigen Umstiegen."
        if closest:
            text += f" Die beste hat {stops(closest)}."
        text += " Du könntest mehr Umstiege zulassen."
    else:
        text += (
            f"An diesen Tagen gibt es{way} keine Verbindung auf dieser Strecke. "
            "Du könntest ein anderes Datum oder einen Zeitraum angeben."
        )
    return text


def rejected(names: list[str]) -> str:
    labels = ", ".join(FIELD_LABELS.get(name, name) for name in names)
    return f"Diese Angabe konnte ich nicht übernehmen: {labels}. "
