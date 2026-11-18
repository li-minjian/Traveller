"""Tests for the trip state: validation, conflicts, missing fields, saving and loading."""

import datetime

from django.test import SimpleTestCase, TestCase

from planning.models import PlanningSession
from planning.trip_state import (
    CONFIRMED,
    INFERRED,
    ONE_WAY,
    ROUND_TRIP,
    UNKNOWN,
    TripState,
    load_trip_state,
    save_trip_state,
)

TODAY = datetime.date(2026, 11, 15)

FIELD_NAMES = (
    "origin", "destination", "departure", "return", "travelers", "budget", "max_stops", "trip_type",
)

# A complete one-way trip: no return date needed.
COMPLETE = {
    "origin": "Berlin",
    "destination": "Lissabon",
    "departure": "2027-05-20",
    "travelers": 2,
    "trip_type": "one_way",
}
# A complete round trip; the trip type is not stated, a round trip is the default.
ROUND = {
    "origin": "Berlin",
    "destination": "Lissabon",
    "departure": "2027-05-20",
    "return": "2027-05-27",
    "travelers": 2,
}


def day(iso: str) -> dict:
    return {"earliest": iso, "latest": iso}


def state_with(changes: dict, **options) -> TripState:
    state = TripState()
    rejected = state.apply(changes, today=TODAY, **options)
    assert rejected == {}, rejected
    return state


class MissingRequiredFieldsTests(SimpleTestCase):
    def test_a_new_state_lacks_all_required_fields_in_fixed_order(self):
        state = TripState()
        self.assertEqual(
            state.missing_required_fields(),
            ["origin", "destination", "departure", "return", "travelers"],
        )
        self.assertFalse(state.is_complete())
        self.assertFalse(state.is_one_way())
        for name in FIELD_NAMES:
            self.assertIsNone(state.value(name))
            self.assertEqual(state.provenance(name), UNKNOWN)

    def test_one_missing_field(self):
        state = TripState()
        state.apply({**COMPLETE, "departure": None}, today=TODAY)
        self.assertEqual(state.missing_required_fields(), ["departure"])

    def test_optional_fields_are_never_missing(self):
        state = TripState()
        self.assertEqual(state.apply(ROUND, today=TODAY), {})
        self.assertEqual(state.missing_required_fields(), [])
        self.assertTrue(state.is_complete())
        for name in ("budget", "max_stops", "trip_type"):
            self.assertIsNone(state.value(name))

    def test_a_round_trip_needs_a_return_date(self):
        state = state_with({**ROUND, "return": None})
        self.assertEqual(state.missing_required_fields(), ["return"])
        self.assertFalse(state.is_complete())
        # Saying "round trip" explicitly does not change that.
        state.apply({"trip_type": "round_trip"}, today=TODAY)
        self.assertEqual(state.missing_required_fields(), ["return"])

    def test_a_one_way_trip_needs_no_return_date(self):
        state = state_with(COMPLETE)
        self.assertTrue(state.is_one_way())
        self.assertEqual(state.missing_required_fields(), [])
        self.assertTrue(state.is_complete())

    def test_the_return_is_asked_for_after_the_departure_and_before_the_travellers(self):
        state = state_with({"origin": "Berlin", "destination": "Lissabon"})
        self.assertEqual(state.missing_required_fields(), ["departure", "return", "travelers"])
        state.apply({"trip_type": "one_way"}, today=TODAY)
        self.assertEqual(state.missing_required_fields(), ["departure", "travelers"])


