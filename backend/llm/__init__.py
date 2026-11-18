"""The single place in the backend that talks to an LLM.

    from llm import Message, get_llm_client

    client = get_llm_client()
    text = client.chat([Message("user", "Hello")], system="You are a travel agent.")
    data = client.structured([Message("user", "...")], schema={...})

Which provider answers is configuration (LLM_PROVIDER), see docs/DEVELOPMENT.md.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from llm.base import (
    LLMClient,
    LLMError,
    LLMInvalidResponse,
    LLMQuotaExceeded,
    LLMTimeout,
    LLMUnavailable,
    Message,
)
from llm.fake import FakeLLM

__all__ = [
    "FakeLLM",
    "LLMClient",
    "LLMError",
    "LLMInvalidResponse",
    "LLMQuotaExceeded",
    "LLMTimeout",
    "LLMUnavailable",
    "Message",
    "get_llm_client",
]


def get_llm_client() -> LLMClient:
    """Return the client for the configured provider."""
    provider = settings.LLM_PROVIDER
    if provider == "offline":
        from llm.offline import OfflineLLM

        return OfflineLLM()
    if provider == "gemini":
        if not settings.LLM_API_KEY:
            raise ImproperlyConfigured("LLM_PROVIDER=gemini requires LLM_API_KEY.")
        from llm.gemini import GeminiClient

        return GeminiClient(
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            endpoint=settings.LLM_ENDPOINT,
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            max_attempts=settings.LLM_MAX_ATTEMPTS,
        )
    raise ImproperlyConfigured(f"Unknown LLM_PROVIDER {provider!r}; use 'offline' or 'gemini'.")
