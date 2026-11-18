"""Main-Agent: one turn of the conversation.

The code decides what happens (which values are valid, what is asked next,
when to search). The LLM reads free text and writes the replies.

    read the message  →  ask for the next missing field      (AG05, AG06)
                      →  or have an assumed value confirmed
                      →  or search and explain                (AG07)
                      →  or just answer, if nothing changed

Everything the LLM reads from a message ends up in exactly one of three
places: in the trip state, in `rejected` with a reason the user is told, or in
`note`. Nothing is dropped silently; `Reading.dropped` exists to prove that in
tests and test conversations.
"""

import datetime
from dataclasses import dataclass, field

from django.conf import settings

from agent import optimizer, places, prompts, texts
from agent.planner_client import PlannerUnavailable
from llm import Message
from planning.trip_state import CONFIRMED, INFERRED, ONE_WAY, REQUIRED_FIELDS, ROUND_TRIP, TripState

# How many earlier messages the LLM sees.
HISTORY_LENGTH = 8

# Fields the user can take back ("budget doesn't matter", "any number of stops").
CLEARABLE = ("budget", "max_stops", "return", "departure", "origin", "destination", "travelers")
# Parts of the flat LLM answer and the trip-state field they belong to.
_PARTS = {
    "departure_earliest": "departure", "departure_latest": "departure",
    "return_earliest": "return", "return_latest": "return",
    "budget_amount": "budget", "budget_basis": "budget",
    "one_way": "trip_type",
}


@dataclass
class Turn:
    reply: str
    #: Search result for the frontend, or None if the agent did not search.
    result: dict | None
    #: Fields whose new values were invalid and not taken over, with the reason.
    rejected: dict[str, str]


@dataclass
class Reading:
    """What the LLM took from one user message and what became of it."""

    rejected: dict[str, str] = field(default_factory=dict)
    intent: str = "trip_info"
    note: str | None = None
    #: What the LLM returned, as trip-state changes (for checks and logs).
    changes: dict = field(default_factory=dict)
    #: Fields the LLM returned that are neither in the state nor rejected.
    #: Must always be empty; anything here is a bug in the code, not in the LLM.
    dropped: list[str] = field(default_factory=list)


