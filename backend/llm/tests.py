"""Tests for the LLM package. No test needs network access or credentials."""

import datetime
import io
import json
import urllib.error
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from llm import (
    FakeLLM,
    LLMError,
    LLMInvalidResponse,
    LLMQuotaExceeded,
    LLMTimeout,
    LLMUnavailable,
    Message,
    get_llm_client,
)
from llm.gemini import GeminiClient
from llm.offline import OfflineLLM, extract

HELLO = [Message("user", "Hello, my secret plan")]
SCHEMA = {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}


class SharedInterfaceTests(SimpleTestCase):
    """Behaviour of the base class, exercised through the fake."""

    def test_chat_returns_the_text(self):
        llm = FakeLLM(["  Hi there  "])
        with self.assertLogs("llm.base", level="INFO"):
            self.assertEqual(llm.chat(HELLO, system="Be brief."), "Hi there")
        self.assertEqual(llm.calls[0]["system"], "Be brief.")
        self.assertEqual(llm.calls[0]["messages"], HELLO)

    def test_structured_returns_the_parsed_object(self):
        llm = FakeLLM([{"city": "Lisbon"}])
        with self.assertLogs("llm.base", level="INFO"):
            self.assertEqual(llm.structured(HELLO, schema=SCHEMA), {"city": "Lisbon"})
        self.assertEqual(llm.calls[0]["schema"], SCHEMA)

    def test_invalid_structured_answers_are_retried_then_fail(self):
        cases = {
            "not json": "Sure! Lisbon.",
            "not an object": '["Lisbon"]',
            "required key missing": '{"country": "Portugal"}',
            "empty": "",
        }
        for name, answer in cases.items():
            with self.subTest(name), self.assertLogs("llm.base", level="WARNING"):
                llm = FakeLLM([answer, answer])
                with self.assertRaises(LLMInvalidResponse):
                    llm.structured(HELLO, schema=SCHEMA)
                self.assertEqual(len(llm.calls), 2)

    def test_a_retry_can_succeed(self):
        llm = FakeLLM([LLMTimeout("slow"), LLMUnavailable("down"), "ok"], max_attempts=3)
        with self.assertLogs("llm.base", level="WARNING"):
            self.assertEqual(llm.chat(HELLO), "ok")
        self.assertEqual(len(llm.calls), 3)

    def test_timeout_fails_with_a_defined_error_after_the_last_attempt(self):
        llm = FakeLLM([LLMTimeout("slow"), LLMTimeout("slow"), "never used"])
        with self.assertLogs("llm.base", level="WARNING"), self.assertRaises(LLMTimeout):
            llm.chat(HELLO)
        self.assertEqual(len(llm.calls), 2)

    def test_quota_errors_are_not_retried(self):
        llm = FakeLLM([LLMQuotaExceeded("quota"), "never used"])
        with self.assertLogs("llm.base", level="WARNING"), self.assertRaises(LLMQuotaExceeded):
            llm.chat(HELLO)
        self.assertEqual(len(llm.calls), 1)

    def test_fake_without_script_fails_clearly(self):
        with self.assertLogs("llm.base", level="WARNING"), self.assertRaises(LLMError):
            FakeLLM().chat(HELLO)

    def test_logs_metadata_but_no_conversation_content(self):
        llm = FakeLLM(["The secret answer", LLMQuotaExceeded("quota")])
        with self.assertLogs("llm.base", level="INFO") as logs:
            llm.chat(HELLO, system="secret system prompt")
            with self.assertRaises(LLMQuotaExceeded):
                llm.chat(HELLO)
        output = "\n".join(logs.output)
        self.assertIn("model=fake", output)
        self.assertIn("duration_ms=", output)
        self.assertIn("input_tokens=0", output)
        self.assertIn("LLMQuotaExceeded", output)
        self.assertNotIn("secret", output)


def _http_response(payload: dict):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def _http_error(code: int):
    return urllib.error.HTTPError("https://example.invalid", code, "error", {}, io.BytesIO(b"{}"))


GEMINI_ANSWER = {
    "candidates": [{"content": {"role": "model", "parts": [{"text": '{"city": "Lisbon"}'}]}}],
    "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 5},
}


