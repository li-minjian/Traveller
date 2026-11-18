"""Fake LLM with scripted answers, for tests. Without LLM access the app uses llm/offline.py."""

import json

from llm.base import Generation, LLMClient, LLMError, Message


class FakeLLM(LLMClient):
    """Answers from a script instead of calling a provider.

    `responses` are consumed in order, one per provider call. A string is
    returned as text, a dict as JSON text, an exception is raised. Every call
    is recorded in `calls` so tests can check what the agent sent.
    """

    model = "fake"

    def __init__(self, responses=(), *, max_attempts: int = 2):
        super().__init__(max_attempts=max_attempts, retry_delay_seconds=0)
        self._responses = list(responses)
        self.calls: list[dict] = []
        self._fallback = None

    def chat(self, messages, *, system=None, fallback=None):
        # Recorded with the call, so tests can check what the agent would say on its own.
        self._fallback = fallback
        try:
            return super().chat(messages, system=system)
        finally:
            self._fallback = None

    def _generate(
        self, messages: list[Message], system: str | None, schema: dict | None
    ) -> Generation:
        self.calls.append({
            "messages": list(messages), "system": system, "schema": schema,
            "fallback": self._fallback,
        })
        if not self._responses:
            # Not retryable: a missing script entry is a mistake in the test setup.
            raise LLMError("FakeLLM has no scripted response left for this call.")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, dict):
            response = json.dumps(response)
        return Generation(text=response, input_tokens=0, output_tokens=0)
