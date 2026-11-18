"""Trip state: everything known about the trip of one planning session.

Each field holds a value and its provenance:

    {"origin": {"value": "Berlin", "provenance": "confirmed"}, ...}

- confirmed: stated by the user (chat or form)
- inferred:  assumed by the agent from a vague statement, not yet confirmed
- unknown:   no value (value is None)

The search request to the Journey Planner is later built from this state.

Principle for conflicts: what the user said last wins. A new value is only
rejected when it is invalid in itself (a date in the past, zero travellers).
When it contradicts an older value, the older value is cleared and the agent
asks for it again; a correct statement must never be dropped silently.
"""

import datetime
import re
from decimal import Decimal, InvalidOperation

from planning.models import PlanningSession

CONFIRMED = "confirmed"
INFERRED = "inferred"
UNKNOWN = "unknown"

ONE_WAY = "one_way"
ROUND_TRIP = "round_trip"

# Fixed order: the agent asks for missing required fields in this order.
# "return" is not required for a one-way trip.
REQUIRED_FIELDS = ("origin", "destination", "departure", "return", "travelers")
OPTIONAL_FIELDS = ("budget", "max_stops", "trip_type")
FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS

BUDGET_BASES = ("per_person", "trip_total")
TRIP_TYPES = (ROUND_TRIP, ONE_WAY)


class InvalidValue(ValueError):
    """A value does not fit its field; the message says why."""


class TripState:
    def __init__(self, data: dict | None = None):
        self._fields = {name: {"value": None, "provenance": UNKNOWN} for name in FIELDS}
        for name, entry in (data or {}).items():
            # Stored data was validated when it was written; unknown names
            # (e.g. from an older version) are dropped.
            if name in self._fields and isinstance(entry, dict) and entry.get("value") is not None:
                provenance = entry.get("provenance")
                self._fields[name] = {
                    "value": entry["value"],
                    "provenance": provenance if provenance in (CONFIRMED, INFERRED) else INFERRED,
                }

    def to_dict(self) -> dict:
        return {name: dict(entry) for name, entry in self._fields.items()}

    def value(self, name: str):
        return self._fields[name]["value"]

    def provenance(self, name: str) -> str:
        return self._fields[name]["provenance"]

    def is_one_way(self) -> bool:
        return self._fields["trip_type"]["value"] == ONE_WAY

    def missing_required_fields(self) -> list[str]:
        """Required fields without a value, in the order they are asked for."""
        return [
            name
            for name in REQUIRED_FIELDS
            if self._fields[name]["value"] is None and not (name == "return" and self.is_one_way())
        ]

    def is_complete(self) -> bool:
        return not self.missing_required_fields()

    def apply(
        self,
        changes: dict,
        *,
        provenance: str = CONFIRMED,
        inferred=(),
        today: datetime.date | None = None,
    ) -> dict[str, str]:
        """Take over the valid values from `changes` and return the rejected ones.

        The result maps each rejected field to the reason. Invalid values never
        reach the state. `None` clears a field. Values that contradict an
        older value replace it; see `_resolve_conflicts`. Fields named in
        `inferred` are stored as assumed, all others with `provenance`.
        """
        if provenance not in (CONFIRMED, INFERRED):
            raise ValueError(f"Unsupported provenance {provenance!r}.")
        today = today or datetime.date.today()
        assumed = set(inferred)

        def source(name: str) -> str:
            return INFERRED if name in assumed else provenance

        rejected: dict[str, str] = {}
        cleared: list[str] = []
        valid: dict = {}
        for name, raw in changes.items():
            if name not in self._fields:
                rejected[name] = "Unknown field."
            elif raw is None:
                cleared.append(name)
            else:
                try:
                    valid[name] = _VALIDATORS[name](raw, today)
                except InvalidValue as error:
                    rejected[name] = str(error)

        for name in cleared:
            self._set(name, None, UNKNOWN)
        self._resolve_conflicts(valid, rejected, source)
        for name, value in valid.items():
            self._set(name, value, source(name))
        return rejected

    def _set(self, name: str, value, provenance: str) -> None:
        self._fields[name] = {"value": value, "provenance": UNKNOWN if value is None else provenance}

    def _resolve_conflicts(self, valid: dict, rejected: dict, source) -> None:
        """Make the new values fit each other and the values already known.

        `valid` holds the new values and is changed in place; fields of the
        state that a new value makes obsolete are cleared here.
        """
        # Origin and destination must differ.
        origin, destination = valid.get("origin"), valid.get("destination")
        if origin is not None and destination is not None:
            # Both in one message: they can be swapped, but not be equal.
            if origin.casefold() == destination.casefold():
                del valid["destination"]
                rejected["destination"] = "Origin and destination must be different places."
        for name, other in (("origin", "destination"), ("destination", "origin")):
            new, known = valid.get(name), self._fields[other]["value"]
            if new is None or other in valid or known is None:
                continue
            if new.casefold() == known.casefold():
                if source(name) == CONFIRMED:
                    # "No, I want to go TO Berlin": the place changes its
                    # role and the other field is open again.
                    self._set(other, None, UNKNOWN)
                else:
                    del valid[name]
                    rejected[name] = "Origin and destination must be different places."

        # The return must not lie before the departure.
        departure = valid.get("departure") or self._fields["departure"]["value"]
        if "return" in valid and departure and valid["return"]["latest"] < departure["earliest"]:
            del valid["return"]
            rejected["return"] = "The return must not be before the departure."
        known_return = self._fields["return"]["value"]
        if "return" not in valid and departure and known_return:
            if known_return["latest"] < departure["earliest"]:
                # A new departure after the known return: the return is outdated.
                self._set("return", None, UNKNOWN)

        # A (valid) return date makes the trip a round trip; one-way has no return date.
        if "return" in valid:
            if valid.get("trip_type") == ONE_WAY or self.is_one_way():
                valid["trip_type"] = ROUND_TRIP
        elif valid.get("trip_type") == ONE_WAY:
            self._set("return", None, UNKNOWN)

    def confirm(self, names) -> None:
        """Mark assumed values as confirmed by the user; other fields stay as they are."""
        for name in names:
            entry = self._fields.get(name)
            if entry and entry["value"] is not None and entry["provenance"] == INFERRED:
                entry["provenance"] = CONFIRMED