class ApplyTests(SimpleTestCase):
    def test_takes_over_valid_values_with_provenance(self):
        state = TripState()
        rejected = state.apply(
            {**ROUND, "origin": "  Berlin ", "budget": 300, "max_stops": 0},
            provenance=INFERRED,
            today=TODAY,
        )
        self.assertEqual(rejected, {})
        self.assertEqual(state.value("origin"), "Berlin")
        self.assertEqual(state.provenance("origin"), INFERRED)
        self.assertEqual(state.value("departure"), day("2027-05-20"))
        self.assertEqual(state.value("return"), day("2027-05-27"))
        self.assertEqual(state.provenance("return"), INFERRED)
        self.assertEqual(state.value("travelers"), 2)
        self.assertEqual(
            state.value("budget"), {"amount": 300.0, "currency": "EUR", "basis": "per_person"}
        )
        self.assertEqual(state.value("max_stops"), 0)

    def test_accepts_a_departure_window_and_a_full_budget(self):
        state = TripState()
        rejected = state.apply(
            {
                "departure": {"earliest": "2027-05-20", "latest": "2027-05-24"},
                "return": {"earliest": "2027-05-27", "latest": "2027-05-30"},
                "budget": {"amount": 1200.456, "currency": "usd", "basis": "trip_total"},
            },
            today=TODAY,
        )
        self.assertEqual(rejected, {})
        self.assertEqual(
            state.value("departure"), {"earliest": "2027-05-20", "latest": "2027-05-24"}
        )
        self.assertEqual(
            state.value("return"), {"earliest": "2027-05-27", "latest": "2027-05-30"}
        )
        self.assertEqual(
            state.value("budget"), {"amount": 1200.46, "currency": "USD", "basis": "trip_total"}
        )

    def test_departure_today_is_allowed(self):
        state = TripState()
        self.assertEqual(state.apply({"departure": TODAY.isoformat()}, today=TODAY), {})
        self.assertEqual(state.value("departure"), day("2026-11-15"))

    def test_departure_and_return_on_the_same_day_are_allowed(self):
        state = TripState()
        rejected = state.apply({"departure": "2027-05-20", "return": "2027-05-20"}, today=TODAY)
        self.assertEqual(rejected, {})
        self.assertEqual(state.value("return"), day("2027-05-20"))

    def test_trip_types(self):
        for value in (ONE_WAY, ROUND_TRIP):
            with self.subTest(value):
                state = TripState()
                self.assertEqual(state.apply({"trip_type": value}, today=TODAY), {})
                self.assertEqual(state.value("trip_type"), value)
                self.assertEqual(state.provenance("trip_type"), CONFIRMED)
                self.assertEqual(state.is_one_way(), value == ONE_WAY)

    def test_invalid_values_are_rejected_and_never_stored(self):
        cases = {
            "origin": ["", "   ", 5, "x" * 101, ["Berlin"]],
            "destination": ["", {"city": "Lisbon"}],
            "departure": [
                "2026-11-14",  # yesterday
                "20. Mai",
                "2027-02-30",
                "2027-02-30T10:00:00",
                20270520,
                {},
                {"earliest": None, "latest": None},
                {"earliest": "2027-05-20", "latest": "bald"},
                {"earliest": "2020-01-01", "latest": "2026-11-14"},  # ended yesterday
            ],
            "return": [
                "2026-11-14",
                "nächste Woche",
                {"earliest": "2020-01-01", "latest": "2020-01-05"},
                {},
                True,
            ],
            "travelers": [0, -1, 2.5, "2", True],
            "budget": [
                0,
                -50,
                "300",
                True,
                float("nan"),
                float("inf"),
                {"amount": 300, "currency": "EURO"},
                {"amount": 300, "basis": "per_night"},
                {"currency": "EUR"},
            ],
            "max_stops": [-1, 1.5, "1", False],
            "trip_type": ["return", "oneway", "", True, 1, ["one_way"]],
        }
        for name, values in cases.items():
            for value in values:
                with self.subTest(field=name, value=value):
                    state = TripState()
                    rejected = state.apply({name: value}, today=TODAY)
                    self.assertEqual(list(rejected), [name])
                    self.assertTrue(rejected[name])
                    self.assertIsNone(state.value(name))
                    self.assertEqual(state.provenance(name), UNKNOWN)

    def test_an_invalid_value_keeps_the_previous_one_and_valid_ones_still_apply(self):
        state = state_with(COMPLETE)
        rejected = state.apply({"travelers": 0, "destination": "Porto"}, today=TODAY)
        self.assertEqual(list(rejected), ["travelers"])
        self.assertEqual(state.value("travelers"), 2)
        self.assertEqual(state.value("destination"), "Porto")

    def test_unknown_fields_are_rejected(self):
        state = TripState()
        self.assertEqual(list(state.apply({"hotel": "Ritz"}, today=TODAY)), ["hotel"])
        self.assertNotIn("hotel", state.to_dict())

    def test_a_confirmed_value_replaces_a_guess(self):
        state = TripState()
        state.apply({"travelers": 1}, provenance=INFERRED, today=TODAY)
        state.apply({"travelers": 3}, provenance=CONFIRMED, today=TODAY)
        self.assertEqual(state.value("travelers"), 3)
        self.assertEqual(state.provenance("travelers"), CONFIRMED)

    def test_none_clears_a_field(self):
        state = state_with({**ROUND, "budget": 300, "max_stops": 0})
        for name in ("origin", "return", "budget", "max_stops"):
            with self.subTest(name):
                self.assertEqual(state.apply({name: None}, today=TODAY), {})
                self.assertIsNone(state.value(name))
                self.assertEqual(state.provenance(name), UNKNOWN)
        self.assertEqual(state.missing_required_fields(), ["origin", "return"])

    def test_clearing_the_trip_type_makes_it_a_round_trip_again(self):
        state = state_with(COMPLETE)
        self.assertEqual(state.apply({"trip_type": None}, today=TODAY), {})
        self.assertFalse(state.is_one_way())
        self.assertEqual(state.missing_required_fields(), ["return"])

    def test_confirm_turns_guesses_into_confirmed_values(self):
        state = TripState()
        state.apply({"travelers": 2, "origin": "Berlin"}, provenance=INFERRED, today=TODAY)
        state.confirm(["travelers", "destination", "hotel"])
        self.assertEqual(state.provenance("travelers"), CONFIRMED)
        self.assertEqual(state.provenance("origin"), INFERRED)
        self.assertEqual(state.provenance("destination"), UNKNOWN)

    def test_unsupported_provenance_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            TripState().apply({"origin": "Berlin"}, provenance=UNKNOWN, today=TODAY)


