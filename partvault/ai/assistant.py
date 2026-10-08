from __future__ import annotations

import logging

from partvault.ai import client as ai_client
from partvault.ai.prompts import ASSISTANT_SYSTEM
from partvault.inventory.service import InventoryResult

log = logging.getLogger(__name__)


def build_inventory_context(results: list[InventoryResult]) -> str:
    """Build a compact text snapshot of the inventory for the AI."""
    if not results:
        return "The inventory is empty."

    lines: list[str] = ["Current inventory:"]
    by_category: dict[str, list[str]] = {}

    for r in results:
        cat = r.category.name
        price_info = ""
        if r.item.purchase_price is not None:
            price_info = f", purchased at ${r.item.purchase_price:.2f}"
        entry = (
            f"  - {r.product.display_name} | qty: {r.item.quantity} | "
            f"condition: {r.item.condition}{price_info}"
        )
        by_category.setdefault(cat, []).append(entry)

    for cat, items in sorted(by_category.items()):
        lines.append(f"\n{cat}:")
        lines.extend(items)

    return "\n".join(lines)


def answer_question(question: str, inventory_context: str) -> str | None:
    """
    Answer a natural-language question about the user's inventory.
    Uses only the provided inventory_context — never invents data.
    Returns None if AI is unavailable.
    """
    user_message = f"{inventory_context}\n\nQuestion: {question}"

    response = ai_client.chat(
        messages=[
            {"role": "system", "content": ASSISTANT_SYSTEM},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
        max_tokens=512,
    )
    return response