class GeminiClientTests(SimpleTestCase):
    def make_client(self, **overrides):
        options = {
            "api_key": "test-key-123",
            "model": "test-model",
            "endpoint": "https://llm.example.invalid/v1/models/{model}:generateContent",
            "timeout_seconds": 7,
            "max_attempts": 1,
        }
        return GeminiClient(**{**options, **overrides})

    def test_sends_the_conversation_and_reads_text_and_tokens(self):
        conversation = [
            Message("user", "Where to?"),
            Message("assistant", "Tell me more."),
            Message("user", "Lisbon"),
        ]
        with (
            patch("llm.gemini.urllib.request.urlopen", return_value=_http_response(GEMINI_ANSWER))
            as urlopen,
            self.assertLogs("llm.base", level="INFO") as logs,
        ):
            result = self.make_client().structured(conversation, schema=SCHEMA, system="Extract.")

        self.assertEqual(result, {"city": "Lisbon"})
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://llm.example.invalid/v1/models/test-model:generateContent",
        )
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key-123")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 7)
        body = json.loads(request.data)
        self.assertEqual([turn["role"] for turn in body["contents"]], ["user", "model", "user"])
        self.assertEqual(body["contents"][2]["parts"], [{"text": "Lisbon"}])
        self.assertEqual(body["systemInstruction"], {"parts": [{"text": "Extract."}]})
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(body["generationConfig"]["responseJsonSchema"], SCHEMA)
        self.assertIn("input_tokens=12 output_tokens=5", logs.output[0])
        self.assertNotIn("test-key-123", "\n".join(logs.output))

    def test_plain_chat_sends_no_generation_config(self):
        answer = {"candidates": [{"content": {"parts": [{"text": "Hi"}]}}]}
        with (
            patch("llm.gemini.urllib.request.urlopen", return_value=_http_response(answer))
            as urlopen,
            self.assertLogs("llm.base", level="INFO"),
        ):
            self.assertEqual(self.make_client().chat(HELLO), "Hi")
        body = json.loads(urlopen.call_args.args[0].data)
        self.assertNotIn("generationConfig", body)
        self.assertNotIn("systemInstruction", body)

    def test_maps_provider_failures_to_defined_errors(self):
        cases = [
            (_http_error(429), LLMQuotaExceeded),
            (_http_error(503), LLMUnavailable),
            (_http_error(504), LLMTimeout),
            (TimeoutError("timed out"), LLMTimeout),
            (urllib.error.URLError(TimeoutError("timed out")), LLMTimeout),
            (urllib.error.URLError("name resolution failed"), LLMUnavailable),
        ]
        for failure, expected in cases:
            with (
                self.subTest(expected=expected.__name__, failure=repr(failure)),
                patch("llm.gemini.urllib.request.urlopen", side_effect=failure),
                self.assertLogs("llm.base", level="WARNING"),
                self.assertRaises(expected),
            ):
                self.make_client().chat(HELLO)

    def test_rejected_requests_are_not_retried_and_hide_the_key(self):
        with (
            patch("llm.gemini.urllib.request.urlopen", side_effect=_http_error(403)) as urlopen,
            self.assertLogs("llm.base", level="WARNING"),
            self.assertRaises(LLMError) as raised,
        ):
            self.make_client(max_attempts=3).chat(HELLO)
        self.assertIs(type(raised.exception), LLMError)
        self.assertEqual(urlopen.call_count, 1)
        self.assertNotIn("test-key-123", str(raised.exception))

    def test_answers_without_text_are_invalid(self):
        cases = {
            "blocked prompt": {"promptFeedback": {"blockReason": "SAFETY"}},
            "no parts": {"candidates": [{"finishReason": "SAFETY"}]},
            "empty text": {"candidates": [{"content": {"parts": [{"text": ""}]}}]},
        }
        for name, answer in cases.items():
            with (
                self.subTest(name),
                patch("llm.gemini.urllib.request.urlopen", return_value=_http_response(answer)),
                self.assertLogs("llm.base", level="WARNING"),
                self.assertRaises(LLMInvalidResponse),
            ):
                self.make_client().chat(HELLO)