class LenientValuesTests(SimpleTestCase):
    """Slips that are obvious to a human are repaired instead of rejected."""

    def test_a_reversed_window_is_swapped(self):
        for name in ("departure", "return"):
            with self.subTest(name):
                state = TripState()
                rejected = state.apply(
                    {name: {"earliest": "2027-05-24", "latest": "2027-05-20"}}, today=TODAY
                )
                self.assertEqual(rejected, {})
                self.assertEqual(
                    state.value(name), {"earliest": "2027-05-20", "latest": "2027-05-24"}
                )

    def test_a_window_that_began_in_the_past_starts_today(self):
        for name in ("departure", "return"):
            with self.subTest(name):
                state = TripState()
                rejected = state.apply(
                    {name: {"earliest": "2020-01-01", "latest": "2027-05-19"}}, today=TODAY
                )
                self.assertEqual(rejected, {})
                self.assertEqual(
                    state.value(name), {"earliest": "2026-11-15", "latest": "2027-05-19"}
                )

    def test_a_window_that_ends_today_is_today(self):
        state = TripState()
        rejected = state.apply(
            {"departure": {"earliest": "2026-11-01", "latest": "2026-11-15"}}, today=TODAY
        )
        self.assertEqual(rejected, {})
        self.assertEqual(state.value("departure"), day("2026-11-15"))

    def test_only_a_window_that_ended_before_today_is_rejected(self):
        state = TripState()
        rejected = state.apply(
            {"departure": {"earliest": "2026-11-01", "latest": "2026-11-14"}}, today=TODAY
        )
        self.assertEqual(list(rejected), ["departure"])
        self.assertIn("past", rejected["departure"])
        self.assertIsNone(state.value("departure"))

    def test_a_timestamp_is_read_as_its_date(self):
        for raw in (
            "2027-05-20T00:00:00",
            "2027-05-20T23:59:59+02:00",
            "2027-05-20 08:30",
            " 2027-05-20 ",
            datetime.date(2027, 5, 20),
            datetime.datetime(2027, 5, 20, 8, 30),
        ):
            with self.subTest(raw=raw):
                state = TripState()
                self.assertEqual(state.apply({"departure": raw, "return": raw}, today=TODAY), {})
                self.assertEqual(state.value("departure"), day("2027-05-20"))
                self.assertEqual(state.value("return"), day("2027-05-20"))

    def test_timestamps_inside_a_window_are_read_as_dates(self):
        state = TripState()
        rejected = state.apply(
            {"departure": {"earliest": "2027-05-20T00:00:00", "latest": "2027-05-24T00:00:00"}},
            today=TODAY,
        )
        self.assertEqual(rejected, {})
        self.assertEqual(
            state.value("departure"), {"earliest": "2027-05-20", "latest": "2027-05-24"}
        )

    def test_a_window_with_one_end_is_a_fixed_day(self):
        for raw in (
            {"latest": "2027-05-20"},
            {"earliest": "2027-05-20"},
            {"earliest": None, "latest": "2027-05-20"},
            {"earliest": "2027-05-20", "latest": None},
        ):
            with self.subTest(raw=raw):
                state = TripState()
                self.assertEqual(state.apply({"departure": raw, "return": raw}, today=TODAY), {})
                self.assertEqual(state.value("departure"), day("2027-05-20"))
                self.assertEqual(state.value("return"), day("2027-05-20"))

    def test_whole_numbers_written_as_floats_are_accepted(self):
        state = TripState()
        self.assertEqual(state.apply({"travelers": 2.0, "max_stops": 0.0}, today=TODAY), {})
        self.assertEqual(state.value("travelers"), 2)
        self.assertIsInstance(state.value("travelers"), int)
        self.assertEqual(state.value("max_stops"), 0)
        self.assertIsInstance(state.value("max_stops"), int)
        # Still not a number of people:
        self.assertEqual(list(state.apply({"travelers": 2.5}, today=TODAY)), ["travelers"])
        self.assertEqual(list(state.apply({"travelers": "2"}, today=TODAY)), ["travelers"])
        self.assertEqual(list(state.apply({"travelers": True}, today=TODAY)), ["travelers"])
        self.assertEqual(list(state.apply({"travelers": 0.0}, today=TODAY)), ["travelers"])
        self.assertEqual(state.value("travelers"), 2)


