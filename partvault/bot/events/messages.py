from __future__ import annotations

import logging

import discord
from discord.ext import commands

from partvault.ai import client as ai_client
from partvault.ai.interpreter import identify_product, interpret_command
from partvault.bot.ui.embeds import (
    embed_add_success,
    embed_error,
    embed_info,
    embed_inventory_list,
    embed_match_candidate,
    embed_product_not_found,
    embed_remove_success,
    embed_summary,
    embed_warning,
)
from partvault.config import settings
from partvault.dashboard.generator import export_dashboard
from partvault.database.connection import get_session
from partvault.inventory import service
from partvault.inventory.matcher import find_product, infer_category, parse_quick_command
from partvault.inventory.models import Category, Condition
from partvault.inventory.service import add_alias, create_product

log = logging.getLogger(__name__)


def _refresh_dashboard() -> None:
    try:
        export_dashboard()
    except Exception as exc:
        log.error("Dashboard export failed: %s", exc)

# Pending reaction-confirmation state: prompt_message_id → operation dict
_pending: dict[int, dict] = {}

_CONFIRM_EMOJI = "✅"
_CANCEL_EMOJI = "❌"

_CONDITION_MAP = {
    "new": Condition.NEW,
    "used": Condition.USED,
    "refurbished": Condition.REFURBISHED,
    "broken": Condition.BROKEN,
}


def _is_inventory_channel(channel_id: int) -> bool:
    return bool(settings.INVENTORY_CHANNEL_IDS) and channel_id in settings.INVENTORY_CHANNEL_IDS


def _is_authorized(user_id: int) -> bool:
    return not settings.AUTHORIZED_USER_IDS or user_id in settings.AUTHORIZED_USER_IDS