def handle_message(
    state: TripState,
    text: str,
    *,
    history: list[Message],
    llm,
    planner,
    today: datetime.date | None = None,
    previous_state: dict | None = None,
    searched_before: bool = False,
) -> Turn:
    """Process one user message. `state` is changed in place; saving is the caller's job.

    `previous_state` is the state before this request (before form fields were
    applied); together with `searched_before` it tells whether a new search
    would show anything new.
    """
    today = today or datetime.date.today()
    before = previous_state if previous_state is not None else state.to_dict()
    # Values set in the form (the caller applied them before this call). They
    # are known before the message is read, so a short answer such as "so"
    # or "passt" is read against them and the next question skips them.
    form = state.to_dict()
    form_changes = [name for name in form if form[name] != before.get(name)]
    reading = Reading()
    if text:
        reading = read_message(
            state, text, history=history, llm=llm, today=today, catalog=places.catalog(planner)
        )
    after = state.to_dict()
    changed = after != before
    if form_changes:
        # Tell the reply step what the user set in the form, so it confirms it.
        form_note = (
            "Der Nutzer hat im Formular geändert: "
            + ", ".join(texts.FIELD_LABELS[name] for name in form_changes)
            + ". Bestätige das kurz und frage nicht danach."
        )
        reading.note = f"{form_note} {reading.note}" if reading.note else form_note

    def reply(task: str, facts: dict, draft: str) -> str:
        """Let the LLM write the reply from facts; `draft` is the answer without an LLM."""
        instruction = prompts.reply_instruction(
            task=task, facts=facts, user_text=text, note=reading.note, rejected=reading.rejected
        )
        if reading.rejected:
            draft = texts.rejected(list(reading.rejected)) + draft
        answer = llm.chat(
            [*history[-HISTORY_LENGTH:], Message("user", instruction)],
            system=prompts.reply_system(state=state.to_dict()),
            fallback=draft,
        )
        return " ".join(answer.split())

    # 1. Something required is missing: ask for it, one field at a time.
    missing = state.missing_required_fields()
    if missing:
        task = prompts.TASK_ASK.format(label=texts.FIELD_LABELS_EN[missing[0]])
        return Turn(reply(task, {}, texts.QUESTIONS[missing[0]]), None, reading.rejected)

    # 2. A required value was only assumed: have it confirmed before searching.
    assumed = [name for name in REQUIRED_FIELDS if state.provenance(name) == INFERRED]
    if assumed:
        facts = {"assumed": {name: state.value(name) for name in assumed}}
        draft = texts.confirmation(state, assumed)
        return Turn(reply(prompts.TASK_CONFIRM, facts, draft), None, reading.rejected)

    search_request = build_search_request(state)

    # 3. Nothing new since the last search and the user is not giving trip
    #    data: answer without searching again.
    if text and searched_before and not changed and reading.intent != "trip_info":
        draft = texts.nothing_changed(search_request)
        facts = {"current_search": search_request}
        return Turn(reply(prompts.TASK_TALK, facts, draft), None, reading.rejected)

    # 4. Search.
    try:
        answer = planner.plan(search_request)
    except PlannerUnavailable:
        return Turn(texts.PLANNER_UNAVAILABLE, _result("error"), reading.rejected)
    if answer["status"] == "error":
        return Turn(texts.SEARCH_FAILED, _result("error"), reading.rejected)

    use_optimizer = settings.OPTIMIZATION_AGENT_ENABLED
    if answer["status"] == "ok":
        review = optimizer.review(answer["journeys"]) if use_optimizer else {}
        facts = {"search": search_request, "connections_found": len(answer["journeys"])}
        intro = reply(
            prompts.TASK_RESULTS, facts, texts.results_intro(search_request, answer["journeys"])
        )
        # Prices and times in the list never pass through the LLM: the code appends it.
        listing = texts.journey_list(answer["journeys"], review)
        result = _result("ok", journeys=answer["journeys"], review=review)
        return Turn(f"{intro}\n{listing}", result, reading.rejected)

    details = answer["no_results"]
    draft = texts.no_results(search_request, details)
    closest = details["closest_journey"]
    facts = {
        "search": search_request,
        "reason": details["reason"],
        "direction": details.get("direction"),
        "closest_outside_criteria": closest
        and {"price": texts.total_price(closest), "stops": closest["stops"]},
        "alternative": None,
    }
    alternative = None
    if use_optimizer:
        alternative = optimizer.find_alternative(
            search_request, details, llm=llm, planner=planner, today=today
        )
    listing = ""
    if alternative:
        draft += " " + alternative["description"]
        relaxed = alternative["request"]
        facts["alternative"] = {
            "change": alternative["strategy"],
            "departure": relaxed["departure"],
            "return": relaxed["return"],
            "max_stops": relaxed["max_stops"],
            "connections_found": len(alternative["journeys"]),
        }
        listing = "\n" + texts.journey_list(alternative["journeys"], alternative["review"])
    result = _result("no_results", no_results=details, alternative=alternative)
    return Turn(reply(prompts.TASK_NO_RESULTS, facts, draft) + listing, result, reading.rejected)