def load_trip_state(session: PlanningSession) -> TripState:
    return TripState(session.trip_state)


def save_trip_state(session: PlanningSession, state: TripState) -> None:
    session.trip_state = state.to_dict()
    session.save(update_fields=["trip_state"])


def _place(raw, today) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidValue("Must be a non-empty text.")
    value = raw.strip()
    if len(value) > 100:
        raise InvalidValue("Must not be longer than 100 characters.")
    return value


def _date(raw, label: str) -> datetime.date:
    if isinstance(raw, datetime.datetime):
        return raw.date()
    if isinstance(raw, datetime.date):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        # A timestamp such as 2027-05-20T00:00:00 is read as its date.
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ].*", text):
            text = text[:10]
        try:
            return datetime.date.fromisoformat(text)
        except ValueError:
            pass
    raise InvalidValue(f"{label} must be a date in the format YYYY-MM-DD.")


def _window(label: str):
    """Validator for a single date ("2027-05-20") or a window ({"earliest", "latest"})."""

    def validate(raw, today) -> dict:
        if isinstance(raw, dict):
            first = raw.get("earliest") if raw.get("earliest") is not None else raw.get("latest")
            last = raw.get("latest") if raw.get("latest") is not None else raw.get("earliest")
            if first is None:
                raise InvalidValue(f"The {label} date is missing.")
            earliest = _date(first, f"The earliest {label} date")
            latest = _date(last, f"The latest {label} date")
            if latest < earliest:
                # An obvious slip; the two ends are swapped.
                earliest, latest = latest, earliest
        else:
            earliest = latest = _date(raw, f"The {label} date")
        if latest < today:
            raise InvalidValue(f"The {label} date must not be in the past.")
        # A window that started already ("this week") begins today.
        earliest = max(earliest, today)
        return {"earliest": earliest.isoformat(), "latest": latest.isoformat()}

    return validate


def _integer(raw, *, minimum: int, label: str) -> int:
    # bool is a subclass of int; True must not count as 1 traveller.
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise InvalidValue(f"{label} must be a whole number.")
    if raw < minimum:
        raise InvalidValue(f"{label} must be at least {minimum}.")
    return raw


def _travelers(raw, today) -> int:
    return _integer(raw, minimum=1, label="The number of travellers")


def _max_stops(raw, today) -> int:
    return _integer(raw, minimum=0, label="The maximum number of stops")


def _budget(raw, today) -> dict:
    """A plain amount (EUR per person) or a money object as in the API conventions."""
    if isinstance(raw, dict):
        amount_raw = raw.get("amount")
        currency = raw.get("currency") or "EUR"
        basis = raw.get("basis") or "per_person"
    else:
        amount_raw, currency, basis = raw, "EUR", "per_person"
    if isinstance(amount_raw, bool) or not isinstance(amount_raw, (int, float, Decimal)):
        raise InvalidValue("The budget must be a number.")
    try:
        amount = Decimal(str(amount_raw))
    except InvalidOperation:
        raise InvalidValue("The budget must be a number.") from None
    if not amount.is_finite() or amount <= 0:
        raise InvalidValue("The budget must be greater than 0.")
    if not isinstance(currency, str) or len(currency.strip()) != 3 or not currency.strip().isalpha():
        raise InvalidValue("The currency must be a three-letter ISO 4217 code.")
    if basis not in BUDGET_BASES:
        raise InvalidValue(f"The budget basis must be one of {', '.join(BUDGET_BASES)}.")
    return {
        "amount": float(round(amount, 2)),
        "currency": currency.strip().upper(),
        "basis": basis,
    }


def _trip_type(raw, today) -> str:
    if raw not in TRIP_TYPES:
        raise InvalidValue(f"The trip type must be one of {', '.join(TRIP_TYPES)}.")
    return raw


_VALIDATORS = {
    "origin": _place,
    "destination": _place,
    "departure": _window("departure"),
    "return": _window("return"),
    "travelers": _travelers,
    "budget": _budget,
    "max_stops": _max_stops,
    "trip_type": _trip_type,
}