class LatestStatementWinsTests(SimpleTestCase):
    """A new value replaces an older one, also when it was only assumed."""

    def test_a_guess_replaces_a_confirmed_value_and_is_stored_as_a_guess(self):
        state = TripState()
        state.apply({"travelers": 2}, provenance=CONFIRMED, today=TODAY)
        rejected = state.apply({"travelers": 4}, provenance=INFERRED, today=TODAY)
        self.assertEqual(rejected, {})
        self.assertEqual(state.value("travelers"), 4)
        self.assertEqual(state.provenance("travelers"), INFERRED)

    def test_fields_named_as_inferred_are_stored_as_guesses_and_the_rest_as_given(self):
        state = state_with(ROUND)
        rejected = state.apply(
            {"departure": "2027-05-22", "destination": "Porto"},
            inferred={"departure"},
            today=TODAY,
        )
        self.assertEqual(rejected, {})
        self.assertEqual(state.value("departure"), day("2027-05-22"))
        self.assertEqual(state.provenance("departure"), INFERRED)
        self.assertEqual(state.value("destination"), "Porto")
        self.assertEqual(state.provenance("destination"), CONFIRMED)
        # Untouched fields keep their provenance.
        self.assertEqual(state.provenance("origin"), CONFIRMED)

    def test_inferred_accepts_any_collection_and_ignores_other_names(self):
        for names in (["travelers"], ("travelers", "hotel"), {"travelers", "budget"}):
            with self.subTest(names=names):
                state = TripState()
                rejected = state.apply(
                    {"travelers": 3, "origin": "Berlin"}, inferred=names, today=TODAY
                )
                self.assertEqual(rejected, {})
                self.assertEqual(state.provenance("travelers"), INFERRED)
                self.assertEqual(state.provenance("origin"), CONFIRMED)
                self.assertEqual(state.provenance("budget"), UNKNOWN)

    def test_an_invalid_guess_is_rejected_and_keeps_the_confirmed_value(self):
        state = TripState()
        state.apply({"travelers": 2}, today=TODAY)
        rejected = state.apply({"travelers": 0}, inferred={"travelers"}, today=TODAY)
        self.assertEqual(list(rejected), ["travelers"])
        self.assertEqual(state.value("travelers"), 2)
        self.assertEqual(state.provenance("travelers"), CONFIRMED)


