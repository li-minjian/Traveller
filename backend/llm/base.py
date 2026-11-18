"""Shared interface for every LLM call in the backend.

Providers implement `_generate`; retries, logging and the check of structured
output live here so that the real client and the fake behave the same.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base class; also raised directly for errors that retrying cannot fix."""


class LLMTimeout(LLMError):
    """The provider did not answer within the configured timeout."""


class LLMQuotaExceeded(LLMError):
    """The provider rejected the call because of quota or rate limits."""


class LLMUnavailable(LLMError):
    """The provider could not be reached or answered with a server error."""


class LLMInvalidResponse(LLMError):
    """The provider answered, but not with usable content."""


# Quota errors are not retried: a second call costs quota as well.
_RETRYABLE = (LLMTimeout, LLMUnavailable, LLMInvalidResponse)


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class Generation:
    """Raw provider result. Token counts are None when the provider omits them."""

    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMClient:
    """Base class of all LLM clients. Use `chat` and `structured`."""

    model = "unknown"

    def __init__(self, *, max_attempts: int = 2, retry_delay_seconds: float = 0.5):
        self.max_attempts = max(1, max_attempts)
        self.retry_delay_seconds = retry_delay_seconds

    def chat(
        self, messages: list[Message], *, system: str | None = None, fallback: str | None = None
    ) -> str:
        """Return the model's text answer to the conversation.

        `fallback` is the answer the caller would give without an LLM. Real
        clients ignore it; the offline stand-in returns it unchanged.
        """
        return self._call(messages, system, schema=None, parse=_parse_text)

    def structured(
        self, messages: list[Message], *, schema: dict, system: str | None = None
    ) -> dict:
        """Return a JSON object that follows `schema` (a JSON Schema object).

        Only the shape is checked here: the answer is a JSON object and holds
        every key the schema requires. Callers validate the values themselves.
        """
        return self._call(
            messages, system, schema=schema, parse=lambda text: _parse_object(text, schema)
        )

    def _generate(
        self, messages: list[Message], system: str | None, schema: dict | None
    ) -> Generation:
        raise NotImplementedError

    def _call(self, messages, system, *, schema, parse):
        kind = "structured" if schema is not None else "chat"
        for attempt in range(1, self.max_attempts + 1):
            started = time.monotonic()
            try:
                generation = self._generate(messages, system, schema)
                result = parse(generation.text)
            except LLMError as error:
                self._log(kind, attempt, started, error=error)
                if not isinstance(error, _RETRYABLE) or attempt == self.max_attempts:
                    raise
                time.sleep(self.retry_delay_seconds)
            else:
                self._log(kind, attempt, started, generation=generation)
                return result
        raise AssertionError("unreachable")

    def _log(self, kind, attempt, started, *, generation=None, error=None):
        # Never log prompts, answers or credentials: only metadata.
        duration_ms = round((time.monotonic() - started) * 1000)
        if error is not None:
            logger.warning(
                "LLM call failed: model=%s kind=%s attempt=%d duration_ms=%d error=%s",
                self.model, kind, attempt, duration_ms, type(error).__name__,
            )
        else:
            logger.info(
                "LLM call: model=%s kind=%s attempt=%d duration_ms=%d "
                "input_tokens=%s output_tokens=%s",
                self.model, kind, attempt, duration_ms,
                generation.input_tokens, generation.output_tokens,
            )


def _parse_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise LLMInvalidResponse("The model returned no text.")
    return text.strip()


def _parse_object(text: str, schema: dict) -> dict:
    try:
        value = json.loads(_parse_text(text))
    except json.JSONDecodeError as error:
        raise LLMInvalidResponse("The model did not return valid JSON.") from error
    if not isinstance(value, dict):
        raise LLMInvalidResponse("The model did not return a JSON object.")
    missing = [key for key in schema.get("required", []) if key not in value]
    if missing:
        raise LLMInvalidResponse(f"The model's answer lacks required keys: {missing}.")
    return value
