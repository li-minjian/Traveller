"""Rule-based stand-in for the LLM, so the chat runs without any LLM access.

It is not intelligent: it recognises a few fixed patterns in German and
English. It follows the conventions of the agent's prompts (package `agent`):

- For a reply, the agent passes the answer it would give without an LLM as
  `fallback`; it is returned unchanged.
- A schema with a `strategy` enum is answered with the first allowed strategy.
- Any other schema is the extraction of trip data from the user's last message.
"""

import datetime
import json
import re

from llm.base import Generation, LLMClient, Message

_MONTHS = {
    "januar": 1, "january": 1, "jan": 1, "februar": 2, "february": 2, "feb": 2,
    "märz": 3, "maerz": 3, "march": 3, "mar": 3, "april": 4, "apr": 4, "mai": 5, "may": 5,
    "juni": 6, "june": 6, "jun": 6, "juli": 7, "july": 7, "jul": 7, "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9, "oktober": 10, "october": 10, "okt": 10, "oct": 10,
    "november": 11, "nov": 11, "dezember": 12, "december": 12, "dez": 12, "dec": 12,
}
_NUMBER_WORDS = {
    "ein": 1, "eine": 1, "einen": 1, "einem": 1, "eins": 1, "one": 1, "zwei": 2, "two": 2,
    "drei": 3, "three": 3, "vier": 4, "four": 4, "fünf": 5, "five": 5, "sechs": 6, "six": 6,
}
_GROUP_WORDS = {
    "alleine": 1, "allein": 1, "alone": 1, "solo": 1, "zu zweit": 2, "wir beide": 2,
    "zu dritt": 3, "zu viert": 4, "zu fünft": 5, "zu sechst": 6,
}
_NOT_A_PLACE = {
    "hallo", "hi", "hey", "moin", "ja", "nein", "ok", "okay", "danke", "egal", "yes", "no",
    "thanks", "hello",
}
_PLACE = r"([A-ZÄÖÜ][\wäöüß.\-]*(?:\s[A-ZÄÖÜ][\wäöüß.\-]*)?)"
_NUMBER = r"(\d+|" + "|".join(_NUMBER_WORDS) + r")"
_PEOPLE = r"(?:personen|person|leuten|leute|erwachsenen|erwachsene|reisenden|reisende|people|persons|travell?ers|adults)"
_STOPS = r"(?:umstiegen|umstiege|umstieg|zwischenstopps|zwischenstopp|stopps|stopp|stops|stop)"


class OfflineLLM(LLMClient):
    model = "offline"

    def __init__(self, *, today: datetime.date | None = None):
        super().__init__(max_attempts=1, retry_delay_seconds=0)
        self._today = today

        self._fallback = None

    def chat(self, messages, *, system=None, fallback=None):
        self._fallback = fallback
        try:
            return super().chat(messages, system=system)
        finally:
            self._fallback = None

    def _generate(
        self, messages: list[Message], system: str | None, schema: dict | None
    ) -> Generation:
        last = messages[-1].content if messages else ""
        if schema is None:
            text = self._fallback if self._fallback is not None else last
        elif "strategy" in schema.get("properties", {}):
            text = json.dumps({"strategy": schema["properties"]["strategy"]["enum"][0]})
        else:
            asked = re.search(r"^Asked field: (\w+)", system or "", re.MULTILINE)
            text = json.dumps(
                extract(last, today=self._today, asked=asked.group(1) if asked else None)
            )
        return Generation(text=text, input_tokens=0, output_tokens=0)