class OriginAndDestinationTests(SimpleTestCase):
    def test_same_origin_and_destination_in_one_message_rejects_the_destination(self):
        for changes in (
            {"origin": "Hamburg", "destination": " hamburg "},
            {"destination": "HAMBURG", "origin": "Hamburg"},
        ):
            with self.subTest(order=list(changes)):
                state = TripState()
                rejected = state.apply(changes, today=TODAY)
                self.assertEqual(list(rejected), ["destination"])
                self.assertIn("different", rejected["destination"])
                self.assertEqual(state.value("origin"), "Hamburg")
                self.assertIsNone(state.value("destination"))

    def test_same_origin_and_destination_keep_an_older_different_destination(self):
        state = state_with({"origin": "Berlin", "destination": "Lissabon"})
        rejected = state.apply({"origin": "Hamburg", "destination": "Hamburg"}, today=TODAY)
        self.assertEqual(list(rejected), ["destination"])
        self.assertEqual(state.value("origin"), "Hamburg")
        self.assertEqual(state.value("destination"), "Lissabon")

    def test_same_origin_and_destination_never_leave_both_fields_equal(self):
        # The new origin equals the destination known so far; the rejected new
        # destination must not hide that from the check.
        state = state_with({"origin": "Berlin", "destination": "Hamburg"})
        rejected = state.apply({"origin": "Hamburg", "destination": "hamburg"}, today=TODAY)
        self.assertEqual(list(rejected), ["destination"])
        self.assertEqual(state.value("origin"), "Hamburg")
        # However the code resolves it: the state never holds the same place twice.
        self.assertNotEqual(
            (state.value("destination") or "").casefold(), state.value("origin").casefold()
        )

    def test_a_place_named_for_the_other_role_moves_there(self):
        # "berlin" was taken as origin; "no, I want to go TO Berlin" corrects that.
        state = state_with({"origin": "Berlin", "travelers": 2})
        self.assertEqual(state.apply({"destination": "berlin"}, today=TODAY), {})
        self.assertEqual(state.value("destination"), "berlin")
        self.assertEqual(state.provenance("destination"), CONFIRMED)
        self.assertIsNone(state.value("origin"))
        self.assertEqual(state.provenance("origin"), UNKNOWN)
        self.assertEqual(state.value("travelers"), 2)
        self.assertEqual(state.missing_required_fields(), ["origin", "departure", "return"])
        # … and the other way round.
        self.assertEqual(state.apply({"origin": "Berlin"}, today=TODAY), {})
        self.assertEqual(state.value("origin"), "Berlin")
        self.assertIsNone(state.value("destination"))
        self.assertEqual(state.provenance("destination"), UNKNOWN)

    def test_a_moved_place_clears_only_the_other_place(self):
        state = state_with({**ROUND, "budget": 300})
        self.assertEqual(state.apply({"origin": "Lissabon"}, today=TODAY), {})
        self.assertEqual(state.value("origin"), "Lissabon")
        self.assertEqual(state.missing_required_fields(), ["destination"])
        self.assertEqual(state.value("departure"), day("2027-05-20"))
        self.assertEqual(state.value("return"), day("2027-05-27"))
        self.assertEqual(state.value("budget")["amount"], 300.0)

    def test_origin_and_destination_can_be_swapped_in_one_step(self):
        state = state_with({"origin": "Berlin", "destination": "Lissabon"})
        self.assertEqual(
            state.apply({"origin": "Lissabon", "destination": "Berlin"}, today=TODAY), {}
        )
        self.assertEqual(state.value("origin"), "Lissabon")
        self.assertEqual(state.value("destination"), "Berlin")

    def test_two_new_places_may_reuse_a_known_one_in_the_other_role(self):
        state = state_with({"origin": "Berlin"})
        self.assertEqual(state.apply({"origin": "Rom", "destination": "Berlin"}, today=TODAY), {})
        self.assertEqual(state.value("origin"), "Rom")
        self.assertEqual(state.value("destination"), "Berlin")

    def test_a_guess_never_clears_a_known_place(self):
        for options in ({"provenance": INFERRED}, {"inferred": {"destination"}}):
            with self.subTest(options=options):
                state = state_with({"origin": "Hamburg"})
                rejected = state.apply({"destination": "Hamburg"}, today=TODAY, **options)
                self.assertEqual(list(rejected), ["destination"])
                self.assertIn("different", rejected["destination"])
                self.assertEqual(state.value("origin"), "Hamburg")
                self.assertEqual(state.provenance("origin"), CONFIRMED)
                self.assertIsNone(state.value("destination"))

    def test_a_guessed_origin_equal_to_the_destination_is_rejected_too(self):
        state = state_with({"origin": "Berlin", "destination": "Rom"})
        rejected = state.apply({"origin": "rom"}, inferred={"origin"}, today=TODAY)
        self.assertEqual(list(rejected), ["origin"])
        self.assertEqual(state.value("origin"), "Berlin")
        self.assertEqual(state.value("destination"), "Rom")


