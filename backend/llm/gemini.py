"""Gemini over its REST API, authenticated with an API key.

The default address is the Gemini platform of Google Cloud (Agent Platform,
formerly Vertex AI). Its API keys belong to a service account of the Cloud
project; that account needs the role "Agent Platform User". The Gemini API of
AI Studio takes the same request at a different address, see LLM_ENDPOINT in
docs/DEVELOPMENT.md.

Uses only the standard library, so no extra dependency is needed.
"""

import json
import socket
import urllib.error
import urllib.request

from llm.base import (
    Generation,
    LLMClient,
    LLMError,
    LLMInvalidResponse,
    LLMQuotaExceeded,
    LLMTimeout,
    LLMUnavailable,
    Message,
)

_ROLES = {"user": "user", "assistant": "model"}


class GeminiClient(LLMClient):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        endpoint: str,
        timeout_seconds: float,
        max_attempts: int = 2,
    ):
        super().__init__(max_attempts=max_attempts)
        self.model = model
        self._api_key = api_key
        # `endpoint` is a URL with the placeholder {model}.
        self._url = endpoint.replace("{model}", model)
        self._timeout = timeout_seconds

    def _generate(
        self, messages: list[Message], system: str | None, schema: dict | None
    ) -> Generation:
        body: dict = {
            "contents": [
                {"role": _ROLES[message.role], "parts": [{"text": message.content}]}
                for message in messages
            ]
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if schema is not None:
            body["generationConfig"] = {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
                # Reading data should give the same result every time.
                "temperature": 0,
            }
        return _read_generation(self._post(body))

    def _post(self, body: dict) -> dict:
        request = urllib.request.Request(
            self._url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self._api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = response.read()
        except urllib.error.HTTPError as error:
            # The error body is not passed on: it may echo parts of the request.
            if error.code == 429:
                raise LLMQuotaExceeded("The LLM provider reported exhausted quota.") from None
            if error.code in (408, 504):
                raise LLMTimeout("The LLM provider timed out.") from None
            if error.code >= 500:
                raise LLMUnavailable(f"The LLM provider answered with {error.code}.") from None
            raise LLMError(
                f"The LLM provider rejected the request with {error.code}. "
                "Check LLM_API_KEY and LLM_MODEL."
            ) from None
        except (TimeoutError, socket.timeout):
            raise LLMTimeout("The LLM provider did not answer in time.") from None
        except urllib.error.URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise LLMTimeout("The LLM provider did not answer in time.") from None
            raise LLMUnavailable("The LLM provider could not be reached.") from None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            raise LLMInvalidResponse("The LLM provider did not answer with JSON.") from None


def _read_generation(payload: dict) -> Generation:
    try:
        parts = payload["candidates"][0]["content"]["parts"]
        text = "".join(part.get("text", "") for part in parts)
    except (KeyError, IndexError, TypeError, AttributeError):
        # Also the case when the prompt or the answer was blocked.
        raise LLMInvalidResponse("The LLM provider returned no candidate text.") from None
    usage = payload.get("usageMetadata") or {}
    return Generation(
        text=text,
        input_tokens=usage.get("promptTokenCount"),
        output_tokens=usage.get("candidatesTokenCount"),
    )
