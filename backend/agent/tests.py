"""Tests for the Main-Agent, the Optimization Agent and the chat endpoint.

No test needs an LLM or a running Journey Planner: the LLM is the scripted
FakeLLM or the rule-based OfflineLLM, the planner a stub that answers with the
shared contract examples from docs/contracts/search-v1/.
"""

import copy
import datetime
import json
import urllib.error
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from agent import main_agent, optimizer, texts
from agent.main_agent import build_search_request, handle_message
from agent.planner_client import PlannerClient, PlannerUnavailable
from llm import FakeLLM, LLMQuotaExceeded, LLMTimeout, Message
from llm.offline import OfflineLLM
from planning.models import PlanningSession
from planning.trip_state import CONFIRMED, INFERRED, ONE_WAY, ROUND_TRIP, UNKNOWN, TripState

# In the repository: <repo>/docs/…; in the container the folder is mounted at /docs/….
EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "search-v1"
TODAY = datetime.date(2026, 11, 15)
SENTENCE = "Ich will am 20. Mai mit 2 Leuten von Berlin nach Lissabon"
# A complete one-way trip; it becomes the search request of request.json.
COMPLETE = {
    "origin": "Berlin",
    "destination": "Lissabon",
    "departure": "2027-05-20",
    "travelers": 2,
    "trip_type": "one_way",
}
# A complete round trip; it becomes the search request of request_round_trip.json.
ROUND = {
    "origin": "Berlin",
    "destination": "Lissabon",
    "departure": "2027-05-20",
    "return": "2027-05-27",
    "travelers": 2,
}
REOPENED = "„{label}“ passt nicht mehr zur neuen Aussage und ist wieder offen."


def example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def day(iso: str) -> dict:
    return {"earliest": iso, "latest": iso}


def extraction(**values) -> dict:
    """An LLM answer for the extraction step; everything not given is null."""
    empty = dict.fromkeys(
        ("origin", "destination", "departure_earliest", "departure_latest",
         "return_earliest", "return_latest", "one_way",
         "travelers", "budget_amount", "budget_basis", "max_stops")
    )
    return {
        **empty, "inferred": [], "confirmed": [], "cleared": [],
        "intent": "trip_info", "note": None, **values,
    }