def extract(text: str, *, today: datetime.date | None = None, asked: str | None = None) -> dict:
    """Read trip data from one message; unknown values are None."""
    today = today or datetime.date.today()
    lower = text.lower()
    result = dict.fromkeys(
        ("origin", "destination", "departure_earliest", "departure_latest",
         "return_earliest", "return_latest", "one_way",
         "travelers", "budget_amount", "budget_basis", "max_stops")
    )
    result["cleared"] = []
    result["inferred"] = []
    result["intent"] = "trip_info"
    result["note"] = None
    # "ja", "passt" … confirm whatever the agent asked to confirm.
    agrees = re.fullmatch(
        r"(ja|jo|jep|jap|genau|passt|passt so|stimmt|richtig|ok|okay|yes|yep|correct|exactly)[.! ]*",
        lower.strip(),
    )
    result["confirmed"] = (
        ["origin", "destination", "departure", "return", "travelers"] if agrees else []
    )

    origin = re.search(r"\b(?:von|ab|aus|from)\s+" + _PLACE, text)
    destination = re.search(r"\b(?:nach|to)\s+" + _PLACE, text)
    if origin:
        result["origin"] = origin.group(1)
    if destination:
        result["destination"] = destination.group(1)

    # Each part of the sentence is either about the way there or about the
    # way back: "am 20. Mai nach Lissabon und am 27. Mai zurück". Inside one
    # part, "bis" separates the two: "vom 20. bis 27. Mai".
    out_dates, back_dates = [], []
    in_range, was_return = False, False
    for part in re.split(r",(?!\s*\d{4})|;|\bund\b|\band\b", lower):
        is_return = asked == "return" or bool(
            re.search(r"\b(zurück|zurueck|rückflug|rückreise|heimflug|return|back)\b", part)
        )
        # "zurück zwischen 27. Mai und 30. Mai": the part after "und" belongs to the range.
        if in_range:
            is_return = was_return
        in_range, was_return = bool(re.search(r"\b(zwischen|between)\b", part)), is_return
        # "vom 20. bis 27. Mai", but not "bis zu 300 €" or "bis zu 2 Umstiege".
        until = re.search(r"\bbis(?: zum)?\b(?! zu\b)", part)
        if until and not is_return:
            out_dates += _dates(part[: until.start()], today)
            back_dates += _dates(part[until.end():], today)
        elif is_return:
            back_dates += _dates(part, today)
        else:
            out_dates += _dates(part, today)
    if out_dates:
        result["departure_earliest"] = min(out_dates).isoformat()
        result["departure_latest"] = max(out_dates).isoformat()
        # A return without a year is the next such date after the departure.
        back_dates = [
            date.replace(year=date.year + 1) if date < min(out_dates) else date for date in back_dates
        ]
    if back_dates:
        result["return_earliest"] = min(back_dates).isoformat()
        result["return_latest"] = max(back_dates).isoformat()
    if re.search(r"\b(nur hinflug|nur hin|ohne rückflug|kein rückflug|one way|one-way|oneway)\b", lower):
        result["one_way"] = True

    budget = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:€|euro\b|eur\b)", lower)
    if budget:
        result["budget_amount"] = float(budget.group(1).replace(",", "."))
        total = re.search(r"\b(insgesamt|gesamt|zusammen|total|in total)\b", lower)
        result["budget_basis"] = "trip_total" if total else "per_person"

    if re.search(r"\b(direkt|direktflug|nonstop|non-stop|ohne umstieg|ohne zwischenstopp)", lower):
        result["max_stops"] = 0
    else:
        stops = re.search(
            r"\b(?:max(?:imal)?\.?|höchstens|at most)\s+" + _NUMBER + r"\s*(?:x\s*)?" + _STOPS, lower
        )
        if stops:
            result["max_stops"] = _number(stops.group(1))

    people = re.search(r"\b" + _NUMBER + r"\s+" + _PEOPLE + r"\b", lower)
    if people:
        result["travelers"] = _number(people.group(1))
    else:
        for words, count in _GROUP_WORDS.items():
            if re.search(r"\b" + words + r"\b", lower):
                result["travelers"] = count
                break

    # A bare answer to the question the agent just asked, e.g. "Berlin" or "2".
    bare = text.strip().strip(".!")
    if asked in ("origin", "destination") and result[asked] is None:
        if _looks_like_a_place(bare):
            result[asked] = bare
    elif asked == "travelers" and result["travelers"] is None:
        if bare.lower() in _NUMBER_WORDS or bare.isdigit():
            result["travelers"] = _number(bare.lower())
    # A message without any trip data is small talk, not a search request.
    said_something = result["confirmed"] or any(
        result[name] is not None
        for name in result
        if name not in ("inferred", "confirmed", "cleared", "intent", "note")
    )
    if not said_something:
        result["intent"] = "smalltalk"
    return result


def _looks_like_a_place(text: str) -> bool:
    words = text.split()
    if not words or len(words) > 3 or re.search(r"\d", text):
        return False
    if len(words) == 1:
        return text.lower() not in _NOT_A_PLACE
    return all(word[0].isupper() for word in words)


def _number(text: str) -> int:
    return int(text) if text.isdigit() else _NUMBER_WORDS[text]


def _dates(lower: str, today: datetime.date) -> list[datetime.date]:
    found = []
    for year, month, day in re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", lower):
        _add(found, int(year), int(month), int(day), today)
    # 20.05.2027, 20.5.27, 20.5.
    for day, month, year in re.findall(r"\b(\d{1,2})\.\s?(\d{1,2})\.(\d{4}|\d{2})?(?!\d)", lower):
        full_year = int(year) + (2000 if year and len(year) == 2 else 0) if year else None
        _add(found, full_year, int(month), int(day), today)
    # 20. Mai, 20. Mai 2027, May 20
    names = "|".join(sorted(_MONTHS, key=len, reverse=True))
    for day, name, year in re.findall(rf"\b(\d{{1,2}})\.?\s+({names})\b\.?(?:\s+(\d{{4}}))?", lower):
        _add(found, int(year) if year else None, _MONTHS[name], int(day), today)
    for name, day, year in re.findall(
        rf"\b({names})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?", lower
    ):
        _add(found, int(year) if year else None, _MONTHS[name], int(day), today)
    return found


def _add(found, year, month, day, today):
    try:
        if year is None:
            # Without a year, the next such date that is not in the past.
            date = datetime.date(today.year, month, day)
            if date < today:
                date = datetime.date(today.year + 1, month, day)
        else:
            date = datetime.date(year, month, day)
    except ValueError:
        return
    if date not in found:
        found.append(date)