def read_message(
    state: TripState,
    text: str,
    *,
    history: list[Message],
    llm,
    today: datetime.date,
    catalog: "places.Catalog | None" = None,
) -> Reading:
    """AG05: let the LLM read the message, then validate every value in code."""
    missing = state.missing_required_fields()
    assumed_before = [name for name in REQUIRED_FIELDS if state.provenance(name) == INFERRED]
    asked = missing[0] if missing else ("confirmation" if assumed_before else None)
    data = llm.structured(
        [*history[-HISTORY_LENGTH:], Message("user", text)],
        schema=prompts.EXTRACTION_SCHEMA,
        system=prompts.extraction_system(
            today=today, state=state.to_dict(), asked=asked, awaiting=assumed_before
        ),
    )
    changes = _changes(data)
    before = state.to_dict()
    # The LLM names the parts it only assumed; map them to trip-state fields.
    assumed = {_PARTS.get(name, name) for name in _names(data.get("inferred"))}
    # One call for everything the message says, so that values of the same
    # message are checked against each other and not against outdated ones.
    # Places are matched against the planner's list: "lisbon" becomes
    # "Lissabon", a place without flights is rejected with the reason.
    checked = dict(changes)
    unknown_places = catalog.check(checked) if catalog else {}
    rejected = state.apply(checked, inferred=assumed, today=today)
    rejected.update(unknown_places)

    # A "yes" confirms assumed values; values changed in this message are not affected.
    confirmed = {name for name in _names(data.get("confirmed")) if name not in changes}
    # The agent asks only once: if it named its assumption last time and the user
    # carries on with other trip data without correcting it, the assumption stands.
    if asked == "confirmation" and changes:
        confirmed |= {name for name in assumed_before if name not in changes}
    state.confirm(confirmed)

    intent = data.get("intent")
    note = data.get("note")
    note = note.strip() if isinstance(note, str) and note.strip() else None
    # Older values that the new statement replaced: the reply should mention
    # that they are open again, so the user is not surprised by the question.
    for name in REQUIRED_FIELDS:
        if before[name]["value"] is not None and state.value(name) is None and name not in changes:
            if not (name == "return" and state.is_one_way()):
                reopened = (
                    f"Die bisherige Angabe „{texts.FIELD_LABELS[name]}“ passt nicht mehr zur "
                    "neuen Aussage und ist wieder offen."
                )
                note = f"{note} {reopened}" if note else reopened

    return Reading(
        rejected=rejected,
        intent=intent if intent in ("trip_info", "question", "smalltalk", "other") else "other",
        note=note,
        changes=changes,
        dropped=[
            name
            for name, value in changes.items()
            if name not in rejected and not _took_effect(state, name, checked.get(name, value))
        ],
    )


def _took_effect(state: TripState, name: str, value) -> bool:
    """Whether a value the LLM returned is reflected in the state."""
    current = state.value(name)
    if value is None:
        return current is None
    if current is None:
        # The LLM gave a value, but the field is empty and nothing was rejected.
        return False
    if name == "trip_type":
        # "one way" plus a return date in one message: the date wins.
        return current == value or (value == ONE_WAY and state.value("return") is not None)
    return True


def _names(value) -> set[str]:
    return {item for item in value if isinstance(item, str)} if isinstance(value, list) else set()


def _window(data: dict, prefix: str) -> dict | None:
    earliest, latest = data.get(f"{prefix}_earliest"), data.get(f"{prefix}_latest")
    if earliest is None and latest is None:
        return None
    return {
        "earliest": earliest if earliest is not None else latest,
        "latest": latest if latest is not None else earliest,
    }


def _changes(data: dict) -> dict:
    """Turn the flat LLM answer into trip-state values; null means "not mentioned"."""
    changes = {
        name: data[name]
        for name in ("origin", "destination", "travelers", "max_stops")
        if data.get(name) is not None
    }
    for name in ("departure", "return"):
        window = _window(data, name)
        if window is not None:
            changes[name] = window
    if data.get("budget_amount") is not None:
        changes["budget"] = {
            "amount": data["budget_amount"],
            "currency": "EUR",
            "basis": data.get("budget_basis") or "per_person",
        }
    if isinstance(data.get("one_way"), bool):
        changes["trip_type"] = ONE_WAY if data["one_way"] else ROUND_TRIP
    # "Budget doesn't matter": take the value back, unless the same message sets it.
    for name in _names(data.get("cleared")):
        if name in CLEARABLE and name not in changes:
            changes[name] = None
    return changes


def build_search_request(state: TripState) -> dict:
    """AG04: the complete trip state as a search request for the Journey Planner."""
    assert state.is_complete(), "search needs " + ", ".join(REQUIRED_FIELDS)
    return {
        "origin": state.value("origin"),
        "destination": state.value("destination"),
        "departure": state.value("departure"),
        "return": None if state.is_one_way() else state.value("return"),
        "travelers": state.value("travelers"),
        "max_price": state.value("budget"),
        "max_stops": state.value("max_stops"),
        "modes": ["flight"],
    }


def _result(status, *, journeys=(), review=None, no_results=None, alternative=None) -> dict:
    return {
        "status": status,
        "journeys": list(journeys),
        "review": review or {},
        "no_results": no_results,
        "alternative": alternative,
    }