class MessageEventsCog(commands.Cog, name="MessageEvents"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not _is_inventory_channel(message.channel.id):
            return

        content = message.content.strip()
        lower = content.lower()

        # --- Keyword shortcuts ---
        if lower in ("inventory", "inv"):
            with get_session() as session:
                results = service.get_inventory(session)
            await message.channel.send(embed=embed_inventory_list(results))
            return

        if lower == "summary":
            with get_session() as session:
                summary = service.get_inventory_summary(session)
            await message.channel.send(embed=embed_summary(summary))
            return

        # --- Quick commands: +4 9070xt / -2 rtx 4090 ---
        parsed = parse_quick_command(content)
        if parsed is not None:
            if not _is_authorized(message.author.id):
                await message.channel.send(
                    embed=embed_error("You are not authorized to modify inventory."),
                    delete_after=8,
                )
                return
            await _handle_quick_command(
                channel=message.channel,
                action=parsed.action,
                quantity=parsed.quantity,
                product_query=parsed.product_query,
                condition=_CONDITION_MAP.get(parsed.condition, Condition.USED),
                user_id=message.author.id,
                original_query=parsed.product_query,
            )
            return

        # --- Free-form natural language (AI only) ---
        if settings.AI_ENABLED and ai_client.is_available():
            await _handle_freeform(message, content)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.user_id == self.bot.user.id:
            return

        pending = _pending.get(payload.message_id)
        if pending is None:
            return
        if payload.user_id != pending["requestor_id"]:
            return

        emoji = str(payload.emoji)
        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            return

        _pending.pop(payload.message_id, None)

        if emoji == _CANCEL_EMOJI:
            await channel.send(embed=embed_warning("Operation cancelled."), delete_after=6)
            return

        if emoji != _CONFIRM_EMOJI:
            return

        with get_session() as session:
            if "product_id" in pending:
                from partvault.inventory.models import Product
                product = session.query(Product).filter_by(id=pending["product_id"]).first()
                # Learn alias from original query so future hits are instant
                if product and pending.get("original_query"):
                    add_alias(session, product, pending["original_query"])
            else:
                cat = session.query(Category).filter_by(
                    slug=pending.get("cat_slug", "misc")
                ).first()
                product = create_product(
                    session=session,
                    category=cat,
                    manufacturer=pending.get("manufacturer"),
                    model=pending["model"],
                    aliases=[pending["original_query"]] if pending.get("original_query") else [],
                )

            if product is None:
                await channel.send(embed=embed_error("Product could not be resolved."))
                return

            await _run_op(
                channel=channel,
                action=pending["action"],
                product=product,
                quantity=pending["quantity"],
                condition=pending["condition"],
                discord_user_id=str(pending["requestor_id"]),
                session=session,
            )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def _handle_quick_command(
    channel: discord.abc.Messageable,
    action: str,
    quantity: int,
    product_query: str,
    condition: Condition,
    user_id: int,
    original_query: str,
) -> None:
    with get_session() as session:
        match = find_product(session, product_query, threshold=settings.FUZZY_MATCH_THRESHOLD)

        if match and (match.score >= 90 or match.matched_via == "alias_exact"):
            # High-confidence — execute immediately
            await _run_op(channel, action, match.product, quantity, condition, str(user_id), session)
            return

        if match and match.score >= settings.FUZZY_MATCH_THRESHOLD:
            # Medium-confidence — ask to confirm
            prompt = await channel.send(embed=embed_match_candidate(
                original_query, match.product, match.score, match.matched_via
            ))
            await prompt.add_reaction(_CONFIRM_EMOJI)
            await prompt.add_reaction(_CANCEL_EMOJI)
            _pending[prompt.id] = {
                "action": action,
                "quantity": quantity,
                "product_id": match.product.id,
                "condition": condition,
                "requestor_id": user_id,
                "original_query": original_query,
            }
            return

        # No fuzzy match — try AI identification
        if settings.AI_ENABLED and ai_client.is_available():
            identified = identify_product(product_query)
        else:
            identified = None

        if identified and identified.confidence in ("high", "medium"):
            # AI identified something — check if it matches an existing product
            ai_match = find_product(session, identified.normalized_name, threshold=80)
            if ai_match:
                prompt = await channel.send(embed=embed_match_candidate(
                    original_query, ai_match.product, ai_match.score,
                    f"ai ({identified.confidence})"
                ))
                await prompt.add_reaction(_CONFIRM_EMOJI)
                await prompt.add_reaction(_CANCEL_EMOJI)
                _pending[prompt.id] = {
                    "action": action,
                    "quantity": quantity,
                    "product_id": ai_match.product.id,
                    "condition": condition,
                    "requestor_id": user_id,
                    "original_query": original_query,
                }
                return

            # AI identified a product not in catalog — offer to create it
            cat = session.query(Category).filter_by(slug=identified.category).first()
            if cat is None:
                cat = session.query(Category).filter_by(slug="misc").first()

            prompt = await channel.send(embed=embed_warning(
                f"**{original_query}** not in catalog.\n\n"
                f"AI identified: **{identified.normalized_name}** ({cat.name})\n\n"
                f"React {_CONFIRM_EMOJI} to add as a new product, or {_CANCEL_EMOJI} to cancel."
            ))
            await prompt.add_reaction(_CONFIRM_EMOJI)
            await prompt.add_reaction(_CANCEL_EMOJI)
            _pending[prompt.id] = {
                "action": action,
                "quantity": quantity,
                "manufacturer": identified.manufacturer,
                "model": identified.model,
                "cat_slug": identified.category,
                "condition": condition,
                "requestor_id": user_id,
                "original_query": original_query,
            }
            return

        # No match at all
        await channel.send(embed=embed_product_not_found(original_query))


async def _handle_freeform(message: discord.Message, content: str) -> None:
    """Handle a free-form natural-language message using AI interpretation."""
    operation = interpret_command(content)
    if operation is None or operation.action == "unclear":
        return  # Not an inventory command — ignore silently

    if not _is_authorized(message.author.id):
        await message.channel.send(
            embed=embed_error("You are not authorized to modify inventory."), delete_after=8
        )
        return

    if operation.requires_clarification and operation.clarification_question:
        await message.channel.send(embed=embed_warning(
            f"**Clarification needed:**\n{operation.clarification_question}"
        ))
        return

    if not operation.product_query:
        await message.channel.send(embed=embed_error("Could not determine the product from your message."))
        return

    condition = _CONDITION_MAP.get(operation.condition, Condition.USED)
    await _handle_quick_command(
        channel=message.channel,
        action=operation.action,
        quantity=operation.quantity,
        product_query=operation.product_query,
        condition=condition,
        user_id=message.author.id,
        original_query=content,
    )


async def _run_op(channel, action, product, quantity, condition, discord_user_id, session):
    try:
        if action == "add":
            item = service.add_inventory(
                session=session,
                product=product,
                quantity=quantity,
                condition=condition,
                discord_user_id=discord_user_id,
            )
            _refresh_dashboard()
            await channel.send(embed=embed_add_success(item, product, quantity))
        else:
            item = service.remove_inventory(
                session=session,
                product=product,
                quantity=quantity,
                condition=condition,
                discord_user_id=discord_user_id,
            )
            _refresh_dashboard()
            await channel.send(embed=embed_remove_success(item, product, quantity))
    except ValueError as exc:
        await channel.send(embed=embed_error(str(exc)))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MessageEventsCog(bot))