class StubPlanner:
    """Answers with prepared responses and records the search requests."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def plan(self, search_request):
        self.requests.append(copy.deepcopy(search_request))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return copy.deepcopy(answer)


def offline():
    return OfflineLLM(today=TODAY)


_read_message = main_agent.read_message
_readings = []


def assert_nothing_dropped(reading) -> None:
    """Everything the LLM returned is in the state or rejected with a reason."""
    if reading.dropped:
        raise AssertionError(
            f"Values of the LLM were dropped silently: {reading.dropped} "
            f"(changes {reading.changes}, rejected {reading.rejected})"
        )


def checked_read_message(*args, **kwargs):
    """`read_message`, with the check that nothing was dropped; used by every turn in the tests."""
    reading = _read_message(*args, **kwargs)
    assert_nothing_dropped(reading)
    _readings.append(reading)
    return reading


def read(state, text, *, llm, history=()):
    """Only the reading step of a turn; returns the `Reading`."""
    with patch("llm.base.logger"):
        return checked_read_message(state, text, history=list(history), llm=llm, today=TODAY)


def turn(
    state, text, *, llm, planner=None, history=(), searched_before=False, previous_state=None
):
    """One turn of the agent. The result also has `reading` (None for a turn without text)."""
    del _readings[:]
    with patch("llm.base.logger"), patch("agent.main_agent.read_message", checked_read_message):
        result = handle_message(
            state, text, history=list(history), llm=llm, planner=planner or StubPlanner(),
            today=TODAY, searched_before=searched_before, previous_state=previous_state,
        )
    result.reading = _readings[-1] if _readings else None
    return result


def complete_state(**extra) -> TripState:
    """A complete one-way trip."""
    state = TripState()
    rejected = state.apply({**COMPLETE, **extra}, today=TODAY)
    assert rejected == {}, rejected
    return state


def round_state(**extra) -> TripState:
    """A complete round trip."""
    state = TripState()
    rejected = state.apply({**ROUND, **extra}, today=TODAY)
    assert rejected == {}, rejected
    return state


def instruction_of(llm, call: int = -1) -> str:
    """What the reply step was told (the last message of that LLM call)."""
    return llm.calls[call]["messages"][-1].content


class ExtractionTests(SimpleTestCase):
    """AG05: chat input reaches the trip state only after validation."""

    def test_example_sentence_fills_four_required_fields_and_the_return_is_asked(self):
        state = TripState()
        planner = StubPlanner()
        result = turn(state, SENTENCE, llm=offline(), planner=planner)
        self.assertEqual(state.value("origin"), "Berlin")
        self.assertEqual(state.value("destination"), "Lissabon")
        self.assertEqual(
            state.value("departure"), {"earliest": "2027-05-20", "latest": "2027-05-20"}
        )
        self.assertEqual(state.value("travelers"), 2)
        self.assertEqual(state.provenance("origin"), CONFIRMED)
        # The sentence says nothing about the way back: no search yet.
        self.assertEqual(state.missing_required_fields(), ["return"])
        self.assertEqual(result.reply, texts.QUESTIONS["return"])
        self.assertIsNone(result.result)
        self.assertEqual(planner.requests, [])

    def test_llm_answer_is_validated_and_invalid_values_are_dropped(self):
        llm = FakeLLM([
            extraction(
                origin="Berlin",
                travelers=0,
                departure_earliest="2020-01-01",
                departure_latest="2020-01-01",
                budget_amount=-5,
                max_stops="none",
            ),
            "Wohin?",
        ])
        state = TripState()
        result = turn(state, "…", llm=llm)
        self.assertEqual(state.value("origin"), "Berlin")
        for name in ("travelers", "departure", "budget", "max_stops"):
            self.assertIsNone(state.value(name), name)
        self.assertEqual(set(result.rejected), {"travelers", "departure", "budget", "max_stops"})
        # The reply step is told what could not be used and why.
        self.assertIn("Values that could not be used", llm.calls[1]["messages"][-1].content)
        self.assertIn("konnte ich nicht übernehmen", llm.calls[1]["fallback"])

    def test_guessed_values_are_marked_inferred(self):
        llm = FakeLLM([
            extraction(
                origin="Berlin", destination="Lissabon", travelers=1,
                budget_amount=300, budget_basis="per_person",
                inferred=["travelers", "budget_amount"],
            ),
            "Wann?",
        ])
        state = TripState()
        turn(state, "Ich fliege von Berlin nach Lissabon", llm=llm)
        self.assertEqual(state.provenance("origin"), CONFIRMED)
        self.assertEqual(state.provenance("travelers"), INFERRED)
        self.assertEqual(state.provenance("budget"), INFERRED)

    def test_a_guess_replaces_what_the_user_confirmed_and_is_stored_as_a_guess(self):
        # The latest statement wins, also when the LLM only assumed its value.
        state = TripState()
        state.apply({"travelers": 2}, today=TODAY)
        llm = FakeLLM([extraction(travelers=5, inferred=["travelers"]), "Von wo?"])
        result = turn(state, "wir sind eine Gruppe", llm=llm)
        self.assertEqual(state.value("travelers"), 5)
        self.assertEqual(state.provenance("travelers"), INFERRED)
        self.assertEqual(result.rejected, {})
        self.assertEqual(result.reading.changes, {"travelers": 5})
        self.assertNotIn("konnte ich nicht", instruction_of(llm))

    def test_a_guess_that_replaced_a_confirmed_value_is_confirmed_before_searching(self):
        planner = StubPlanner()
        state = complete_state()
        llm = FakeLLM([
            extraction(
                departure_earliest="2027-06-01", departure_latest="2027-06-30",
                inferred=["departure"],
            ),
            "Meinst du im Juni?",
        ])
        result = turn(state, "doch lieber im Sommer", llm=llm, planner=planner, searched_before=True)
        self.assertEqual(
            state.value("departure"), {"earliest": "2027-06-01", "latest": "2027-06-30"}
        )
        self.assertEqual(state.provenance("departure"), INFERRED)
        self.assertIsNone(result.result)
        self.assertEqual(planner.requests, [])
        self.assertIn("Do not search yet", instruction_of(llm))
        self.assertIn("zwischen 01.06.2027 und 30.06.2027", llm.calls[1]["fallback"])

    def test_parts_named_as_inferred_mark_their_field(self):
        llm = FakeLLM([
            extraction(
                departure_earliest="2027-05-20", departure_latest="2027-05-20",
                return_earliest="2027-05-27", return_latest="2027-05-29",
                one_way=False, budget_amount=300,
                inferred=["return_latest", "one_way", "budget_amount", "hotel", 7],
            ),
            "Von wo?",
        ])
        state = TripState()
        turn(state, "…", llm=llm)
        self.assertEqual(state.provenance("departure"), CONFIRMED)
        self.assertEqual(state.provenance("return"), INFERRED)
        self.assertEqual(state.provenance("trip_type"), INFERRED)
        self.assertEqual(state.provenance("budget"), INFERRED)

    def test_an_invalid_value_is_mentioned_even_when_the_agent_searches(self):
        llm = FakeLLM([extraction(travelers=0), "…"])
        state = complete_state()
        result = turn(state, "wir sind 0", llm=llm, planner=StubPlanner(example("response_ok.json")))
        self.assertEqual(state.value("travelers"), 2)
        self.assertEqual(list(result.rejected), ["travelers"])
        instruction = llm.calls[1]["messages"][-1].content
        self.assertIn("Values that could not be used", instruction)
        self.assertIn("at least 1", instruction)
        fallback = llm.calls[1]["fallback"]
        self.assertIn("konnte ich nicht übernehmen: Anzahl der Reisenden", fallback)
        self.assertIn("5 Verbindungen", fallback)

    def test_the_llm_sees_today_the_known_state_and_the_asked_field(self):
        state = TripState()
        state.apply({"origin": "Berlin"}, today=TODAY)
        llm = FakeLLM([extraction(), "Wohin?"])
        history = [Message("assistant", "Wohin soll die Reise gehen?")]
        turn(state, "weiß nicht", llm=llm, history=history)
        call = llm.calls[0]
        self.assertIn("Today: 2026-11-15", call["system"])
        self.assertIn("Asked field: destination", call["system"])
        self.assertIn('"Berlin"', call["system"])
        self.assertEqual(call["messages"][-1], Message("user", "weiß nicht"))
        self.assertEqual(call["messages"][0], history[0])

    def test_window_and_budget_are_assembled(self):
        llm = FakeLLM([
            extraction(
                departure_earliest="2027-05-20", departure_latest="2027-05-24",
                return_earliest="2027-05-27", return_latest="2027-05-30",
                budget_amount=450.5, budget_basis="trip_total", max_stops=0,
            ),
            "Von wo?",
        ])
        state = TripState()
        result = turn(state, "…", llm=llm)
        self.assertEqual(
            state.value("departure"), {"earliest": "2027-05-20", "latest": "2027-05-24"}
        )
        self.assertEqual(
            state.value("return"), {"earliest": "2027-05-27", "latest": "2027-05-30"}
        )
        self.assertEqual(
            result.reading.changes,
            {
                "departure": {"earliest": "2027-05-20", "latest": "2027-05-24"},
                "return": {"earliest": "2027-05-27", "latest": "2027-05-30"},
                "budget": {"amount": 450.5, "currency": "EUR", "basis": "trip_total"},
                "max_stops": 0,
            },
        )
        self.assertEqual(
            state.value("budget"), {"amount": 450.5, "currency": "EUR", "basis": "trip_total"}
        )
        self.assertEqual(state.value("max_stops"), 0)


class ConversationTests(SimpleTestCase):
    """What makes the agent cope with vague, off-topic or contradictory messages."""

    def test_a_guessed_required_value_is_confirmed_before_searching(self):
        planner = StubPlanner(example("response_ok.json"))
        llm = FakeLLM([
            extraction(
                origin="Berlin", destination="Lissabon", travelers=2,
                departure_earliest="2027-03-20", departure_latest="2027-06-20",
                one_way=True, inferred=["departure_earliest", "departure_latest"],
            ),
            "Meinst du zwischen März und Juni?",
        ])
        state = TripState()
        result = turn(
            state, "im Frühling von Berlin nach Lissabon, zu zweit, nur hin", llm=llm, planner=planner
        )
        self.assertIsNone(result.result)
        self.assertEqual(planner.requests, [])
        self.assertEqual(state.provenance("departure"), INFERRED)
        instruction = llm.calls[1]["messages"][-1].content
        self.assertIn("Do not search yet", instruction)
        self.assertIn('"assumed": {"departure": {"earliest": "2027-03-20"', instruction)
        # Without an LLM the agent would ask this:
        self.assertIn("zwischen 20.03.2027 und 20.06.2027", llm.calls[1]["fallback"])

    def test_a_yes_confirms_the_guess_and_starts_the_search(self):
        planner = StubPlanner(example("response_ok.json"))
        state = complete_state()
        state.apply({"departure": None}, today=TODAY)
        state.apply({"departure": "2027-05-20"}, provenance=INFERRED, today=TODAY)
        llm = FakeLLM([extraction(confirmed=["departure"]), "Alles klar."])
        result = turn(state, "ja passt", llm=llm, planner=planner)
        self.assertEqual(state.provenance("departure"), CONFIRMED)
        self.assertEqual(result.result["status"], "ok")
        self.assertEqual(len(planner.requests), 1)

    def test_a_new_value_wins_over_a_confirmation_in_the_same_message(self):
        state = complete_state()
        state.apply({"departure": None}, today=TODAY)
        state.apply({"departure": "2027-05-20"}, provenance=INFERRED, today=TODAY)
        llm = FakeLLM([
            extraction(
                departure_earliest="2027-06-01", departure_latest="2027-06-01",
                confirmed=["departure"],
            ),
            "Okay.",
        ])
        turn(state, "ja, aber lieber am 1. Juni", llm=llm, planner=StubPlanner(example("response_ok.json")))
        self.assertEqual(state.value("departure"), {"earliest": "2027-06-01", "latest": "2027-06-01"})
        self.assertEqual(state.provenance("departure"), CONFIRMED)

    def test_an_assumption_is_asked_about_only_once(self):
        planner = StubPlanner(example("response_ok.json"))
        state = complete_state()
        state.apply({"travelers": None}, today=TODAY)
        state.apply({"travelers": 2}, provenance=INFERRED, today=TODAY)
        # The user does not answer the question but gives other trip data.
        llm = FakeLLM([extraction(budget_amount=150), "Mit 150 € habe ich etwas gefunden:"])
        result = turn(state, "und wenn ich bis 150 gehe?", llm=llm, planner=planner)
        self.assertEqual(state.provenance("travelers"), CONFIRMED)
        self.assertEqual(result.result["status"], "ok")

    def test_an_assumption_stays_open_when_the_user_says_nothing_about_the_trip(self):
        state = complete_state()
        state.apply({"travelers": None}, today=TODAY)
        state.apply({"travelers": 2}, provenance=INFERRED, today=TODAY)
        llm = FakeLLM([extraction(intent="other"), "Stimmt die Zahl?"])
        result = turn(state, "hä?", llm=llm)
        self.assertEqual(state.provenance("travelers"), INFERRED)
        self.assertIsNone(result.result)

    def test_no_new_search_when_nothing_changed(self):
        planner = StubPlanner()
        llm = FakeLLM([extraction(intent="smalltalk", note="Der Nutzer bedankt sich."), "Gern!"])
        result = turn(
            complete_state(), "danke dir", llm=llm, planner=planner, searched_before=True
        )
        self.assertEqual(result.reply, "Gern!")
        self.assertIsNone(result.result)
        self.assertEqual(planner.requests, [])
        instruction = llm.calls[1]["messages"][-1].content
        self.assertIn("Der Nutzer bedankt sich.", instruction)
        self.assertIn('"current_search"', instruction)
        self.assertIn("Deine Suche steht weiterhin", llm.calls[1]["fallback"])

    def test_a_change_after_a_search_searches_again(self):
        planner = StubPlanner(example("response_ok.json"))
        llm = FakeLLM([extraction(max_stops=0), "Nur direkt, verstanden."])
        result = turn(complete_state(), "nur direkt", llm=llm, planner=planner, searched_before=True)
        self.assertEqual(result.result["status"], "ok")
        self.assertEqual(planner.requests[0]["max_stops"], 0)

    def test_the_first_complete_state_searches_even_without_a_change(self):
        planner = StubPlanner(example("response_ok.json"))
        result = turn(complete_state(), "los", llm=offline(), planner=planner, searched_before=False)
        self.assertEqual(result.result["status"], "ok")

    def test_the_reply_step_gets_the_message_the_note_and_the_history(self):
        llm = FakeLLM([
            extraction(intent="question", note="Der Nutzer fragt nach Hotels, das geht noch nicht."),
            "Hotels kann ich noch nicht. Von wo startest du?",
        ])
        history = [Message("user", "hi"), Message("assistant", "Von wo möchtest du starten?")]
        turn(TripState(), "kannst du auch hotels?", llm=llm, history=history)
        call = llm.calls[1]
        self.assertEqual(call["messages"][:2], history)
        instruction = call["messages"][-1].content
        self.assertIn('"kannst du auch hotels?"', instruction)
        self.assertIn("das geht noch nicht", instruction)
        self.assertIn("city the trip starts in", instruction)
        self.assertIn("cannot book", call["system"])

    def test_same_origin_and_destination_is_rejected_with_the_reason(self):
        llm = FakeLLM([extraction(origin="Hamburg", destination="hamburg"), "Wohin denn?"])
        state = TripState()
        result = turn(state, "von Hamburg nach Hamburg", llm=llm)
        self.assertEqual(state.value("origin"), "Hamburg")
        self.assertIsNone(state.value("destination"))
        self.assertEqual(list(result.rejected), ["destination"])
        instruction = llm.calls[1]["messages"][-1].content
        self.assertIn("must be different", instruction)
        self.assertIn("konnte ich nicht übernehmen: Ziel", llm.calls[1]["fallback"])

    def test_correcting_the_role_of_a_place_asks_for_the_other_one(self):
        # First answer "berlin" was stored as origin; now the user says it is the destination.
        state = TripState()
        state.apply({"origin": "Berlin"}, today=TODAY)
        llm = FakeLLM([
            extraction(destination="Berlin", note="Bayern ist keine Stadt."),
            "Von wo in Bayern startest du?",
        ])
        result = turn(state, "ne ich will nach berlin fahren und komme aus bayern", llm=llm)
        self.assertEqual(state.value("destination"), "Berlin")
        self.assertIsNone(state.value("origin"))
        self.assertEqual(result.rejected, {})
        instruction = llm.calls[1]["messages"][-1].content
        self.assertIn("Ask for the city the trip starts in.", instruction)
        self.assertIn("Bayern ist keine Stadt.", instruction)
        self.assertIn(REOPENED.format(label="Startort"), instruction)
        self.assertEqual(llm.calls[1]["fallback"], texts.QUESTIONS["origin"])
        self.assertEqual(result.reading.changes, {"destination": "Berlin"})
        self.assertEqual(result.reading.dropped, [])

    def test_unknown_intent_and_bad_lists_do_not_break_the_turn(self):
        llm = FakeLLM([
            extraction(intent="dancing", inferred="all", confirmed=None, note="  "),
            "Von wo?",
        ])
        result = turn(TripState(), "…", llm=llm)
        self.assertEqual(result.reply, "Von wo?")


class NextQuestionTests(SimpleTestCase):
    """AG06: the code decides what is asked, the LLM how."""

    def test_everything_missing_asks_for_the_first_field(self):
        llm = FakeLLM([extraction(), "Wo geht es los?"])
        result = turn(TripState(), "Hallo, ich will in den Urlaub", llm=llm)
        self.assertEqual(result.reply, "Wo geht es los?")
        self.assertIsNone(result.result)
        self.assertIn("city the trip starts in", llm.calls[1]["messages"][-1].content)
        self.assertEqual(llm.calls[1]["fallback"], texts.QUESTIONS["origin"])

    def test_one_missing_field_is_asked_and_known_ones_are_not(self):
        state = TripState()
        state.apply({**COMPLETE, "travelers": None}, today=TODAY)
        llm = FakeLLM([extraction(), "Wie viele seid ihr?"])
        turn(state, "ok", llm=llm)
        instruction = llm.calls[1]["messages"][-1].content
        self.assertIn("Ask for the number of travellers.", instruction)
        self.assertEqual(llm.calls[1]["fallback"], texts.QUESTIONS["travelers"])
        for other in ("origin", "destination", "departure", "return"):
            self.assertNotIn(texts.FIELD_LABELS_EN[other], instruction)

    def test_the_return_is_asked_after_the_departure(self):
        state = TripState()
        state.apply({**ROUND, "return": None, "travelers": None}, today=TODAY)
        llm = FakeLLM([extraction(intent="other"), "Und zurück?"])
        result = turn(state, "hm", llm=llm)
        self.assertIsNone(result.result)
        self.assertIn("Asked field: return", llm.calls[0]["system"])
        instruction = instruction_of(llm)
        self.assertIn("Ask for the date or period of the return flight", instruction)
        self.assertIn("one-way", instruction)
        self.assertNotIn(texts.FIELD_LABELS_EN["travelers"], instruction)
        self.assertEqual(llm.calls[1]["fallback"], texts.QUESTIONS["return"])
        self.assertIn("zurückfliegen", texts.QUESTIONS["return"])
        self.assertIn("nur den Hinflug", texts.QUESTIONS["return"])

    def test_a_one_way_trip_is_not_asked_for_the_return(self):
        state = TripState()
        state.apply({**COMPLETE, "travelers": None}, today=TODAY)
        llm = FakeLLM([extraction(intent="other"), "Wie viele?"])
        turn(state, "hm", llm=llm)
        self.assertIn("Asked field: travelers", llm.calls[0]["system"])
        self.assertEqual(llm.calls[1]["fallback"], texts.QUESTIONS["travelers"])

    def test_nothing_missing_summarises_and_searches(self):
        planner = StubPlanner(example("response_ok.json"))
        result = turn(complete_state(), "passt so", llm=offline(), planner=planner)
        self.assertEqual(len(planner.requests), 1)
        self.assertIn("Berlin nach Lissabon am 20.05.2027 für 2 Personen", result.reply)
        self.assertEqual(result.result["status"], "ok")

    def test_a_conversation_needs_one_question_per_missing_field(self):
        state, llm = TripState(), offline()
        planner = StubPlanner(example("response_ok.json"))
        answers = ["Ich möchte verreisen", "Berlin", "Lissabon", "20.05.2027", "nur Hinflug", "2"]
        replies = []
        for answer in answers:
            result = turn(state, answer, llm=llm, planner=planner)
            if result.result is None:
                replies.append(result.reply)
        self.assertEqual(
            replies,
            [texts.QUESTIONS[name] for name in ("origin", "destination", "departure", "return", "travelers")],
        )
        self.assertEqual(result.result["status"], "ok")
        self.assertEqual(state.value("trip_type"), ONE_WAY)
        expected = {**example("request.json"), "max_price": None}
        self.assertEqual(build_search_request(state), expected)
        self.assertEqual(planner.requests, [expected])

    def test_a_round_trip_conversation_needs_one_question_per_missing_field(self):
        state, llm = TripState(), offline()
        planner = StubPlanner(example("response_round_trip.json"))
        answers = ["Ich möchte verreisen", "Berlin", "Lissabon", "20.05.2027", "27.05.2027", "2"]
        replies = []
        for answer in answers:
            result = turn(state, answer, llm=llm, planner=planner)
            if result.result is None:
                replies.append(result.reply)
        self.assertEqual(
            replies,
            [texts.QUESTIONS[name] for name in ("origin", "destination", "departure", "return", "travelers")],
        )
        self.assertEqual(result.result["status"], "ok")
        expected = {**example("request_round_trip.json"), "max_price": None}
        self.assertEqual(build_search_request(state), expected)
        self.assertEqual(planner.requests, [expected])
        self.assertIn("zurück am 27.05.2027", result.reply)
        self.assertIn("   Hin: ", result.reply)
        self.assertIn("   Zurück: ", result.reply)


class SearchAndExplainTests(SimpleTestCase):
    """AG07: search, explain, and survive a planner that does not answer."""

    def test_results_are_passed_on_unchanged_and_explained_from_the_data(self):
        answer = example("response_ok.json")
        planner = StubPlanner(answer)
        state = complete_state(budget=300)
        result = turn(state, "", llm=offline(), planner=planner)
        self.assertEqual(planner.requests, [example("request.json")])
        self.assertEqual(result.result["journeys"], answer["journeys"])
        self.assertIn("98,00 € pro Person", result.reply)
        self.assertIn("8 h 20 min", result.reply)
        self.assertIn("2 Umstiege (Zürich, Madrid)", result.reply)
        self.assertIn("5 Verbindungen", result.reply)

    def test_the_llm_writes_the_intro_and_the_code_appends_the_list(self):
        llm = FakeLLM(["Hier sind deine Flüge."])
        result = turn(complete_state(), "", llm=llm, planner=StubPlanner(example("response_ok.json")))
        intro, _, listing = result.reply.partition("\n")
        self.assertEqual(intro, "Hier sind deine Flüge.")
        # Prices and times never pass through the LLM.
        self.assertIn("189,00 € pro Person", listing)
        self.assertIn("ab 20.05.2027 06:40 Uhr", listing)
        instruction = llm.calls[0]["messages"][-1].content
        self.assertIn('"connections_found": 5', instruction)
        self.assertNotIn("189", instruction)
        self.assertIn("5 Verbindungen", llm.calls[0]["fallback"])

    @override_settings(OPTIMIZATION_AGENT_ENABLED=False)
    def test_no_results_explains_the_reason_and_suggests_a_change(self):
        planner = StubPlanner(example("response_no_results.json"))
        result = turn(complete_state(budget=50), "", llm=offline(), planner=planner)
        self.assertEqual(result.result["status"], "no_results")
        self.assertEqual(result.result["journeys"], [])
        self.assertIsNone(result.result["alternative"])
        self.assertEqual(len(planner.requests), 1)
        self.assertIn("über deinem Budget", result.reply)
        self.assertIn("98,00 € pro Person", result.reply)
        self.assertIn("Budget erhöhen", result.reply)

    def test_unreachable_planner_gives_a_clear_message_instead_of_a_crash(self):
        planner = StubPlanner(PlannerUnavailable("down"))
        result = turn(complete_state(), "", llm=FakeLLM(), planner=planner)
        self.assertEqual(result.reply, texts.PLANNER_UNAVAILABLE)
        self.assertEqual(result.result["status"], "error")

    def test_planner_error_status_is_reported_as_error(self):
        planner = StubPlanner(example("response_error.json"))
        result = turn(complete_state(), "", llm=FakeLLM(), planner=planner)
        self.assertEqual(result.reply, texts.SEARCH_FAILED)
        self.assertEqual(result.result["status"], "error")


class OptimizerReviewTests(SimpleTestCase):
    def setUp(self):
        self.journeys = example("response_ok.json")["journeys"]
        self.review = optimizer.review(self.journeys)

    def by_suffix(self, suffix):
        return next(notes for key, notes in self.review.items() if key.endswith(suffix))

    def test_flags_a_transfer_that_is_too_short(self):
        self.assertEqual(
            self.by_suffix("via-frankfurt")["warnings"],
            ["Nur 25 Minuten zum Umsteigen in Frankfurt."],
        )
        self.assertEqual(self.by_suffix("via-madrid")["warnings"], [])

    def test_marks_cheapest_fastest_and_a_recommendation(self):
        self.assertIn("cheapest", self.by_suffix("via-zuerich-madrid")["tags"])
        self.assertIn("fastest", self.by_suffix("direct-early")["tags"])
        tagged = [key for key, notes in self.review.items() if "recommended" in notes["tags"]]
        self.assertEqual(len(tagged), 1)
        # The recommendation is never a connection with a warning.
        self.assertEqual(self.review[tagged[0]]["warnings"], [])

    def test_flags_implausible_times_long_waits_and_missing_prices(self):
        broken = copy.deepcopy(self.journeys[2])  # via Madrid
        broken["legs"][0]["arrival"] = broken["legs"][0]["departure"]
        broken["legs"][1]["departure"] = "2027-05-20T23:30:00+02:00"
        broken["legs"][1]["arrival"] = "2027-05-21T00:10:00+01:00"
        broken["price"] = None
        warnings = optimizer.review([broken])[broken["id"]]["warnings"]
        self.assertEqual(len(warnings), 3)
        self.assertIn("nicht plausibel", warnings[0])
        self.assertIn("Lange Wartezeit in Madrid", warnings[1])
        self.assertIn("kein Preis", warnings[2])

    def test_every_journey_has_an_entry(self):
        self.assertEqual(set(self.review), {journey["id"] for journey in self.journeys})


class OptimizerAlternativeTests(SimpleTestCase):
    def test_searches_again_with_flexible_dates_and_keeps_the_state(self):
        planner = StubPlanner(example("response_no_results.json"), example("response_ok.json"))
        state = complete_state(budget=50)
        before = state.to_dict()
        result = turn(state, "", llm=offline(), planner=planner)
        self.assertEqual(len(planner.requests), 2)
        self.assertEqual(
            planner.requests[1]["departure"], {"earliest": "2027-05-17", "latest": "2027-05-23"}
        )
        # The budget is the user's decision and is never raised automatically.
        self.assertEqual(planner.requests[1]["max_price"], planner.requests[0]["max_price"])
        alternative = result.result["alternative"]
        self.assertEqual(alternative["strategy"], "flexible_dates")
        self.assertEqual(len(alternative["journeys"]), 5)
        self.assertEqual(result.result["journeys"], [])
        self.assertIn("zwischen 17.05.2027 und 23.05.2027", result.reply)
        self.assertEqual(state.to_dict(), before)

    def test_the_llm_chooses_among_the_allowed_strategies_only(self):
        details = {"reason": "budget", "closest_journey": None}
        request = {**example("request.json"), "max_stops": 0}
        for answer, expected in [
            ({"strategy": "more_stops"}, 1),
            ({"strategy": "raise_budget"}, None),  # not allowed: falls back to the first option
        ]:
            with self.subTest(answer=answer), patch("llm.base.logger"):
                planner = StubPlanner(example("response_ok.json"))
                alternative = optimizer.find_alternative(
                    request, details, llm=FakeLLM([answer]), planner=planner, today=TODAY
                )
                self.assertIsNotNone(alternative)
                changed = planner.requests[0]
                if expected is None:
                    self.assertEqual(alternative["strategy"], "flexible_dates")
                    self.assertEqual(changed["max_stops"], 0)
                else:
                    self.assertEqual(alternative["strategy"], "more_stops")
                    self.assertEqual(changed["max_stops"], expected)
                self.assertEqual(changed["max_price"], request["max_price"])

    def test_tries_at_most_two_searches_and_gives_up(self):
        empty = example("response_no_results.json")
        planner = StubPlanner(empty, empty, empty)
        request = {**example("request.json"), "max_stops": 0}
        details = {"reason": "budget", "closest_journey": None}
        with patch("llm.base.logger"):
            alternative = optimizer.find_alternative(
                request, details, llm=offline(), planner=planner, today=TODAY
            )
        self.assertIsNone(alternative)
        self.assertEqual(len(planner.requests), 2)

    def test_works_without_the_llm(self):
        planner = StubPlanner(example("response_ok.json"))
        request = {**example("request.json"), "max_stops": 0}
        details = {"reason": "budget", "closest_journey": None}
        with patch("llm.base.logger"):
            alternative = optimizer.find_alternative(
                request, details, llm=FakeLLM([LLMTimeout("slow")], max_attempts=1),
                planner=planner, today=TODAY,
            )
        self.assertEqual(alternative["strategy"], "flexible_dates")

    def test_flexible_dates_never_reach_into_the_past(self):
        request = {
            **example("request.json"),
            "departure": {"earliest": "2026-11-16", "latest": "2026-11-16"},
        }
        planner = StubPlanner(example("response_ok.json"))
        optimizer.find_alternative(
            request, {"reason": "no_connection", "closest_journey": None},
            llm=FakeLLM(), planner=planner, today=TODAY,
        )
        self.assertEqual(
            planner.requests[0]["departure"], {"earliest": "2026-11-15", "latest": "2026-11-19"}
        )


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._payload


class PlannerClientTests(SimpleTestCase):
    def make(self):
        return PlannerClient(base_url="http://planner.invalid:8001/", timeout_seconds=3)

    def test_posts_the_request_and_returns_the_answer(self):
        payload = json.dumps(example("response_ok.json")).encode()
        with patch("agent.planner_client.urllib.request.urlopen", return_value=_Response(payload)) as urlopen:
            answer = self.make().plan(example("request.json"))
        self.assertEqual(answer, example("response_ok.json"))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://planner.invalid:8001/plan")
        self.assertEqual(json.loads(request.data), example("request.json"))
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 3)

    def test_every_failure_becomes_planner_unavailable(self):
        http_400 = urllib.error.HTTPError("http://x", 400, "bad", {}, None)
        failures = [
            urllib.error.URLError("refused"),
            TimeoutError("slow"),
            ConnectionResetError("reset"),
            http_400,
        ]
        for failure in failures:
            with (
                self.subTest(type(failure).__name__),
                patch("agent.planner_client.urllib.request.urlopen", side_effect=failure),
                patch("agent.planner_client.logger"),
                self.assertRaises(PlannerUnavailable),
            ):
                self.make().plan(example("request.json"))

    def test_answers_outside_the_contract_are_rejected(self):
        for payload in (b"<html>", b"[]", b'{"status": "maybe", "journeys": []}', b'{"status": "ok"}'):
            with (
                self.subTest(payload),
                patch("agent.planner_client.urllib.request.urlopen", return_value=_Response(payload)),
                patch("agent.planner_client.logger"),
                self.assertRaises(PlannerUnavailable),
            ):
                self.make().plan(example("request.json"))


@override_settings(LLM_PROVIDER="offline")
class ChatEndpointTests(TestCase):
    """AG08, and the end-to-end conversation of IN03 with a fake LLM."""

    def setUp(self):
        self.client = APIClient()
        self.session = PlanningSession.objects.create(title="Chat")
        self.url = f"/api/v1/planning-sessions/{self.session.id}/messages/"
        self.planner = StubPlanner()
        patcher = patch("planning.views.PlannerClient", return_value=self.planner)
        patcher.start()
        self.addCleanup(patcher.stop)
        quiet = patch("llm.base.logger")
        quiet.start()
        self.addCleanup(quiet.stop)
        # Every message read in these tests is checked: nothing may be dropped silently.
        del _readings[:]
        checked = patch("agent.main_agent.read_message", checked_read_message)
        checked.start()
        self.addCleanup(checked.stop)
        self.state_url = f"/api/v1/planning-sessions/{self.session.id}/trip-state/"

    def send(self, **body):
        return self.client.post(self.url, body, format="json")

    def test_form_values_sent_with_a_message_are_known_before_it_is_read(self):
        # The case from the browser: dates typed into the form, then "so" in the chat.
        year = datetime.date.today().year + 1
        self.send(fields={"origin": "München", "destination": "Berlin"})
        llm = FakeLLM([extraction(intent="trip_info"), "Wie viele Personen fliegen mit?"])
        with patch("planning.views.get_llm_client", return_value=llm):
            response = self.send(
                text="so",
                fields={"departure": f"{year}-05-20", "return": f"{year}-05-27"},
            )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["missing_fields"], ["travelers"])
        self.assertEqual(
            body["trip_state"]["return"]["value"],
            {"earliest": f"{year}-05-27", "latest": f"{year}-05-27"},
        )
        # The LLM reads "so" against a state that already holds the form values …
        reading_prompt = llm.calls[0]["system"]
        self.assertIn("Asked field: travelers", reading_prompt)
        self.assertIn(f"{year}-05-27", reading_prompt)
        # … and the reply step is told to confirm them and ask for the next field.
        instruction = llm.calls[1]["messages"][-1].content
        self.assertIn("Der Nutzer hat im Formular geändert: Reisedatum, Rückflug", instruction)
        self.assertIn("Ask for the number of travellers.", instruction)
        self.assertEqual(body["user_message"]["content"], "so")

    def test_an_invalid_form_value_blocks_the_whole_message(self):
        response = self.send(text="so", fields={"departure": "2020-01-01"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("departure", response.json()["error"]["fields"]["fields"])
        self.assertEqual(self.session.messages.count(), 0)

    def test_a_first_message_gets_a_question_and_the_state(self):
        response = self.send(text="Hallo, ich will nach Lissabon")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(set(body), {"user_message", "reply", "trip_state", "missing_fields"})
        self.assertEqual(body["user_message"]["role"], "user")
        self.assertEqual(body["user_message"]["content"], "Hallo, ich will nach Lissabon")
        self.assertIsNone(body["user_message"]["result"])
        self.assertEqual(body["reply"]["role"], "assistant")
        self.assertEqual(body["reply"]["content"], texts.QUESTIONS["origin"])
        self.assertIsNone(body["reply"]["result"])
        self.assertEqual(
            body["trip_state"]["destination"], {"value": "Lissabon", "provenance": "confirmed"}
        )
        self.assertEqual(body["missing_fields"], ["origin", "departure", "return", "travelers"])
        self.assertEqual(len(body["trip_state"]), 8)
        self.assertEqual(
            set(body["reply"]), {"id", "role", "content", "created_at", "result"}
        )

    def test_end_to_end_conversation_reaches_five_journeys(self):
        self.planner.answers = [example("response_ok.json")]
        today = datetime.date.today()
        year = today.year if datetime.date(today.year, 5, 20) >= today else today.year + 1
        response = self.send(text=SENTENCE + ", nur Hinflug, maximal 300 € pro Person")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["missing_fields"], [])
        self.assertEqual(
            body["trip_state"]["trip_type"], {"value": "one_way", "provenance": "confirmed"}
        )
        self.assertEqual(body["trip_state"]["return"], {"value": None, "provenance": "unknown"})
        self.assertEqual(
            self.planner.requests,
            [{
                **example("request.json"),
                "departure": {"earliest": f"{year}-05-20", "latest": f"{year}-05-20"},
            }],
        )
        result = body["reply"]["result"]
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["journeys"], example("response_ok.json")["journeys"])
        self.assertEqual(len(result["journeys"]), 5)
        self.assertEqual(set(result["review"]), {j["id"] for j in result["journeys"]})
        self.assertIsNone(result["alternative"])
        self.assertIn("5 Verbindungen", body["reply"]["content"])

    def test_form_fields_are_confirmed_without_the_llm(self):
        with patch("planning.views.get_llm_client", return_value=FakeLLM(["Wohin?"])) as factory:
            response = self.send(fields={"origin": "Berlin", "travelers": 2})
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIsNone(body["user_message"])
        self.assertEqual(body["trip_state"]["travelers"], {"value": 2, "provenance": "confirmed"})
        self.assertEqual(body["missing_fields"], ["destination", "departure", "return"])
        # Only the question was phrased; nothing was extracted.
        self.assertEqual(len(factory.return_value.calls), 1)

    def test_state_and_history_are_kept_between_requests(self):
        self.send(text="von Berlin")
        self.send(text="nach Rom")
        self.session.refresh_from_db()
        self.assertEqual(self.session.trip_state["origin"]["value"], "Berlin")
        self.assertEqual(self.session.trip_state["destination"]["value"], "Rom")

        history = self.client.get(self.url)
        self.assertEqual(history.status_code, 200)
        page = history.json()
        self.assertEqual(page["count"], 4)
        self.assertEqual(
            [message["role"] for message in page["results"]],
            ["user", "assistant", "user", "assistant"],
        )
        self.assertEqual(page["results"][0]["content"], "von Berlin")

    def test_invalid_input_returns_400(self):
        cases = {
            "empty body": ({}, "non_field_errors"),
            "blank text": ({"text": "   "}, "non_field_errors"),
            "text too long": ({"text": "x" * 2001}, "text"),
            "fields not an object": ({"fields": ["origin"]}, "fields"),
            "invalid field value": ({"fields": {"travelers": 0}}, "fields"),
            "unknown field": ({"fields": {"hotel": "Ritz"}}, "fields"),
        }
        for name, (body, key) in cases.items():
            with self.subTest(name):
                response = self.send(**body)
                self.assertEqual(response.status_code, 400)
                error = response.json()["error"]
                self.assertEqual(error["code"], "validation_error")
                self.assertIn(key, error["fields"])
        self.assertEqual(self.session.messages.count(), 0)
        self.session.refresh_from_db()
        self.assertEqual(self.session.trip_state, {})

    def test_invalid_form_field_names_the_field(self):
        response = self.send(fields={"travelers": 0})
        self.assertIn("travelers", response.json()["error"]["fields"]["fields"])

    def test_unknown_session_returns_404(self):
        url = "/api/v1/planning-sessions/00000000-0000-0000-0000-000000000000/messages/"
        for response in (self.client.post(url, {"text": "Hallo"}, format="json"), self.client.get(url)):
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_llm_failure_returns_503_and_saves_nothing(self):
        for failure in (LLMTimeout("slow"), LLMQuotaExceeded("quota")):
            with (
                self.subTest(type(failure).__name__),
                patch(
                    "planning.views.get_llm_client",
                    return_value=FakeLLM([failure], max_attempts=1),
                ),
                self.assertLogs("planning.views", level="WARNING"),
                self.assertLogs("django.request", level="ERROR"),
            ):
                response = self.send(text="von Berlin")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(
                response.json(),
                {
                    "error": {
                        "code": "service_unavailable",
                        "message": "The language model is temporarily unavailable.",
                    }
                },
            )
        self.assertEqual(self.session.messages.count(), 0)
        self.session.refresh_from_db()
        self.assertEqual(self.session.trip_state, {})

    def test_after_a_failed_search_the_next_message_searches_again(self):
        self.planner.answers = [PlannerUnavailable("down"), example("response_ok.json")]
        self.assertEqual(self.send(fields=COMPLETE).json()["reply"]["result"]["status"], "error")
        retry = self.send(text="nochmal bitte").json()
        self.assertEqual(retry["reply"]["result"]["status"], "ok")
        # After a successful search, a message that is no trip data and changes
        # nothing does not search again. (The offline stand-in reads every
        # message as trip data, so this step needs a scripted LLM.)
        llm = FakeLLM([extraction(intent="smalltalk"), "Gern!"])
        with patch("planning.views.get_llm_client", return_value=llm):
            again = self.send(text="danke").json()
        self.assertIsNone(again["reply"]["result"])
        self.assertEqual(again["reply"]["content"], "Gern!")
        self.assertEqual(len(self.planner.requests), 2)

    def test_unreachable_planner_is_a_normal_answer(self):
        self.planner.answers = [PlannerUnavailable("down")]
        response = self.send(fields=COMPLETE)
        self.assertEqual(response.status_code, 201)
        reply = response.json()["reply"]
        self.assertEqual(reply["content"], texts.PLANNER_UNAVAILABLE)
        self.assertEqual(reply["result"]["status"], "error")

    # --- Round trip and one-way through the endpoint -------------------------

    def test_round_trip_in_one_sentence_lists_outbound_and_return_flights(self):
        self.planner.answers = [example("response_round_trip.json")]
        # Explicit years: the view works with the real current date.
        year = datetime.date.today().year + 1
        response = self.send(
            text=f"Ich will am 20. Mai {year} zu zweit von Berlin nach Lissabon "
            f"und zurück am 27. Mai {year}, maximal 400 € pro Person"
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["missing_fields"], [])
        self.assertEqual(
            self.planner.requests,
            [{
                **example("request_round_trip.json"),
                "departure": day(f"{year}-05-20"),
                "return": day(f"{year}-05-27"),
            }],
        )
        self.assertEqual(
            body["trip_state"]["return"],
            {"value": day(f"{year}-05-27"), "provenance": "confirmed"},
        )
        self.assertEqual(body["trip_state"]["trip_type"], {"value": None, "provenance": "unknown"})
        result = body["reply"]["result"]
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["journeys"], example("response_round_trip.json")["journeys"])
        self.assertEqual(set(result["review"]), {j["id"] for j in result["journeys"]})
        content = body["reply"]["content"]
        self.assertIn(f"zurück am 27.05.{year}", content)
        self.assertIn("5 Verbindungen", content)
        self.assertIn("1. 200,67 € pro Person für Hin- und Rückflug · günstigste", content)
        self.assertEqual(content.count("\n   Hin: "), 5)
        self.assertEqual(content.count("\n   Zurück: "), 5)
        self.assertEqual(len(_readings), 1)
        self.assertEqual(_readings[0].dropped, [])

    def test_round_trip_conversation_asks_for_the_return_and_then_searches(self):
        self.planner.answers = [example("response_round_trip.json")]
        year = datetime.date.today().year + 1
        first = self.send(text=f"Ich will am 20.05.{year} zu zweit von Berlin nach Lissabon").json()
        self.assertEqual(first["missing_fields"], ["return"])
        self.assertEqual(first["reply"]["content"], texts.QUESTIONS["return"])
        self.assertIsNone(first["reply"]["result"])
        self.assertEqual(self.planner.requests, [])

        second = self.send(text=f"27.05.{year}").json()
        self.assertEqual(second["missing_fields"], [])
        self.assertEqual(second["reply"]["result"]["status"], "ok")
        self.assertEqual(
            self.planner.requests,
            [{
                **example("request_round_trip.json"),
                "departure": day(f"{year}-05-20"),
                "return": day(f"{year}-05-27"),
                "max_price": None,
            }],
        )
        self.assertIn("Hin:", second["reply"]["content"])
        self.assertIn("Zurück:", second["reply"]["content"])
        self.assertEqual([reading.dropped for reading in _readings], [[], []])

    def test_one_way_conversation_needs_no_return(self):
        self.planner.answers = [example("response_ok.json")]
        year = datetime.date.today().year + 1
        first = self.send(text=f"Ich will am 20.05.{year} zu zweit von Berlin nach Lissabon").json()
        self.assertEqual(first["reply"]["content"], texts.QUESTIONS["return"])

        second = self.send(text="nur Hinflug").json()
        self.assertEqual(second["missing_fields"], [])
        self.assertEqual(
            second["trip_state"]["trip_type"], {"value": "one_way", "provenance": "confirmed"}
        )
        self.assertEqual(
            self.planner.requests,
            [{**example("request.json"), "departure": day(f"{year}-05-20"), "max_price": None}],
        )
        self.assertIsNone(self.planner.requests[0]["return"])
        content = second["reply"]["content"]
        self.assertIn("5 Verbindungen", content)
        self.assertNotIn("Hin:", content)
        self.assertNotIn("Zurück", content)
        self.assertNotIn("zurück", content)

    def test_one_way_in_one_sentence_searches_at_once(self):
        self.planner.answers = [example("response_ok.json")]
        year = datetime.date.today().year + 1
        body = self.send(
            text=f"Ich will am 20.05.{year} zu zweit von Berlin nach Lissabon, nur Hinflug"
        ).json()
        self.assertEqual(body["missing_fields"], [])
        self.assertEqual(body["reply"]["result"]["status"], "ok")
        self.assertIsNone(self.planner.requests[0]["return"])

    def test_a_place_in_the_wrong_role_is_moved_and_the_other_one_asked_again(self):
        # The original bug: "Berlin" was stored as origin, the user means the destination.
        self.send(text="Hallo")
        self.assertEqual(self.send(text="Berlin").json()["missing_fields"][0], "destination")
        body = self.send(text="Nein, ich will nach Berlin").json()
        self.assertEqual(
            body["trip_state"]["destination"], {"value": "Berlin", "provenance": "confirmed"}
        )
        self.assertEqual(body["trip_state"]["origin"], {"value": None, "provenance": "unknown"})
        self.assertEqual(body["missing_fields"][0], "origin")
        self.assertEqual(body["reply"]["content"], texts.QUESTIONS["origin"])
        self.assertEqual([reading.dropped for reading in _readings], [[], [], []])

    # --- Form fields ---------------------------------------------------------

    def test_form_fields_accept_return_and_trip_type(self):
        self.planner.answers = [example("response_round_trip.json"), example("response_ok.json")]
        year = datetime.date.today().year + 1
        fields = {**ROUND, "departure": f"{year}-05-20", "return": f"{year}-05-27"}
        body = self.send(fields=fields).json()
        self.assertIsNone(body["user_message"])
        self.assertEqual(body["missing_fields"], [])
        self.assertEqual(
            body["trip_state"]["return"],
            {"value": day(f"{year}-05-27"), "provenance": "confirmed"},
        )
        self.assertEqual(self.planner.requests[0]["return"], day(f"{year}-05-27"))
        self.assertIn("Zurück:", body["reply"]["content"])

        # Switching to one-way takes the return date back and searches again.
        body = self.send(fields={"trip_type": "one_way"}).json()
        self.assertEqual(body["trip_state"]["return"], {"value": None, "provenance": "unknown"})
        self.assertEqual(
            body["trip_state"]["trip_type"], {"value": "one_way", "provenance": "confirmed"}
        )
        self.assertEqual(body["missing_fields"], [])
        self.assertEqual(len(self.planner.requests), 2)
        self.assertIsNone(self.planner.requests[1]["return"])

    def test_a_null_form_field_clears_the_value(self):
        self.planner.answers = [example("response_ok.json"), example("response_ok.json")]
        year = datetime.date.today().year + 1
        fields = {**COMPLETE, "departure": f"{year}-05-20", "budget": 300, "max_stops": 1}
        body = self.send(fields=fields).json()
        self.assertEqual(body["trip_state"]["budget"]["value"]["amount"], 300.0)

        body = self.send(fields={"budget": None}).json()
        self.assertEqual(body["trip_state"]["budget"], {"value": None, "provenance": "unknown"})
        self.assertEqual(body["trip_state"]["max_stops"], {"value": 1, "provenance": "confirmed"})
        self.assertIsNone(self.planner.requests[1]["max_price"])
        self.assertEqual(self.planner.requests[1]["max_stops"], 1)

        # A cleared required field is asked for again instead of searched without.
        body = self.send(fields={"travelers": None, "trip_type": None}).json()
        self.assertEqual(body["missing_fields"], ["return", "travelers"])
        self.assertEqual(body["reply"]["content"], texts.QUESTIONS["return"])
        self.assertIsNone(body["reply"]["result"])
        self.assertEqual(len(self.planner.requests), 2)

    def test_the_reply_step_is_told_what_the_form_changed(self):
        llm = FakeLLM(["Wohin?"])
        with patch("planning.views.get_llm_client", return_value=llm):
            self.send(fields={"origin": "Berlin", "travelers": 2})
        self.assertIn(
            "Note about that message: Der Nutzer hat im Formular geändert: "
            "Startort, Anzahl der Reisenden.",
            instruction_of(llm),
        )

    def test_invalid_return_and_trip_type_in_the_form_return_400(self):
        year = datetime.date.today().year + 1
        cases = {
            "return in the past": ({"return": "2020-01-01"}, "return"),
            "return not a date": ({"return": "bald"}, "return"),
            "unknown trip type": ({"trip_type": "both_ways"}, "trip_type"),
            "return before departure": (
                {"departure": f"{year}-05-20", "return": f"{year}-05-19"}, "return",
            ),
        }
        for name, (fields, key) in cases.items():
            with self.subTest(name):
                response = self.send(fields=fields)
                self.assertEqual(response.status_code, 400)
                error = response.json()["error"]
                self.assertEqual(error["code"], "validation_error")
                self.assertIn(key, error["fields"]["fields"])
        self.assertEqual(self.session.messages.count(), 0)
        self.session.refresh_from_db()
        self.assertEqual(self.session.trip_state, {})

    # --- GET …/trip-state/ ---------------------------------------------------

    def test_trip_state_of_a_new_session_is_empty_and_complete_in_shape(self):
        response = self.client.get(self.state_url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {"trip_state", "missing_fields"})
        self.assertEqual(
            body["trip_state"],
            {
                name: {"value": None, "provenance": "unknown"}
                for name in (
                    "origin", "destination", "departure", "return",
                    "travelers", "budget", "max_stops", "trip_type",
                )
            },
        )
        self.assertEqual(
            body["missing_fields"], ["origin", "destination", "departure", "return", "travelers"]
        )

    def test_trip_state_shows_what_the_chat_stored(self):
        year = datetime.date.today().year + 1
        posted = self.send(
            text=f"am 20.05.{year} von Berlin nach Lissabon, zurück am 27.05.{year}"
        ).json()
        response = self.client.get(self.state_url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body, {
            "trip_state": posted["trip_state"], "missing_fields": posted["missing_fields"],
        })
        self.assertEqual(body["missing_fields"], ["travelers"])
        self.assertEqual(
            body["trip_state"]["return"],
            {"value": day(f"{year}-05-27"), "provenance": "confirmed"},
        )
        self.assertEqual(body["trip_state"]["origin"], {"value": "Berlin", "provenance": "confirmed"})

    def test_trip_state_of_a_one_way_trip_does_not_miss_the_return(self):
        self.send(fields={"trip_type": "one_way", "origin": "Berlin"})
        body = self.client.get(self.state_url).json()
        self.assertEqual(body["missing_fields"], ["destination", "departure", "travelers"])
        self.assertEqual(
            body["trip_state"]["trip_type"], {"value": "one_way", "provenance": "confirmed"}
        )

    def test_trip_state_is_read_only_and_per_session(self):
        self.send(fields={"origin": "Berlin"})
        other = PlanningSession.objects.create(title="Other")
        body = self.client.get(f"/api/v1/planning-sessions/{other.id}/trip-state/").json()
        self.assertIsNone(body["trip_state"]["origin"]["value"])
        before = self.session.messages.count()
        self.client.get(self.state_url)
        self.assertEqual(self.session.messages.count(), before)
        self.assertEqual(self.client.post(self.state_url, {}, format="json").status_code, 405)

    def test_trip_state_of_an_unknown_session_returns_404(self):
        url = "/api/v1/planning-sessions/00000000-0000-0000-0000-000000000000/trip-state/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")


class LatestStatementWinsTests(SimpleTestCase):
    """What the user says last wins; nothing the LLM read is dropped silently."""

    def test_a_destination_equal_to_the_known_origin_moves_the_place(self):
        # The original bug: origin=Berlin, the LLM returns destination="Berlin".
        state = TripState()
        state.apply({"origin": "Berlin"}, today=TODAY)
        reading = read(state, "ich will nach Berlin", llm=FakeLLM([extraction(destination="Berlin")]))
        self.assertEqual(state.value("destination"), "Berlin")
        self.assertEqual(state.provenance("destination"), CONFIRMED)
        self.assertIsNone(state.value("origin"))
        self.assertEqual(state.provenance("origin"), UNKNOWN)
        self.assertEqual(reading.changes, {"destination": "Berlin"})
        self.assertEqual(reading.rejected, {})
        self.assertEqual(reading.dropped, [])
        self.assertEqual(reading.note, "Die bisherige Angabe " + REOPENED.format(label="Startort"))

    def test_after_a_moved_place_the_agent_asks_for_the_origin(self):
        state = TripState()
        state.apply({"origin": "Berlin"}, today=TODAY)
        llm = FakeLLM([extraction(destination="Berlin"), "Und von wo startest du?"])
        result = turn(state, "ich will nach Berlin", llm=llm)
        self.assertEqual(result.reply, "Und von wo startest du?")
        self.assertIsNone(result.result)
        self.assertEqual(result.rejected, {})
        self.assertEqual(result.reading.dropped, [])
        self.assertEqual(state.missing_required_fields()[0], "origin")
        self.assertIn("Ask for the city the trip starts in.", instruction_of(llm))
        self.assertIn(REOPENED.format(label="Startort"), instruction_of(llm))
        self.assertEqual(llm.calls[1]["fallback"], texts.QUESTIONS["origin"])

    def test_the_offline_stand_in_moves_the_place_too(self):
        state, llm = TripState(), offline()
        turn(state, "Hallo", llm=llm)
        turn(state, "Berlin", llm=llm)
        self.assertEqual(state.value("origin"), "Berlin")
        result = turn(state, "Nein, ich will nach Berlin", llm=llm)
        self.assertEqual(state.value("destination"), "Berlin")
        self.assertIsNone(state.value("origin"))
        self.assertEqual(result.reply, texts.QUESTIONS["origin"])
        self.assertEqual(result.reading.dropped, [])

    def test_an_origin_equal_to_the_known_destination_moves_the_place(self):
        state = round_state()
        llm = FakeLLM([extraction(origin="Lissabon"), "Wohin dann?"])
        result = turn(state, "ich starte in Lissabon", llm=llm, searched_before=True)
        self.assertEqual(state.value("origin"), "Lissabon")
        self.assertIsNone(state.value("destination"))
        self.assertIsNone(result.result)
        self.assertEqual(result.rejected, {})
        self.assertIn("Ask for the destination city.", instruction_of(llm))
        self.assertIn(REOPENED.format(label="Ziel"), instruction_of(llm))

    def test_an_assumed_place_never_clears_the_other_one(self):
        state = TripState()
        state.apply({"origin": "Berlin"}, today=TODAY)
        llm = FakeLLM([extraction(destination="Berlin", inferred=["destination"]), "Wohin?"])
        result = turn(state, "irgendwas mit Berlin", llm=llm)
        self.assertEqual(state.value("origin"), "Berlin")
        self.assertIsNone(state.value("destination"))
        self.assertEqual(list(result.rejected), ["destination"])
        self.assertEqual(result.reading.dropped, [])
        self.assertIn("must be different", instruction_of(llm))
        self.assertNotIn("passt nicht mehr", instruction_of(llm))
        self.assertIn("konnte ich nicht übernehmen: Ziel", llm.calls[1]["fallback"])

    def test_origin_and_destination_are_swapped_in_one_message(self):
        planner = StubPlanner(example("response_ok.json"))
        state = complete_state()
        llm = FakeLLM([extraction(origin="Lissabon", destination="Berlin"), "Andersherum:"])
        result = turn(state, "andersrum bitte", llm=llm, planner=planner, searched_before=True)
        self.assertEqual(state.value("origin"), "Lissabon")
        self.assertEqual(state.value("destination"), "Berlin")
        self.assertEqual(result.rejected, {})
        self.assertNotIn("passt nicht mehr", instruction_of(llm))
        self.assertEqual(planner.requests[0]["origin"], "Lissabon")
        self.assertEqual(planner.requests[0]["destination"], "Berlin")

    def test_all_values_of_one_message_are_checked_against_each_other(self):
        # A new departure and a new return in one message: the return is
        # compared with the new departure, not with the outdated one.
        state = round_state()
        llm = FakeLLM([
            extraction(
                departure_earliest="2027-06-10", departure_latest="2027-06-10",
                return_earliest="2027-06-17", return_latest="2027-06-17",
            ),
            "Neu gesucht:",
        ])
        planner = StubPlanner(example("response_round_trip.json"))
        result = turn(state, "lieber 10. bis 17. Juni", llm=llm, planner=planner, searched_before=True)
        self.assertEqual(result.rejected, {})
        self.assertEqual(state.value("departure"), day("2027-06-10"))
        self.assertEqual(state.value("return"), day("2027-06-17"))
        self.assertEqual(planner.requests[0]["return"], day("2027-06-17"))
        self.assertEqual(len(llm.calls), 2)

    def test_lenient_values_from_the_llm_are_taken_over(self):
        llm = FakeLLM([
            extraction(
                departure_earliest="2027-05-24T00:00:00", departure_latest="2027-05-20T00:00:00",
                return_latest="2027-05-27", travelers=2.0, max_stops=1.0,
            ),
            "Von wo?",
        ])
        state = TripState()
        result = turn(state, "…", llm=llm)
        self.assertEqual(result.rejected, {})
        self.assertEqual(
            state.value("departure"), {"earliest": "2027-05-20", "latest": "2027-05-24"}
        )
        self.assertEqual(state.value("return"), day("2027-05-27"))
        self.assertEqual(state.value("travelers"), 2)
        self.assertEqual(state.value("max_stops"), 1)

    def test_a_window_that_began_in_the_past_starts_today(self):
        llm = FakeLLM([
            extraction(departure_earliest="2026-11-09", departure_latest="2026-11-22"),
            "Von wo?",
        ])
        state = TripState()
        result = turn(state, "diese oder nächste Woche", llm=llm)
        self.assertEqual(result.rejected, {})
        self.assertEqual(
            state.value("departure"), {"earliest": "2026-11-15", "latest": "2026-11-22"}
        )

    def test_values_of_the_wrong_type_are_rejected_with_a_reason_not_dropped(self):
        llm = FakeLLM([
            extraction(
                origin=5, travelers="2", budget_amount="300", departure_earliest="morgen",
                return_earliest="2020-01-01",
            ),
            "Von wo?",
        ])
        state = TripState()
        result = turn(state, "…", llm=llm)
        self.assertEqual(
            set(result.rejected), {"origin", "travelers", "budget", "departure", "return"}
        )
        self.assertTrue(all(result.rejected.values()))
        self.assertEqual(result.reading.dropped, [])
        self.assertEqual(state.to_dict(), TripState().to_dict())

    def test_one_way_with_an_impossible_return_date_drops_nothing(self):
        # "one way" and a return date that lies before the departure in one
        # message: whatever becomes of the two, the reading accounts for both.
        state = TripState()
        state.apply({**ROUND, "return": None}, today=TODAY)
        llm = FakeLLM([
            extraction(one_way=True, return_earliest="2027-05-10", return_latest="2027-05-10")
        ])
        with patch("llm.base.logger"):
            reading = _read_message(
                state, "nur hin, zurück am 10. Mai", history=[], llm=llm, today=TODAY
            )
        self.assertEqual(list(reading.rejected), ["return"])
        self.assertEqual(reading.dropped, [])


class ClearedTests(SimpleTestCase):
    """The user takes a value back without giving a new one."""

    def test_a_cleared_budget_becomes_unknown_and_the_agent_searches_again(self):
        planner = StubPlanner(example("response_ok.json"))
        state = complete_state(budget=300)
        llm = FakeLLM([extraction(cleared=["budget"]), "Ohne Limit:"])
        result = turn(state, "Budget ist egal", llm=llm, planner=planner, searched_before=True)
        self.assertIsNone(state.value("budget"))
        self.assertEqual(state.provenance("budget"), UNKNOWN)
        self.assertEqual(result.reading.changes, {"budget": None})
        self.assertEqual(result.reading.dropped, [])
        self.assertEqual(result.rejected, {})
        self.assertEqual(result.result["status"], "ok")
        self.assertIsNone(planner.requests[0]["max_price"])

    def test_cleared_is_ignored_for_a_field_the_same_message_sets(self):
        state = complete_state(budget=300, max_stops=0)
        llm = FakeLLM([
            extraction(budget_amount=200, cleared=["budget", "max_stops"]), "Okay:",
        ])
        result = turn(state, "200 reichen, Umstiege egal", llm=llm,
                      planner=StubPlanner(example("response_ok.json")))
        self.assertEqual(
            state.value("budget"), {"amount": 200.0, "currency": "EUR", "basis": "per_person"}
        )
        self.assertIsNone(state.value("max_stops"))
        self.assertEqual(
            result.reading.changes,
            {"budget": {"amount": 200, "currency": "EUR", "basis": "per_person"}, "max_stops": None},
        )

    def test_cleared_does_not_hide_an_invalid_new_value(self):
        state = complete_state()
        llm = FakeLLM([extraction(travelers=0, cleared=["travelers"]), "…"])
        result = turn(state, "…", llm=llm, planner=StubPlanner(example("response_ok.json")))
        self.assertEqual(list(result.rejected), ["travelers"])
        self.assertEqual(state.value("travelers"), 2)

    def test_a_cleared_required_field_is_asked_for_again(self):
        for name in ("origin", "destination", "departure", "return", "travelers"):
            with self.subTest(name):
                planner = StubPlanner()
                state = round_state()
                llm = FakeLLM([extraction(cleared=[name]), "Wie dann?"])
                result = turn(state, "vergiss das", llm=llm, planner=planner, searched_before=True)
                self.assertEqual(state.missing_required_fields(), [name])
                self.assertIsNone(result.result)
                self.assertEqual(planner.requests, [])
                self.assertEqual(result.reading.changes, {name: None})
                self.assertEqual(llm.calls[1]["fallback"], texts.QUESTIONS[name])
                # The user took it back knowingly: no "no longer fits" remark.
                self.assertNotIn("passt nicht mehr", instruction_of(llm))

    def test_cleared_ignores_names_that_cannot_be_cleared(self):
        for cleared in (["trip_type", "hotel", "intent", 3, None], "budget", None, {"budget": True}):
            with self.subTest(cleared=cleared):
                state = complete_state(budget=300)
                before = state.to_dict()
                reading = read(state, "…", llm=FakeLLM([extraction(cleared=cleared)]))
                self.assertEqual(reading.changes, {})
                self.assertEqual(state.to_dict(), before)

    def test_clearing_an_unknown_field_changes_nothing(self):
        planner = StubPlanner()
        state = complete_state()
        llm = FakeLLM([extraction(cleared=["budget"], intent="other"), "Alles klar."])
        result = turn(state, "Budget egal", llm=llm, planner=planner, searched_before=True)
        self.assertIsNone(result.result)
        self.assertEqual(planner.requests, [])
        self.assertEqual(result.reading.dropped, [])


class RoundTripConversationTests(SimpleTestCase):
    """Return flight and trip type in the conversation."""

    SENTENCE = (
        "Ich will am 20. Mai zu zweit von Berlin nach Lissabon und zurück am 27. Mai, "
        "maximal 400 € pro Person"
    )

    def test_search_request_of_a_round_trip_has_the_return_window(self):
        self.assertEqual(
            build_search_request(round_state(budget=400)), example("request_round_trip.json")
        )

    def test_search_request_of_a_one_way_trip_has_return_null(self):
        request = build_search_request(complete_state(budget=300))
        self.assertEqual(request, example("request.json"))
        self.assertIn("return", request)
        self.assertIsNone(request["return"])

    def test_no_search_request_without_the_return_of_a_round_trip(self):
        state = TripState()
        state.apply({**ROUND, "return": None}, today=TODAY)
        with self.assertRaises(AssertionError):
            build_search_request(state)

    def test_one_sentence_with_everything_searches_a_round_trip(self):
        planner = StubPlanner(example("response_round_trip.json"))
        state = TripState()
        result = turn(state, self.SENTENCE, llm=offline(), planner=planner)
        self.assertEqual(planner.requests, [example("request_round_trip.json")])
        self.assertEqual(state.value("return"), day("2027-05-27"))
        self.assertEqual(state.provenance("return"), CONFIRMED)
        self.assertEqual(result.reading.dropped, [])
        self.assertEqual(result.result["status"], "ok")
        self.assertEqual(result.result["journeys"], example("response_round_trip.json")["journeys"])
        intro, _, listing = result.reply.partition("\n")
        self.assertEqual(
            intro,
            "Ich habe alles, was ich brauche: Berlin nach Lissabon am 20.05.2027, zurück am "
            "27.05.2027, für 2 Personen, höchstens 400,00 € pro Person. "
            "Dafür habe ich 5 Verbindungen gefunden:",
        )
        self.assertEqual(len(listing.split("\n")), 5 * 3 + 2)  # two outbound flights with a warning
        self.assertIn("   Hin: 98,00 € pro Person", listing)
        self.assertIn("   Zurück: 102,67 € pro Person", listing)

    def test_the_reply_step_learns_that_the_search_was_a_round_trip(self):
        llm = FakeLLM(["Hier sind Hin- und Rückflüge:"])
        result = turn(round_state(), "", llm=llm, planner=StubPlanner(example("response_round_trip.json")))
        instruction = instruction_of(llm)
        self.assertIn('"return": {"earliest": "2027-05-27", "latest": "2027-05-27"}', instruction)
        self.assertIn('"connections_found": 5', instruction)
        # Prices never pass through the LLM, also not the total price.
        self.assertNotIn("200", instruction)
        intro, _, listing = result.reply.partition("\n")
        self.assertEqual(intro, "Hier sind Hin- und Rückflüge:")
        self.assertIn("200,67 € pro Person für Hin- und Rückflug", listing)

    def test_a_single_return_date_from_the_llm_is_a_fixed_day(self):
        for values in ({"return_earliest": "2027-05-27"}, {"return_latest": "2027-05-27"}):
            with self.subTest(values=values):
                state = TripState()
                reading = read(state, "zurück am 27.", llm=FakeLLM([extraction(**values)]))
                self.assertEqual(state.value("return"), day("2027-05-27"))
                self.assertEqual(reading.changes, {"return": day("2027-05-27")})

    def test_a_return_before_the_departure_is_rejected_with_the_reason(self):
        state = TripState()
        state.apply({**ROUND, "return": None}, today=TODAY)
        llm = FakeLLM([
            extraction(return_earliest="2027-05-10", return_latest="2027-05-10"),
            "Der Rückflug liegt vor dem Hinflug. Wann willst du zurück?",
        ])
        result = turn(state, "zurück am 10. Mai", llm=llm)
        self.assertEqual(list(result.rejected), ["return"])
        self.assertIsNone(state.value("return"))
        self.assertIsNone(result.result)
        self.assertEqual(result.reading.dropped, [])
        instruction = instruction_of(llm)
        self.assertIn("Values that could not be used", instruction)
        self.assertIn("must not be before the departure", instruction)
        self.assertIn("Ask for the date or period of the return flight", instruction)
        self.assertEqual(
            llm.calls[1]["fallback"],
            "Diese Angabe konnte ich nicht übernehmen: Rückflug. " + texts.QUESTIONS["return"],
        )

    def test_a_new_return_before_the_departure_keeps_the_known_return(self):
        state = round_state()
        llm = FakeLLM([extraction(return_earliest="2027-05-10"), "…"])
        result = turn(state, "zurück am 10. Mai", llm=llm,
                      planner=StubPlanner(example("response_round_trip.json")))
        self.assertEqual(list(result.rejected), ["return"])
        self.assertEqual(state.value("return"), day("2027-05-27"))
        self.assertIn("konnte ich nicht übernehmen: Rückflug", llm.calls[1]["fallback"])

    def test_a_new_departure_after_the_return_reopens_the_return(self):
        planner = StubPlanner()
        state = round_state()
        llm = FakeLLM([
            extraction(departure_earliest="2027-06-10", departure_latest="2027-06-10"),
            "Und wann zurück?",
        ])
        result = turn(state, "doch erst am 10. Juni", llm=llm, planner=planner, searched_before=True)
        self.assertEqual(state.value("departure"), day("2027-06-10"))
        self.assertIsNone(state.value("return"))
        self.assertEqual(state.missing_required_fields(), ["return"])
        self.assertEqual(result.rejected, {})
        self.assertEqual(result.reading.changes, {"departure": day("2027-06-10")})
        self.assertEqual(result.reading.dropped, [])
        self.assertIsNone(result.result)
        self.assertEqual(planner.requests, [])
        instruction = instruction_of(llm)
        self.assertIn(
            "Note about that message: Die bisherige Angabe " + REOPENED.format(label="Rückflug"),
            instruction,
        )
        self.assertIn("Ask for the date or period of the return flight", instruction)
        self.assertEqual(llm.calls[1]["fallback"], texts.QUESTIONS["return"])

    def test_the_reopened_remark_is_added_to_the_note_of_the_llm(self):
        state = round_state()
        llm = FakeLLM([
            extraction(departure_earliest="2027-06-10", note="Der Nutzer verschiebt die Reise."),
        ])
        reading = read(state, "doch erst am 10. Juni", llm=llm)
        self.assertEqual(
            reading.note,
            "Der Nutzer verschiebt die Reise. Die bisherige Angabe "
            + REOPENED.format(label="Rückflug"),
        )

    def test_one_way_takes_the_return_back_and_searches_without_it(self):
        planner = StubPlanner(example("response_ok.json"))
        state = round_state()
        llm = FakeLLM([extraction(one_way=True), "Nur der Hinflug:"])
        result = turn(state, "ich brauche nur den Hinflug", llm=llm, planner=planner, searched_before=True)
        self.assertEqual(state.value("trip_type"), ONE_WAY)
        self.assertEqual(state.provenance("trip_type"), CONFIRMED)
        self.assertIsNone(state.value("return"))
        self.assertEqual(result.reading.changes, {"trip_type": ONE_WAY})
        self.assertEqual(result.reading.dropped, [])
        self.assertEqual(result.result["status"], "ok")
        self.assertIsNone(planner.requests[0]["return"])
        # The return is not "open again": a one-way trip has none.
        self.assertNotIn("passt nicht mehr", instruction_of(llm))
        self.assertNotIn("zurück", llm.calls[1]["fallback"])

    def test_one_way_answers_the_question_for_the_return(self):
        planner = StubPlanner(example("response_ok.json"))
        state = TripState()
        state.apply({**ROUND, "return": None}, today=TODAY)
        result = turn(state, "ohne Rückflug", llm=offline(), planner=planner)
        self.assertTrue(state.is_one_way())
        self.assertEqual(result.result["status"], "ok")
        self.assertEqual(planner.requests, [{**example("request.json"), "max_price": None}])

    def test_a_return_date_makes_a_one_way_trip_a_round_trip(self):
        planner = StubPlanner(example("response_round_trip.json"))
        state = complete_state()
        llm = FakeLLM([
            extraction(return_earliest="2027-05-27", return_latest="2027-05-27"), "Mit Rückflug:",
        ])
        result = turn(state, "doch zurück am 27. Mai", llm=llm, planner=planner, searched_before=True)
        self.assertEqual(state.value("trip_type"), ROUND_TRIP)
        self.assertEqual(state.value("return"), day("2027-05-27"))
        self.assertEqual(result.reading.dropped, [])
        self.assertEqual(planner.requests, [{**example("request_round_trip.json"), "max_price": None}])

    def test_wanting_a_return_flight_after_one_way_asks_for_its_date(self):
        planner = StubPlanner()
        state = complete_state()
        llm = FakeLLM([extraction(one_way=False), "Wann zurück?"])
        result = turn(state, "doch mit Rückflug", llm=llm, planner=planner, searched_before=True)
        self.assertEqual(state.value("trip_type"), ROUND_TRIP)
        self.assertEqual(state.missing_required_fields(), ["return"])
        self.assertIsNone(result.result)
        self.assertEqual(planner.requests, [])
        self.assertEqual(llm.calls[1]["fallback"], texts.QUESTIONS["return"])

    def test_a_return_date_wins_over_one_way_in_the_same_message(self):
        state = TripState()
        llm = FakeLLM([extraction(one_way=True, return_earliest="2027-05-27")])
        reading = read(state, "one way, zurück am 27. Mai", llm=llm)
        self.assertEqual(state.value("return"), day("2027-05-27"))
        self.assertEqual(state.value("trip_type"), ROUND_TRIP)
        self.assertEqual(reading.rejected, {})
        self.assertEqual(reading.dropped, [])

    def test_one_way_is_only_read_from_a_boolean(self):
        for value in ("yes", 1, "true", None):
            with self.subTest(value=value):
                state = TripState()
                reading = read(state, "…", llm=FakeLLM([extraction(one_way=value)]))
                self.assertEqual(reading.changes, {})
                self.assertIsNone(state.value("trip_type"))

    def test_an_assumed_return_is_confirmed_before_searching(self):
        planner = StubPlanner(example("response_round_trip.json"))
        state = TripState()
        state.apply({**ROUND, "return": None}, today=TODAY)
        llm = FakeLLM([
            extraction(
                return_earliest="2027-05-27", return_latest="2027-05-27", inferred=["return"],
            ),
            "Also zurück am 27.05.2027?",
        ])
        result = turn(state, "für eine Woche", llm=llm, planner=planner)
        self.assertEqual(state.provenance("return"), INFERRED)
        self.assertIsNone(result.result)
        self.assertEqual(planner.requests, [])
        instruction = instruction_of(llm)
        self.assertIn("Do not search yet", instruction)
        self.assertIn('"assumed": {"return": {"earliest": "2027-05-27"', instruction)
        self.assertEqual(
            llm.calls[1]["fallback"],
            "Ich habe das so verstanden: Rückflug am 27.05.2027. "
            "Passt das, oder möchtest du es genauer angeben?",
        )

        # "ja" confirms it and starts the search.
        result = turn(state, "ja", llm=offline(), planner=planner)
        self.assertEqual(state.provenance("return"), CONFIRMED)
        self.assertEqual(result.result["status"], "ok")
        self.assertEqual(planner.requests, [{**example("request_round_trip.json"), "max_price": None}])

    def test_the_llm_is_told_which_values_await_confirmation(self):
        state = round_state()
        state.apply({"return": "2027-05-27"}, inferred={"return"}, today=TODAY)
        llm = FakeLLM([extraction(intent="other"), "Passt der 27.?"])
        turn(state, "hä?", llm=llm)
        self.assertIn("Asked field: confirmation", llm.calls[0]["system"])
        self.assertIn("Awaiting confirmation: return", llm.calls[0]["system"])


class SearchAgainTests(SimpleTestCase):
    """Step 3: when a message after a search leads to a new search."""

    def test_trip_data_without_a_change_searches_again(self):
        planner = StubPlanner(example("response_ok.json"))
        state = complete_state()
        before = state.to_dict()
        llm = FakeLLM([extraction(origin="Berlin", intent="trip_info"), "Nochmal gesucht:"])
        result = turn(state, "von Berlin, such nochmal", llm=llm, planner=planner, searched_before=True)
        self.assertEqual(state.to_dict(), before)
        self.assertEqual(result.result["status"], "ok")
        self.assertEqual(len(planner.requests), 1)
        self.assertNotIn("there is no new search", instruction_of(llm))

    def test_other_messages_without_a_change_do_not_search_again(self):
        for intent in ("question", "smalltalk", "other", "dancing", None):
            with self.subTest(intent=intent):
                planner = StubPlanner()
                llm = FakeLLM([extraction(intent=intent), "Gern!"])
                result = turn(
                    complete_state(), "danke", llm=llm, planner=planner, searched_before=True
                )
                self.assertIsNone(result.result)
                self.assertEqual(planner.requests, [])
                self.assertIn("there is no new search", instruction_of(llm))
                self.assertIn('"current_search"', instruction_of(llm))

    def test_the_summary_of_the_standing_search_names_the_return(self):
        llm = FakeLLM([extraction(intent="smalltalk"), "Gern!"])
        turn(round_state(), "danke", llm=llm, searched_before=True)
        self.assertEqual(
            llm.calls[1]["fallback"],
            "Deine Suche steht weiterhin: Berlin nach Lissabon am 20.05.2027, zurück am "
            "27.05.2027, für 2 Personen. Sag mir einfach, was ich ändern soll, zum Beispiel "
            "Datum, Budget oder Umstiege.",
        )

    def test_a_question_that_changes_something_searches(self):
        planner = StubPlanner(example("response_ok.json"))
        llm = FakeLLM([extraction(budget_amount=150, intent="question"), "Mit 150 €:"])
        result = turn(
            complete_state(), "und bis 150?", llm=llm, planner=planner, searched_before=True
        )
        self.assertEqual(result.result["status"], "ok")
        self.assertEqual(planner.requests[0]["max_price"]["amount"], 150.0)

    def test_without_an_earlier_search_every_complete_state_searches(self):
        planner = StubPlanner(example("response_ok.json"))
        llm = FakeLLM([extraction(intent="smalltalk"), "Los:"])
        result = turn(complete_state(), "hi", llm=llm, planner=planner, searched_before=False)
        self.assertEqual(result.result["status"], "ok")


class FormTurnTests(SimpleTestCase):
    """Turns without text: the user changed values in the form."""

    def test_the_reply_step_is_told_which_fields_the_form_changed(self):
        state = TripState()
        previous = state.to_dict()
        state.apply({"origin": "Berlin", "travelers": 2, "budget": 300}, today=TODAY)
        llm = FakeLLM(["Wohin?"])
        result = turn(state, "", llm=llm, previous_state=previous)
        self.assertIsNone(result.reading)
        self.assertEqual(len(llm.calls), 1)
        instruction = instruction_of(llm)
        self.assertIn('Latest user message: ""', instruction)
        self.assertIn(
            "Note about that message: Der Nutzer hat im Formular geändert: "
            "Startort, Anzahl der Reisenden, Budget.",
            instruction,
        )
        self.assertIn("Ask for the destination city.", instruction)

    def test_the_note_names_fields_that_changed_as_a_consequence(self):
        state = round_state()
        previous = state.to_dict()
        state.apply({"trip_type": "one_way"}, today=TODAY)
        llm = FakeLLM(["Nur hin:"])
        result = turn(state, "", llm=llm, previous_state=previous, searched_before=True,
                      planner=StubPlanner(example("response_ok.json")))
        self.assertIn(
            "Der Nutzer hat im Formular geändert: Rückflug, Reiseart.", instruction_of(llm)
        )
        # A changed form searches again.
        self.assertEqual(result.result["status"], "ok")

    def test_no_note_when_the_form_changed_nothing(self):
        state = TripState()
        state.apply({"origin": "Berlin"}, today=TODAY)
        for previous in (state.to_dict(), None):
            with self.subTest(previous=previous is not None):
                llm = FakeLLM(["Wohin?"])
                turn(state, "", llm=llm, previous_state=previous)
                self.assertNotIn("Formular", instruction_of(llm))
                self.assertNotIn("Note about that message", instruction_of(llm))

    def test_form_and_text_together_mention_both(self):
        # Form values sent with a message are confirmed in the reply, not ignored.
        state = TripState()
        previous = state.to_dict()
        state.apply({"origin": "Berlin"}, today=TODAY)
        llm = FakeLLM([extraction(note="Der Nutzer grüßt."), "Wohin?"])
        turn(state, "hallo", llm=llm, previous_state=previous)
        instruction = instruction_of(llm)
        self.assertIn(
            "Note about that message: Der Nutzer hat im Formular geändert: Startort. "
            "Bestätige das kurz und frage nicht danach. Der Nutzer grüßt.",
            instruction,
        )
        self.assertIn("Ask for the destination city.", instruction)

    def test_form_values_count_as_a_change_for_the_search(self):
        # The form set a budget, the text is only a thank-you: search again.
        planner = StubPlanner(example("response_ok.json"))
        state = complete_state()
        previous = state.to_dict()
        state.apply({"budget": 300}, today=TODAY)
        llm = FakeLLM([extraction(intent="smalltalk"), "Mit Budget:"])
        result = turn(state, "danke", llm=llm, planner=planner, previous_state=previous,
                      searched_before=True)
        self.assertEqual(result.result["status"], "ok")
        self.assertEqual(planner.requests, [example("request.json")])


class TextsTests(SimpleTestCase):
    """The German wording the code builds from the data."""

    def setUp(self):
        self.one_way = example("response_ok.json")["journeys"]
        self.round = example("response_round_trip.json")["journeys"]

    def test_every_field_has_a_label_and_every_required_field_a_question(self):
        self.assertEqual(set(texts.FIELD_LABELS), set(TripState().to_dict()))
        required = {"origin", "destination", "departure", "return", "travelers"}
        self.assertEqual(set(texts.QUESTIONS), required)
        self.assertEqual(set(texts.FIELD_LABELS_EN), required)
        self.assertEqual(texts.rejected(["return", "trip_type"]),
                         "Diese Angabe konnte ich nicht übernehmen: Rückflug, Reiseart. ")

    def test_summary_names_the_return_only_for_a_round_trip(self):
        self.assertEqual(
            texts.summary(example("request.json")),
            "Berlin nach Lissabon am 20.05.2027 für 2 Personen, höchstens 300,00 € pro Person",
        )
        self.assertEqual(
            texts.summary(example("request_round_trip.json")),
            "Berlin nach Lissabon am 20.05.2027, zurück am 27.05.2027, für 2 Personen, "
            "höchstens 400,00 € pro Person",
        )
        request = {
            **example("request_round_trip.json"),
            "return": {"earliest": "2027-05-27", "latest": "2027-05-30"},
            "max_price": None,
            "max_stops": 0,
        }
        self.assertEqual(
            texts.summary(request),
            "Berlin nach Lissabon am 20.05.2027, zurück zwischen 27.05.2027 und 30.05.2027, "
            "für 2 Personen, nur direkt",
        )

    def test_one_way_lines_are_one_line_per_connection(self):
        review = optimizer.review(self.one_way)
        lines = texts.journey_list(self.one_way, review).split("\n")
        self.assertEqual(
            lines[0],
            "1. 98,00 € pro Person · 8 h 20 min · 2 Umstiege (Zürich, Madrid) · "
            "ab 20.05.2027 06:00 Uhr · günstigste, Empfehlung",
        )
        self.assertEqual(
            lines[1:3],
            [
                "2. 119,00 € pro Person · 4 h 40 min · 1 Umstieg (Frankfurt) · "
                "ab 20.05.2027 07:05 Uhr",
                "   Achtung: Nur 25 Minuten zum Umsteigen in Frankfurt.",
            ],
        )
        self.assertEqual(
            lines[-1],
            "5. 189,00 € pro Person · 3 h 55 min · direkt · ab 20.05.2027 06:40 Uhr · schnellste",
        )
        self.assertEqual(len(lines), 6)
        self.assertNotIn("Hin", "\n".join(lines))

    def test_one_way_lines_do_not_need_the_new_keys(self):
        # Answers in the older shape, without `inbound` and `total_price`.
        old = copy.deepcopy(self.one_way)
        for journey in old:
            del journey["inbound"], journey["total_price"]
        self.assertEqual(
            texts.journey_list(old, optimizer.review(old)),
            texts.journey_list(self.one_way, optimizer.review(self.one_way)),
        )

    def test_round_trip_lines_show_the_total_and_both_flights(self):
        review = optimizer.review(self.round)
        lines = texts.journey_list(self.round, review).split("\n")
        self.assertEqual(
            lines[:3],
            [
                "1. 200,67 € pro Person für Hin- und Rückflug · günstigste, Empfehlung",
                "   Hin: 98,00 € pro Person · 8 h 20 min · 2 Umstiege (Zürich, Madrid) · "
                "ab 20.05.2027 06:00 Uhr",
                "   Zurück: 102,67 € pro Person · 8 h 50 min · 2 Umstiege (Paris, Frankfurt) · "
                "ab 27.05.2027 05:45 Uhr",
            ],
        )
        # The warning comes after both flights.
        self.assertEqual(
            lines[3:7],
            [
                "2. 221,67 € pro Person für Hin- und Rückflug",
                "   Hin: 119,00 € pro Person · 4 h 40 min · 1 Umstieg (Frankfurt) · "
                "ab 20.05.2027 07:05 Uhr",
                "   Zurück: 102,67 € pro Person · 8 h 50 min · 2 Umstiege (Paris, Frankfurt) · "
                "ab 27.05.2027 05:45 Uhr",
                "   Achtung: Nur 25 Minuten zum Umsteigen in Frankfurt.",
            ],
        )
        self.assertEqual(sum(line.startswith("   Hin: ") for line in lines), 5)
        self.assertEqual(sum(line.startswith("   Zurück: ") for line in lines), 5)
        self.assertEqual(
            [line for line in lines if line[0].isdigit()][3],
            "4. 256,90 € pro Person für Hin- und Rückflug · schnellste",
        )

    def test_a_round_trip_line_without_review(self):
        self.assertEqual(
            texts.journey_line(7, self.round[4], {}),
            "7. 316,65 € pro Person für Hin- und Rückflug\n"
            "   Hin: 142,50 € pro Person · 5 h 55 min · 1 Umstieg (Madrid) · ab 20.05.2027 10:15 Uhr\n"
            "   Zurück: 174,15 € pro Person · 6 h 20 min · 1 Umstieg (Paris) · ab 27.05.2027 14:25 Uhr",
        )

    def test_total_price_is_the_price_of_both_flights(self):
        self.assertEqual(texts.total_price(self.round[0])["amount"], 200.67)
        self.assertEqual(texts.total_price(self.one_way[0])["amount"], 98.0)
        without = {key: value for key, value in self.one_way[0].items() if key != "total_price"}
        self.assertEqual(texts.total_price(without)["amount"], 98.0)
        self.assertIsNone(texts.total_price({**without, "price": None}))

    def test_no_results_names_the_flight_that_is_the_problem(self):
        request = example("request_round_trip.json")
        cases = [
            ("no_connection", "outbound", "An diesen Tagen gibt es für den Hinflug keine Verbindung"),
            ("no_connection", "inbound", "An diesen Tagen gibt es für den Rückflug keine Verbindung"),
            ("no_connection", None, "An diesen Tagen gibt es keine Verbindung"),
            ("max_stops", "outbound", "Es gibt für den Hinflug keine Verbindung mit so wenigen"),
            ("max_stops", "inbound", "Es gibt für den Rückflug keine Verbindung mit so wenigen"),
            ("max_stops", None, "Es gibt keine Verbindung mit so wenigen"),
        ]
        for reason, direction, expected in cases:
            with self.subTest(reason=reason, direction=direction):
                details = {"reason": reason, "direction": direction, "closest_journey": None}
                text = texts.no_results(request, details)
                self.assertIn(expected, text)
                self.assertTrue(text.startswith(
                    "Für Berlin nach Lissabon am 20.05.2027, zurück am 27.05.2027, für 2 Personen"
                ))

    def test_no_results_works_without_a_direction(self):
        # Answers in the older shape have no `direction` at all.
        text = texts.no_results(
            example("request.json"), {"reason": "no_connection", "closest_journey": None}
        )
        self.assertIn("An diesen Tagen gibt es keine Verbindung auf dieser Strecke.", text)

    def test_the_closest_option_is_quoted_with_its_total_price(self):
        details = {"reason": "budget", "direction": None, "closest_journey": self.round[0]}
        text = texts.no_results(example("request_round_trip.json"), details)
        self.assertIn("Alle Verbindungen liegen über deinem Budget.", text)
        self.assertIn("Die günstigste kostet 200,67 € pro Person.", text)
        self.assertNotIn("98,00", text)

    def test_confirmation_names_an_assumed_return(self):
        state = round_state()
        self.assertEqual(
            texts.confirmation(state, ["departure", "return", "travelers"]),
            "Ich habe das so verstanden: Abflug am 20.05.2027, Rückflug am 27.05.2027, "
            "2 Personen. Passt das, oder möchtest du es genauer angeben?",
        )


class RoundTripSearchTests(SimpleTestCase):
    """Round trips in the Optimization Agent and in the explanation of empty results."""

    def setUp(self):
        self.journeys = example("response_round_trip.json")["journeys"]

    def test_tags_use_the_total_price_and_the_total_duration(self):
        review = optimizer.review(self.journeys)
        self.assertEqual(set(review), {journey["id"] for journey in self.journeys})
        tags = [review[journey["id"]]["tags"] for journey in self.journeys]
        self.assertEqual(tags, [["cheapest", "recommended"], [], [], ["fastest"], []])

    def test_tags_follow_the_whole_trip_not_the_outbound_flight(self):
        cheap_out, cheap_total = copy.deepcopy(self.journeys[0]), copy.deepcopy(self.journeys[4])
        # Cheap and short outbound flight, expensive and long trip.
        cheap_out["price"]["amount"], cheap_out["total_price"]["amount"] = 50.0, 300.0
        cheap_out["duration_minutes"], cheap_out["inbound"]["duration_minutes"] = 100, 900
        cheap_total["price"]["amount"], cheap_total["total_price"]["amount"] = 100.0, 200.0
        cheap_total["duration_minutes"], cheap_total["inbound"]["duration_minutes"] = 200, 300
        review = optimizer.review([cheap_out, cheap_total])
        self.assertEqual(review[cheap_out["id"]]["tags"], [])
        self.assertEqual(
            review[cheap_total["id"]]["tags"], ["cheapest", "fastest", "recommended"]
        )

    def test_warnings_of_the_return_flight_are_in_the_same_entry(self):
        review = optimizer.review(self.journeys)
        self.assertEqual(
            review[self.journeys[1]["id"]]["warnings"],
            ["Nur 25 Minuten zum Umsteigen in Frankfurt."],
        )
        broken = copy.deepcopy(self.journeys[1])  # outbound via Frankfurt, 25 minutes
        broken["inbound"]["legs"][1]["departure"] = "2027-05-27T09:35:00+02:00"
        broken["inbound"]["price"] = None
        review = optimizer.review([broken])
        self.assertEqual(list(review), [broken["id"]])
        self.assertEqual(
            review[broken["id"]]["warnings"],
            [
                "Nur 25 Minuten zum Umsteigen in Frankfurt.",
                "Rückflug: Nur 20 Minuten zum Umsteigen in Paris.",
                "Rückflug: Für diese Verbindung ist kein Preis bekannt.",
            ],
        )
        # A trip with a warning on either flight is never the recommendation.
        self.assertNotIn("recommended", review[broken["id"]]["tags"])

    def test_a_warning_on_the_return_flight_alone_is_marked_as_such(self):
        broken = copy.deepcopy(self.journeys[0])
        broken["inbound"]["legs"][0]["arrival"] = broken["inbound"]["legs"][0]["departure"]
        warnings = optimizer.review([broken])[broken["id"]]["warnings"]
        self.assertTrue(warnings)
        self.assertTrue(all(warning.startswith("Rückflug: ") for warning in warnings), warnings)
        self.assertIn("nicht plausibel", warnings[0])
        listing = texts.journey_list([broken], optimizer.review([broken]))
        self.assertIn("\n   Achtung: Rückflug: ", listing)

    def test_review_works_without_the_new_keys(self):
        old = copy.deepcopy(example("response_ok.json")["journeys"])
        for journey in old:
            del journey["inbound"], journey["total_price"]
        self.assertEqual(
            optimizer.review(old), optimizer.review(example("response_ok.json")["journeys"])
        )

    def test_flexible_dates_widen_the_return_window_too(self):
        request = example("request_round_trip.json")
        planner = StubPlanner(example("response_round_trip.json"))
        alternative = optimizer.find_alternative(
            request, {"reason": "no_connection", "direction": "inbound", "closest_journey": None},
            llm=FakeLLM(), planner=planner, today=TODAY,
        )
        self.assertEqual(
            planner.requests[0]["departure"], {"earliest": "2027-05-17", "latest": "2027-05-23"}
        )
        self.assertEqual(
            planner.requests[0]["return"], {"earliest": "2027-05-24", "latest": "2027-05-30"}
        )
        self.assertEqual(planner.requests[0]["max_price"], request["max_price"])
        self.assertEqual(alternative["strategy"], "flexible_dates")
        self.assertEqual(alternative["request"], planner.requests[0])
        self.assertEqual(
            alternative["description"],
            "Wenn du beim Datum flexibel bist, habe ich für den Abflug zwischen 17.05.2027 und "
            "23.05.2027 und den Rückflug zwischen 24.05.2027 und 30.05.2027 aber etwas gefunden:",
        )
        self.assertEqual(set(alternative["review"]), {j["id"] for j in alternative["journeys"]})
        # The request of the user is not changed.
        self.assertEqual(request, example("request_round_trip.json"))

    def test_the_widened_return_never_starts_before_the_earliest_departure(self):
        cases = [
            # Tomorrow and the day after: both windows are cut off at today.
            ("2026-11-16", "2026-11-17", "2026-11-15", {"earliest": "2026-11-15", "latest": "2026-11-20"}),
            # Out and back on the same day.
            ("2027-05-20", "2027-05-20", "2027-05-17", {"earliest": "2027-05-17", "latest": "2027-05-23"}),
        ]
        for departure, back, earliest_departure, expected in cases:
            with self.subTest(departure=departure, back=back):
                request = {
                    **example("request_round_trip.json"),
                    "departure": day(departure), "return": day(back),
                }
                planner = StubPlanner(example("response_round_trip.json"))
                optimizer.find_alternative(
                    request, {"reason": "no_connection", "closest_journey": None},
                    llm=FakeLLM(), planner=planner, today=TODAY,
                )
                relaxed = planner.requests[0]
                self.assertEqual(relaxed["departure"]["earliest"], earliest_departure)
                self.assertEqual(relaxed["return"], expected)
                self.assertGreaterEqual(relaxed["return"]["earliest"], relaxed["departure"]["earliest"])

    def test_flexible_dates_of_a_one_way_trip_keep_return_null(self):
        planner = StubPlanner(example("response_ok.json"))
        alternative = optimizer.find_alternative(
            example("request.json"), {"reason": "no_connection", "closest_journey": None},
            llm=FakeLLM(), planner=planner, today=TODAY,
        )
        self.assertIn("return", planner.requests[0])
        self.assertIsNone(planner.requests[0]["return"])
        self.assertEqual(alternative["request"], planner.requests[0])
        self.assertNotIn("Rückflug", alternative["description"])

    def test_more_stops_keeps_both_windows(self):
        request = {**example("request_round_trip.json"), "max_stops": 0}
        planner = StubPlanner(example("response_round_trip.json"))
        with patch("llm.base.logger"):
            alternative = optimizer.find_alternative(
                request, {"reason": "max_stops", "direction": "outbound", "closest_journey": None},
                llm=FakeLLM([{"strategy": "more_stops"}]), planner=planner, today=TODAY,
            )
        self.assertEqual(alternative["strategy"], "more_stops")
        self.assertEqual(alternative["request"], {**request, "max_stops": 1})
        self.assertEqual(planner.requests, [{**request, "max_stops": 1}])

    def test_a_round_trip_without_results_gets_an_alternative_with_both_flights(self):
        planner = StubPlanner(
            example("response_no_results.json"), example("response_round_trip.json")
        )
        state = round_state(budget=50)
        before = state.to_dict()
        llm = FakeLLM(["Mit anderen Tagen habe ich etwas gefunden:"])
        result = turn(state, "", llm=llm, planner=planner)
        self.assertEqual(len(planner.requests), 2)
        self.assertEqual(planner.requests[0]["return"], day("2027-05-27"))
        self.assertEqual(
            planner.requests[1]["return"], {"earliest": "2027-05-24", "latest": "2027-05-30"}
        )
        self.assertEqual(planner.requests[1]["max_price"], planner.requests[0]["max_price"])
        alternative = result.result["alternative"]
        self.assertEqual(alternative["request"], planner.requests[1])
        self.assertEqual(len(alternative["journeys"]), 5)
        self.assertEqual(result.result["status"], "no_results")
        self.assertEqual(state.to_dict(), before)
        instruction = instruction_of(llm)
        self.assertIn('"change": "flexible_dates"', instruction)
        self.assertIn('"return": {"earliest": "2027-05-24", "latest": "2027-05-30"}', instruction)
        self.assertIn('"direction": null', instruction)
        fallback = llm.calls[0]["fallback"]
        self.assertIn("zurück am 27.05.2027", fallback)
        self.assertIn("und den Rückflug zwischen 24.05.2027 und 30.05.2027", fallback)
        intro, _, listing = result.reply.partition("\n")
        self.assertEqual(intro, "Mit anderen Tagen habe ich etwas gefunden:")
        self.assertIn("   Hin: ", listing)
        self.assertIn("   Zurück: ", listing)

    @override_settings(OPTIMIZATION_AGENT_ENABLED=False)
    def test_the_explanation_says_which_flight_found_nothing(self):
        answer = {
            "status": "no_results",
            "journeys": [],
            "no_results": {"reason": "no_connection", "direction": "inbound", "closest_journey": None},
            "error": None,
        }
        llm = FakeLLM(["Für den Rückflug gibt es nichts."])
        result = turn(round_state(), "", llm=llm, planner=StubPlanner(answer))
        self.assertEqual(result.result["status"], "no_results")
        self.assertEqual(result.result["no_results"], answer["no_results"])
        instruction = instruction_of(llm)
        self.assertIn('"reason": "no_connection"', instruction)
        self.assertIn('"direction": "inbound"', instruction)
        self.assertIn('"closest_outside_criteria": null', instruction)
        self.assertIn(
            "An diesen Tagen gibt es für den Rückflug keine Verbindung", llm.calls[0]["fallback"]
        )

    @override_settings(OPTIMIZATION_AGENT_ENABLED=False)
    def test_the_closest_round_trip_is_explained_with_its_total_price(self):
        answer = {
            "status": "no_results",
            "journeys": [],
            "no_results": {
                "reason": "budget", "direction": None, "closest_journey": self.journeys[0],
            },
            "error": None,
        }
        llm = FakeLLM(["Zu teuer."])
        turn(round_state(budget=150), "", llm=llm, planner=StubPlanner(answer))
        instruction = instruction_of(llm)
        self.assertIn(
            '"closest_outside_criteria": {"price": {"amount": 200.67, "currency": "EUR", '
            '"basis": "per_person"}, "stops": 2}',
            instruction,
        )
        self.assertIn("Die günstigste kostet 200,67 € pro Person.", llm.calls[0]["fallback"])