class FactoryTests(SimpleTestCase):
    @override_settings(LLM_PROVIDER="offline")
    def test_offline_is_available_without_credentials(self):
        self.assertIsInstance(get_llm_client(), OfflineLLM)

    @override_settings(
        LLM_PROVIDER="gemini", LLM_API_KEY="k", LLM_MODEL="m",
        LLM_ENDPOINT="https://llm.example.invalid/x/{model}:generateContent",
    )
    def test_gemini_uses_the_configured_model_and_endpoint(self):
        client = get_llm_client()
        self.assertIsInstance(client, GeminiClient)
        self.assertEqual(client.model, "m")
        self.assertEqual(client._url, "https://llm.example.invalid/x/m:generateContent")

    @override_settings(LLM_PROVIDER="gemini", LLM_API_KEY="")
    def test_gemini_without_key_fails_clearly(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "LLM_API_KEY"):
            get_llm_client()

    @override_settings(LLM_PROVIDER="other")
    def test_unknown_provider_fails_clearly(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "other"):
            get_llm_client()


class OfflineLLMTests(SimpleTestCase):
    """The rule-based stand-in that lets the chat run without LLM access."""

    today = datetime.date(2026, 11, 15)

    def test_reads_the_example_sentence(self):
        result = extract(
            "Ich will am 20. Mai mit 2 Leuten von Berlin nach Lissabon, maximal 300 € pro Person",
            today=self.today,
        )
        self.assertEqual(result["origin"], "Berlin")
        self.assertEqual(result["destination"], "Lissabon")
        self.assertEqual(result["departure_earliest"], "2027-05-20")
        self.assertEqual(result["departure_latest"], "2027-05-20")
        self.assertEqual(result["travelers"], 2)
        self.assertEqual(result["budget_amount"], 300.0)
        self.assertEqual(result["budget_basis"], "per_person")
        self.assertIsNone(result["max_stops"])
        self.assertIsNone(result["return_earliest"])
        self.assertIsNone(result["return_latest"])
        self.assertIsNone(result["one_way"])
        self.assertEqual(result["cleared"], [])
        self.assertEqual(result["inferred"], [])
        self.assertEqual(result["confirmed"], [])
        self.assertEqual(result["intent"], "trip_info")

    def test_the_answer_has_every_key_of_the_extraction_schema(self):
        from agent.prompts import EXTRACTION_SCHEMA

        for text in ("", "hallo", "von Berlin nach Rom, zurück am 27. Mai, nur Hinflug"):
            with self.subTest(text):
                result = extract(text, today=self.today)
                self.assertEqual(set(result), set(EXTRACTION_SCHEMA["properties"]))
                self.assertIsInstance(result["cleared"], list)
                self.assertIn(result["one_way"], (None, True))

    def test_dates_after_a_return_word_are_the_return(self):
        out, back = "2027-05-20", "2027-05-27"
        cases = {
            "am 20. Mai nach Lissabon und zurück am 27. Mai": (out, out, back, back),
            "Hinflug am 20.05.2027, Rückflug am 27.05.2027": (out, out, back, back),
            "Hinflug 20.05.2027, Rückreise 27.05.2027": (out, out, back, back),
            "vom 20. Mai bis 27. Mai": (out, out, back, back),
            "vom 20. Mai bis zum 27. Mai": (out, out, back, back),
            "from Berlin to Lisbon on May 20, back on May 27": (out, out, back, back),
            "leaving May 20, return May 27": (out, out, back, back),
            "am 20. Mai, zurück zwischen 27. Mai und 30. Mai": (out, out, back, "2027-05-30"),
            "zurück am 27. Mai": (None, None, back, back),
            "am 20. Mai": (out, out, None, None),
            # "zwischen … und …" stays one departure window.
            "zwischen 20. Mai und 24. Mai": (out, "2027-05-24", None, None),
            "irgendwann zurück": (None, None, None, None),
        }
        for text, expected in cases.items():
            with self.subTest(text):
                result = extract(text, today=self.today)
                self.assertEqual(
                    (
                        result["departure_earliest"], result["departure_latest"],
                        result["return_earliest"], result["return_latest"],
                    ),
                    expected,
                )
                self.assertIsNone(result["one_way"])

    def test_a_return_date_before_the_return_word_is_the_return(self):
        # The usual German word order: "… und am 27. Mai zurück".
        result = extract(
            "Ich will am 20. Mai zu zweit von Berlin nach Lissabon und am 27. Mai zurück",
            today=self.today,
        )
        self.assertEqual(result["departure_earliest"], "2027-05-20")
        self.assertEqual(result["departure_latest"], "2027-05-20")
        self.assertEqual(result["return_earliest"], "2027-05-27")
        self.assertEqual(result["return_latest"], "2027-05-27")

    def test_the_round_trip_sentence_is_read_completely(self):
        result = extract(
            "Ich will am 20. Mai zu zweit von Berlin nach Lissabon und zurück am 27. Mai, "
            "maximal 400 € pro Person",
            today=self.today,
        )
        self.assertEqual(result["origin"], "Berlin")
        self.assertEqual(result["destination"], "Lissabon")
        self.assertEqual(result["departure_earliest"], "2027-05-20")
        self.assertEqual(result["departure_latest"], "2027-05-20")
        self.assertEqual(result["return_earliest"], "2027-05-27")
        self.assertEqual(result["return_latest"], "2027-05-27")
        self.assertEqual(result["travelers"], 2)
        self.assertEqual(result["budget_amount"], 400.0)
        self.assertIsNone(result["one_way"])

    def test_plain_dates_answer_the_question_for_the_return(self):
        cases = {
            "27.05.2027": ("2027-05-27", "2027-05-27"),
            "am 27. Mai": ("2027-05-27", "2027-05-27"),
            "zwischen 27. Mai und 30. Mai": ("2027-05-27", "2027-05-30"),
            "zurück am 27. Mai": ("2027-05-27", "2027-05-27"),
            "keine Ahnung": (None, None),
        }
        for text, (earliest, latest) in cases.items():
            with self.subTest(text):
                result = extract(text, today=self.today, asked="return")
                self.assertEqual(result["return_earliest"], earliest)
                self.assertEqual(result["return_latest"], latest)
                self.assertIsNone(result["departure_earliest"])
                self.assertIsNone(result["departure_latest"])
        # Asked for anything else, a plain date is the departure.
        for asked in ("departure", "travelers", "confirmation", None):
            with self.subTest(asked=asked):
                result = extract("27.05.2027", today=self.today, asked=asked)
                self.assertEqual(result["departure_earliest"], "2027-05-27")
                self.assertIsNone(result["return_earliest"])

    def test_one_way_wordings(self):
        for text in (
            "nur Hinflug", "Nur hin, bitte", "ohne Rückflug", "kein Rückflug nötig",
            "one way please", "a one-way ticket", "oneway",
        ):
            for asked in (None, "return"):
                with self.subTest(text, asked=asked):
                    result = extract(text, today=self.today, asked=asked)
                    self.assertIs(result["one_way"], True)
                    self.assertIsNone(result["return_earliest"])
                    self.assertIsNone(result["return_latest"])
        for text in ("mit Rückflug", "hin und zurück", "am 20. Mai", "danke"):
            with self.subTest(text):
                self.assertIsNone(extract(text, today=self.today)["one_way"])

    def test_one_way_keeps_the_departure_of_the_same_sentence(self):
        result = extract(
            "Ich will am 20. Mai zu zweit von Berlin nach Lissabon, nur Hinflug", today=self.today
        )
        self.assertEqual(result["departure_earliest"], "2027-05-20")
        self.assertEqual(result["departure_latest"], "2027-05-20")
        self.assertEqual(result["travelers"], 2)
        self.assertEqual(result["destination"], "Lissabon")

    def test_date_formats(self):
        cases = {
            "am 2027-05-20": ("2027-05-20", "2027-05-20"),
            "am 20.05.2027": ("2027-05-20", "2027-05-20"),
            "am 20.5.": ("2027-05-20", "2027-05-20"),
            "am 20.12.": ("2026-12-20", "2026-12-20"),
            "on May 20th, 2028": ("2028-05-20", "2028-05-20"),
            "zwischen 20. Mai und 24. Mai": ("2027-05-20", "2027-05-24"),
            "am 31.02.": (None, None),
            "irgendwann": (None, None),
        }
        for text, (earliest, latest) in cases.items():
            with self.subTest(text):
                result = extract(text, today=self.today)
                self.assertEqual(result["departure_earliest"], earliest)
                self.assertEqual(result["departure_latest"], latest)

    def test_people_budget_and_stops(self):
        cases = [
            ("wir sind zu dritt", "travelers", 3),
            ("ich reise alleine", "travelers", 1),
            ("für vier Personen", "travelers", 4),
            ("höchstens 450,50 Euro insgesamt", "budget_amount", 450.5),
            ("höchstens 450 Euro insgesamt", "budget_basis", "trip_total"),
            ("nur Direktflug bitte", "max_stops", 0),
            ("maximal 1 Umstieg", "max_stops", 1),
            ("höchstens zwei Stopps", "max_stops", 2),
        ]
        for text, field, expected in cases:
            with self.subTest(text):
                self.assertEqual(extract(text, today=self.today)[field], expected)

    def test_agreement_confirms_what_the_agent_asked_to_confirm(self):
        for text in ("ja", "Passt so!", "genau.", "ok"):
            with self.subTest(text):
                confirmed = extract(text, today=self.today)["confirmed"]
                self.assertIn("departure", confirmed)
                self.assertIn("return", confirmed)
                self.assertEqual(
                    set(confirmed), {"origin", "destination", "departure", "return", "travelers"}
                )
        self.assertEqual(extract("ja, aber am 20. Mai", today=self.today)["confirmed"], [])
        self.assertEqual(extract("ja, zurück am 27. Mai", today=self.today)["confirmed"], [])

    def test_a_bare_answer_belongs_to_the_asked_field(self):
        self.assertEqual(extract("Berlin", today=self.today, asked="origin")["origin"], "Berlin")
        self.assertEqual(
            extract("New York.", today=self.today, asked="destination")["destination"], "New York"
        )
        self.assertEqual(extract("2", today=self.today, asked="travelers")["travelers"], 2)
        self.assertEqual(extract("zwei", today=self.today, asked="travelers")["travelers"], 2)
        self.assertIsNone(extract("Berlin", today=self.today)["origin"])
        self.assertIsNone(extract("keine Ahnung, mal sehen was geht", today=self.today, asked="origin")["origin"])

    def test_chat_returns_the_fallback_and_structured_follows_the_schema(self):
        llm = OfflineLLM(today=self.today)
        with self.assertLogs("llm.base", level="INFO"):
            self.assertEqual(
                llm.chat([Message("user", "Ask for the destination.")], fallback="Wohin soll es gehen?"),
                "Wohin soll es gehen?",
            )
            # The fallback belongs to one call only.
            self.assertEqual(llm.chat([Message("user", "Hallo")]), "Hallo")
            strategy = llm.structured(
                [Message("user", "…")],
                schema={
                    "type": "object",
                    "properties": {"strategy": {"type": "string", "enum": ["b", "a"]}},
                    "required": ["strategy"],
                },
            )
            self.assertEqual(strategy, {"strategy": "b"})
            data = llm.structured(
                [Message("user", "Lissabon")],
                schema={"type": "object", "properties": {}, "required": []},
                system="x\nAsked field: destination\ny",
            )
        self.assertEqual(data["destination"], "Lissabon")

    def test_structured_reads_the_asked_return_from_the_system_prompt(self):
        llm = OfflineLLM(today=self.today)
        schema = {"type": "object", "properties": {}, "required": []}
        with self.assertLogs("llm.base", level="INFO"):
            asked = llm.structured(
                [Message("user", "27.05.2027")], schema=schema, system="x\nAsked field: return\ny"
            )
            not_asked = llm.structured(
                [Message("user", "27.05.2027")], schema=schema, system="x\nAsked field: none\ny"
            )
            one_way = llm.structured(
                [Message("user", "nur Hinflug")], schema=schema, system="x\nAsked field: return\ny"
            )
        self.assertEqual(asked["return_earliest"], "2027-05-27")
        self.assertEqual(asked["return_latest"], "2027-05-27")
        self.assertIsNone(asked["departure_earliest"])
        self.assertEqual(not_asked["departure_earliest"], "2027-05-27")
        self.assertIsNone(not_asked["return_earliest"])
        self.assertIs(one_way["one_way"], True)