class ReturnAndTripTypeTests(SimpleTestCase):
    def test_a_return_date_turns_a_one_way_trip_into_a_round_trip(self):
        state = state_with(COMPLETE)
        self.assertEqual(state.apply({"return": "2027-05-27"}, today=TODAY), {})
        self.assertEqual(state.value("return"), day("2027-05-27"))
        self.assertEqual(state.value("trip_type"), ROUND_TRIP)
        self.assertFalse(state.is_one_way())
        self.assertTrue(state.is_complete())

    def test_a_return_date_leaves_an_unknown_trip_type_alone(self):
        state = state_with(ROUND)
        self.assertIsNone(state.value("trip_type"))
        self.assertEqual(state.provenance("trip_type"), UNKNOWN)

    def test_one_way_clears_a_known_return(self):
        state = state_with(ROUND)
        self.assertEqual(state.apply({"trip_type": "one_way"}, today=TODAY), {})
        self.assertIsNone(state.value("return"))
        self.assertEqual(state.provenance("return"), UNKNOWN)
        self.assertTrue(state.is_one_way())
        self.assertEqual(state.missing_required_fields(), [])

    def test_a_return_date_wins_over_one_way_in_the_same_call(self):
        for start in ({}, COMPLETE, ROUND):
            with self.subTest(start=start):
                state = state_with(start)
                rejected = state.apply(
                    {"trip_type": "one_way", "return": "2027-05-28"}, today=TODAY
                )
                self.assertEqual(rejected, {})
                self.assertEqual(state.value("return"), day("2027-05-28"))
                self.assertEqual(state.value("trip_type"), ROUND_TRIP)

    def test_round_trip_after_one_way_asks_for_the_return(self):
        state = state_with(COMPLETE)
        self.assertEqual(state.apply({"trip_type": "round_trip"}, today=TODAY), {})
        self.assertEqual(state.missing_required_fields(), ["return"])

    def test_clearing_the_return_keeps_the_trip_a_round_trip(self):
        state = state_with(ROUND)
        self.assertEqual(state.apply({"return": None}, today=TODAY), {})
        self.assertFalse(state.is_one_way())
        self.assertEqual(state.missing_required_fields(), ["return"])

    def test_a_new_return_before_the_departure_is_rejected(self):
        state = state_with(ROUND)
        rejected = state.apply({"return": "2027-05-19"}, today=TODAY)
        self.assertEqual(list(rejected), ["return"])
        self.assertIn("before the departure", rejected["return"])
        # The return known so far still fits and stays.
        self.assertEqual(state.value("return"), day("2027-05-27"))
        self.assertEqual(state.value("departure"), day("2027-05-20"))

    def test_a_first_return_before_the_departure_is_rejected(self):
        state = state_with({**ROUND, "return": None})
        rejected = state.apply({"return": "2027-05-19"}, today=TODAY)
        self.assertEqual(list(rejected), ["return"])
        self.assertIsNone(state.value("return"))
        self.assertEqual(state.missing_required_fields(), ["return"])

    def test_a_return_before_the_departure_of_the_same_call_is_rejected(self):
        state = TripState()
        rejected = state.apply({"departure": "2027-05-20", "return": "2027-05-19"}, today=TODAY)
        self.assertEqual(list(rejected), ["return"])
        self.assertTrue(rejected["return"])
        self.assertEqual(state.value("departure"), day("2027-05-20"))
        self.assertIsNone(state.value("return"))

    def test_a_rejected_return_never_leaves_an_older_return_before_the_new_departure(self):
        # Departure and return are both new, the new return is rejected: the
        # return known so far lies before the new departure and is outdated.
        state = state_with(ROUND)
        rejected = state.apply({"departure": "2027-06-10", "return": "2027-06-05"}, today=TODAY)
        self.assertEqual(list(rejected), ["return"])
        self.assertEqual(state.value("departure"), day("2027-06-10"))
        # However the code resolves it: the state never holds a return before the departure.
        back = state.value("return")
        if back is not None:
            self.assertGreaterEqual(back["latest"], state.value("departure")["earliest"])

    def test_the_return_is_compared_with_the_earliest_departure(self):
        state = state_with({"departure": {"earliest": "2027-05-20", "latest": "2027-05-25"}})
        # In the middle of the departure window: possible.
        self.assertEqual(state.apply({"return": "2027-05-22"}, today=TODAY), {})
        # A window that ends before the earliest departure: impossible.
        rejected = state.apply(
            {"return": {"earliest": "2027-05-10", "latest": "2027-05-19"}}, today=TODAY
        )
        self.assertEqual(list(rejected), ["return"])
        self.assertEqual(state.value("return"), day("2027-05-22"))

    def test_a_new_departure_after_the_known_return_clears_the_return(self):
        state = state_with(ROUND)
        self.assertEqual(state.apply({"departure": "2027-06-10"}, today=TODAY), {})
        self.assertEqual(state.value("departure"), day("2027-06-10"))
        self.assertIsNone(state.value("return"))
        self.assertEqual(state.provenance("return"), UNKNOWN)
        self.assertEqual(state.missing_required_fields(), ["return"])

    def test_a_new_departure_before_the_known_return_keeps_the_return(self):
        state = state_with(ROUND)
        self.assertEqual(state.apply({"departure": "2027-05-27"}, today=TODAY), {})
        self.assertEqual(state.value("return"), day("2027-05-27"))
        self.assertTrue(state.is_complete())

    def test_a_new_departure_together_with_a_fitting_return_keeps_both(self):
        state = state_with(ROUND)
        rejected = state.apply({"departure": "2027-06-10", "return": "2027-06-17"}, today=TODAY)
        self.assertEqual(rejected, {})
        self.assertEqual(state.value("departure"), day("2027-06-10"))
        self.assertEqual(state.value("return"), day("2027-06-17"))

    def test_a_one_way_trip_has_no_return_to_compare(self):
        state = state_with(COMPLETE)
        self.assertEqual(state.apply({"departure": "2027-06-10"}, today=TODAY), {})
        self.assertTrue(state.is_complete())


