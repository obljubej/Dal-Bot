from __future__ import annotations

import json
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class GeminiPriceResult:
    new_price: float | None
    used_price: float | None
    currency: str
    confidence: str          # "high" | "medium" | "low"
    sources: list[str]
    notes: str


def _extract_json(text: str) -> dict:
    text = text.strip()
    # Strip markdown fences if present
    if "```" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            text = text[start:end]
    return json.loads(text)


async def fetch_prices_gemini(
    product_name: str,
    currency: str = "CAD",
) -> GeminiPriceResult | None:
    """
    Use Gemini with Google Search grounding to find current new and used
    market prices for a PC hardware product.
    """
    from partvault.config import settings

    if not settings.GEMINI_API_KEY:
        return None

    try:
        from google import genai
        from google.genai import types as gtypes
    except ImportError:
        log.warning("google-genai not installed — falling back to knowledge-based pricing.")
        return await _fetch_prices_openai_compat(product_name, currency)

    prompt = f"""Search the web for the current market price of: **{product_name}**

Currency: {currency}

Search eBay sold listings, Amazon, Newegg, and PC hardware resale communities.

Return ONLY a valid JSON object — no explanation, no markdown:
{{
  "new_price": <number or null>,
  "used_price": <number or null>,
  "currency": "{currency}",
  "confidence": "high" | "medium" | "low",
  "sources": ["site1", "site2"],
  "notes": "brief summary of findings"
}}

For used_price: prioritize recent completed/sold listings.
For new_price: use in-stock retail prices only.
Set confidence to "high" if 3+ matching listings found, "medium" for 1-2, "low" if estimated from related products.
Use null if no reliable data found for that price type."""

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=settings.AI_MODEL,
            contents=prompt,
            config=gtypes.GenerateContentConfig(
                tools=[gtypes.Tool(google_search=gtypes.GoogleSearch())],
                temperature=0.1,
            ),
        )
        text = response.text
    except Exception as exc:
        log.error("Gemini pricing request failed: %s", exc)
        return None

    try:
        data = _extract_json(text)
        return GeminiPriceResult(
            new_price=float(data["new_price"]) if data.get("new_price") else None,
            used_price=float(data["used_price"]) if data.get("used_price") else None,
            currency=data.get("currency", currency),
            confidence=data.get("confidence", "low"),
            sources=data.get("sources", []),
            notes=data.get("notes", ""),
        )
    except Exception as exc:
        log.error("Failed to parse Gemini price response: %s\n%s", exc, text)
        return None


async def _fetch_prices_openai_compat(
    product_name: str,
    currency: str,
) -> GeminiPriceResult | None:
    """
    Fallback: ask Gemini via OpenAI-compatible endpoint (no live search).
    Results are from training data — less accurate but still useful.
    """
    from partvault.ai import client as ai_client

    prompt = f"""Estimate the current market price for: {product_name}
Currency: {currency}

Return ONLY valid JSON:
{{
  "new_price": <number or null>,
  "used_price": <number or null>,
  "currency": "{currency}",
  "confidence": "low",
  "sources": ["AI knowledge estimate"],
  "notes": "Based on training data — not live prices"
}}"""

    response = ai_client.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=200,
        json_mode=True,
    )
    if not response:
        return None

    try:
        data = _extract_json(response)
        return GeminiPriceResult(
            new_price=float(data["new_price"]) if data.get("new_price") else None,
            used_price=float(data["used_price"]) if data.get("used_price") else None,
            currency=data.get("currency", currency),
            confidence="low",
            sources=["AI knowledge estimate"],
            notes=data.get("notes", "Not from live search"),
        )
    except Exception as exc:
        log.error("Failed to parse fallback price response: %s", exc)
        return None
