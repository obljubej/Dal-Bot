from __future__ import annotations

from datetime import timezone

import discord

from partvault.inventory.models import InventoryItem, InventoryTransaction, Product
from partvault.inventory.service import InventoryResult, InventorySummary

COLOUR_GREEN = discord.Colour.from_rgb(87, 242, 135)
COLOUR_RED = discord.Colour.from_rgb(237, 66, 69)
COLOUR_BLUE = discord.Colour.from_rgb(88, 101, 242)
COLOUR_YELLOW = discord.Colour.from_rgb(254, 231, 92)
COLOUR_GREY = discord.Colour.from_rgb(153, 170, 181)


def _condition_label(condition: str) -> str:
    return condition.capitalize()


def embed_add_success(item: InventoryItem, product: Product, quantity_added: int) -> discord.Embed:
    embed = discord.Embed(
        title="✅ Inventory Updated",
        colour=COLOUR_GREEN,
    )
    embed.add_field(name="Product", value=product.display_name, inline=False)
    embed.add_field(name="Category", value=product.category.name, inline=True)
    embed.add_field(name="Condition", value=_condition_label(item.condition), inline=True)
    embed.add_field(name="Added", value=f"+{quantity_added}", inline=True)
    embed.add_field(name="Total Owned", value=str(item.quantity), inline=True)
    embed.add_field(name="Estimated Used Price", value="Not yet retrieved", inline=True)
    return embed


def embed_remove_success(item: InventoryItem, product: Product, quantity_removed: int) -> discord.Embed:
    embed = discord.Embed(
        title="✅ Inventory Updated",
        colour=COLOUR_GREEN,
    )
    embed.add_field(name="Product", value=product.display_name, inline=False)
    embed.add_field(name="Category", value=product.category.name, inline=True)
    embed.add_field(name="Condition", value=_condition_label(item.condition), inline=True)
    embed.add_field(name="Removed", value=f"-{quantity_removed}", inline=True)
    embed.add_field(name="Total Owned", value=str(item.quantity), inline=True)
    return embed


def embed_error(message: str) -> discord.Embed:
    return discord.Embed(title="❌ Error", description=message, colour=COLOUR_RED)


def embed_warning(message: str) -> discord.Embed:
    return discord.Embed(title="⚠️ Warning", description=message, colour=COLOUR_YELLOW)


def embed_info(title: str, message: str) -> discord.Embed:
    return discord.Embed(title=title, description=message, colour=COLOUR_BLUE)


def embed_product_not_found(query: str) -> discord.Embed:
    embed = discord.Embed(
        title="❓ Product Not Found",
        colour=COLOUR_YELLOW,
    )
    embed.description = (
        f"Could not identify **{query}** in the product catalog.\n\n"
        "Use `/inventory add` with more detail, or `/product create` to add a new product."
    )
    return embed


def embed_inventory_list(results: list[InventoryResult], title: str = "Inventory") -> discord.Embed:
    embed = discord.Embed(title=f"📦 {title}", colour=COLOUR_BLUE)

    if not results:
        embed.description = "No inventory items found."
        return embed

    # Group by category
    by_category: dict[str, list[InventoryResult]] = {}
    for r in results:
        cat_name = r.category.name
        by_category.setdefault(cat_name, []).append(r)

    for cat_name, items in by_category.items():
        lines = []
        for r in items:
            cond = f"[{_condition_label(r.item.condition)}]"
            lines.append(f"`×{r.item.quantity}` {r.product.display_name} {cond}")
        # Discord field value limit = 1024 chars; truncate if needed
        value = "\n".join(lines)
        if len(value) > 1020:
            value = value[:1020] + "…"
        embed.add_field(name=cat_name, value=value, inline=False)

    return embed


def embed_summary(summary: InventorySummary) -> discord.Embed:
    embed = discord.Embed(title="📊 Inventory Summary", colour=COLOUR_BLUE)
    embed.add_field(name="Total Components", value=str(summary.total_components), inline=True)
    embed.add_field(name="Unique Products", value=str(summary.unique_products), inline=True)
    embed.add_field(name="Estimated Value", value="N/A (Phase 3)", inline=True)

    # Category breakdown
    by_category: dict[str, int] = {}
    for r in summary.items:
        cat = r.category.name
        by_category[cat] = by_category.get(cat, 0) + r.item.quantity

    if by_category:
        lines = [f"**{cat}:** {qty}" for cat, qty in sorted(by_category.items())]
        embed.add_field(name="By Category", value="\n".join(lines), inline=False)

    return embed


def embed_match_candidate(
    query: str,
    product: Product,
    score: float,
    matched_via: str,
) -> discord.Embed:
    embed = discord.Embed(
        title="🔍 Product Match",
        colour=COLOUR_YELLOW,
    )
    embed.add_field(name="Query", value=query, inline=False)
    embed.add_field(name="Matched Product", value=product.display_name, inline=True)
    embed.add_field(name="Category", value=product.category.name, inline=True)
    embed.add_field(name="Match Score", value=f"{score:.0f}%", inline=True)
    embed.add_field(name="Method", value=matched_via, inline=True)
    embed.set_footer(text="React ✅ to confirm or ❌ to cancel.")
    return embed


def embed_transaction_history(
    transactions: list[InventoryTransaction],
) -> discord.Embed:
    embed = discord.Embed(title="📋 Transaction History", colour=COLOUR_GREY)

    if not transactions:
        embed.description = "No transactions recorded."
        return embed

    lines = []
    for tx in transactions:
        ts = tx.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        date_str = ts.strftime("%Y-%m-%d %H:%M")
        sign = "+" if tx.quantity_change >= 0 else ""
        lines.append(
            f"`{date_str}` **{tx.action.upper()}** {sign}{tx.quantity_change} "
            f"(item #{tx.inventory_item_id})"
        )

    embed.description = "\n".join(lines[:20])
    return embed