class SerialisationTests(SimpleTestCase):
    def test_every_field_is_always_present(self):
        self.assertEqual(
            TripState().to_dict(),
            {name: {"value": None, "provenance": "unknown"} for name in FIELD_NAMES},
        )
        self.assertEqual(len(TripState().to_dict()), 8)
        self.assertEqual(list(TripState().to_dict()), list(FIELD_NAMES))

    def test_round_trip(self):
        state = TripState()
        state.apply({**ROUND, "budget": 300, "trip_type": "round_trip"}, today=TODAY)
        state.apply({"max_stops": 1}, provenance=INFERRED, today=TODAY)
        self.assertEqual(TripState(state.to_dict()).to_dict(), state.to_dict())

    def test_ignores_unknown_names_in_stored_data(self):
        state = TripState({"hotel": {"value": "Ritz", "provenance": "confirmed"}, "origin": "x"})
        self.assertNotIn("hotel", state.to_dict())
        self.assertIsNone(state.value("origin"))

    def test_data_stored_before_the_return_existed_is_a_round_trip_without_return(self):
        old = {
            "origin": {"value": "Berlin", "provenance": "confirmed"},
            "destination": {"value": "Lissabon", "provenance": "confirmed"},
            "departure": {"value": day("2027-05-20"), "provenance": "confirmed"},
            "travelers": {"value": 2, "provenance": "confirmed"},
            "budget": {"value": None, "provenance": "unknown"},
            "max_stops": {"value": None, "provenance": "unknown"},
        }
        state = TripState(old)
        self.assertEqual(len(state.to_dict()), 8)
        self.assertEqual(state.missing_required_fields(), ["return"])


