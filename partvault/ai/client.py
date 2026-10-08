from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# Lazy import so the bot starts even without the openai package installed
_openai_client = None


def _get_client():
    global _openai_client
    if _openai_client is not None:
        return _openai_client

    from partvault.config import settings

    if not settings.GEMINI_API_KEY:
        return None

    try:
        from openai import OpenAI

        _openai_client = OpenAI(
            api_key=settings.GEMINI_API_KEY,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        return _openai_client
    except ImportError:
        log.warning("openai package not installed — AI features disabled.")
        return None


def is_available() -> bool:
    from partvault.config import settings
    return bool(settings.GEMINI_API_KEY)


def chat(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    json_mode: bool = False,
) -> str | None:
    """
    Send a chat request to Gemini (via OpenAI-compatible API).
    Returns the response text, or None on failure.
    """
    client = _get_client()
    if client is None:
        return None

    from partvault.config import settings

    effective_model = model or settings.AI_MODEL

    kwargs: dict[str, Any] = {
        "model": effective_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
    except Exception as exc:
        log.error("AI request failed: %s", exc)
        return None
