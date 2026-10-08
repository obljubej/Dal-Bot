from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from partvault.ai import client as ai_client
from partvault.ai.prompts import IDENTIFIER_SYSTEM, INTERPRETER_SYSTEM

log = logging.getLogger(__name__)


@dataclass
class ParsedOperation:
    action: str                        # "add" | "remove" | "unclear"
    quantity: int
    product_query: str | None
    condition: str                     # "new" | "used" | "refurbished" | "broken"
    requires_clarification: bool
    clarification_question: str | None


@dataclass
class IdentifiedProduct:
    manufacturer: str | None
    model: str
    category: str
    confidence: str                    # "high" | "medium" | "low"
    normalized_name: str


def interpret_command(text: str) -> ParsedOperation | None:
    """
    Use AI to parse a free-form user message into a structured inventory operation.
    Returns None if AI is unavailable or the response cannot be parsed.
    """
    response = ai_client.chat(
        messages=[
            {"role": "system", "content": INTERPRETER_SYSTEM},
            {"role": "user", "content": text},
        ],
        temperature=0.1,
        max_tokens=256,
        json_mode=True,
    )
    if not response:
        return None

    try:
        data = _extract_json(response)
        return ParsedOperation(
            action=data.get("action", "unclear"),
            quantity=int(data.get("quantity", 1)),
            product_query=data.get("product_query") or None,
            condition=data.get("condition", "used"),
            requires_clarification=bool(data.get("requires_clarification", False)),
            clarification_question=data.get("clarification_question") or None,
        )
    except Exception as exc:
        log.error("Failed to parse interpreter response: %s\n%s", exc, response)
        return None


def identify_product(query: str) -> IdentifiedProduct | None:
    """
    Use AI to normalize a short product description into a full, structured product name.
    Returns None if AI is unavailable.
    """
    response = ai_client.chat(
        messages=[
            {"role": "system", "content": IDENTIFIER_SYSTEM},
            {"role": "user", "content": query},
        ],
        temperature=0.1,
        max_tokens=200,
        json_mode=True,
    )
    if not response:
        return None

    try:
        data = _extract_json(response)
        return IdentifiedProduct(
            manufacturer=data.get("manufacturer") or None,
            model=data.get("model", query),
            category=data.get("category", "misc"),
            confidence=data.get("confidence", "low"),
            normalized_name=data.get("normalized_name", query),
        )
    except Exception as exc:
        log.error("Failed to parse identifier response: %s\n%s", exc, response)
        return None


def _extract_json(text: str) -> dict:
    """Extract JSON from a string that may have surrounding markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    return json.loads(text)