class PersistenceTests(TestCase):
    def test_a_new_session_has_an_empty_state(self):
        session = PlanningSession.objects.create(title="Trip")
        self.assertEqual(load_trip_state(session).missing_required_fields(), [
            "origin", "destination", "departure", "return", "travelers",
        ])

    def test_state_is_saved_and_loaded_per_session(self):
        session = PlanningSession.objects.create(title="Lisbon")
        other = PlanningSession.objects.create(title="Other")
        state = load_trip_state(session)
        state.apply({**ROUND, "budget": 300}, today=TODAY)
        save_trip_state(session, state)

        reloaded = load_trip_state(PlanningSession.objects.get(pk=session.pk))
        self.assertEqual(reloaded.to_dict(), state.to_dict())
        self.assertTrue(reloaded.is_complete())
        self.assertEqual(reloaded.provenance("budget"), CONFIRMED)
        self.assertEqual(reloaded.value("return"), day("2027-05-27"))
        self.assertFalse(load_trip_state(PlanningSession.objects.get(pk=other.pk)).is_complete())

    def test_a_one_way_trip_is_saved_and_loaded(self):
        session = PlanningSession.objects.create(title="Lisbon")
        state = load_trip_state(session)
        state.apply(COMPLETE, today=TODAY)
        save_trip_state(session, state)
        reloaded = load_trip_state(PlanningSession.objects.get(pk=session.pk))
        self.assertTrue(reloaded.is_one_way())
        self.assertTrue(reloaded.is_complete())

    def test_saving_the_state_leaves_other_columns_alone(self):
        session = PlanningSession.objects.create(title="Lisbon")
        PlanningSession.objects.filter(pk=session.pk).update(title="Renamed elsewhere")
        save_trip_state(session, TripState())
        self.assertEqual(PlanningSession.objects.get(pk=session.pk).title, "Renamed elsewhere")
