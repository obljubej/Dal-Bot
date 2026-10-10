from __future__ import annotations

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands

from partvault.ai import client as ai_client
from partvault.ai.assistant import answer_question, build_inventory_context
from partvault.bot.ui.embeds import (
    embed_add_success,
    embed_error,
    embed_info,
    embed_inventory_list,
    embed_match_candidate,
    embed_product_not_found,
    embed_remove_success,
    embed_summary,
    embed_transaction_history,
    embed_warning,
)
from partvault.config import settings
from partvault.dashboard.generator import export_dashboard
from partvault.database.connection import get_session
from partvault.inventory import service
from partvault.inventory.matcher import find_product, infer_category
from partvault.inventory.models import Category, Condition, Product
from partvault.inventory.service import create_product


log = logging.getLogger(__name__)


def _refresh_dashboard() -> None:
    try:
        export_dashboard()
    except Exception as exc:
        log.error("Dashboard export failed: %s", exc)


def _is_authorized(interaction: discord.Interaction) -> bool:
    if not settings.AUTHORIZED_USER_IDS:
        return True  # Open access when no list configured
    return interaction.user.id in settings.AUTHORIZED_USER_IDS


async def _require_auth(interaction: discord.Interaction) -> bool:
    if not _is_authorized(interaction):
        try:
            await interaction.response.send_message(
                embed=embed_error("You are not authorized to modify inventory."),
                ephemeral=True,
            )
        except discord.NotFound:
            log.warning("Interaction expired before auth response could be sent")
        return False
    return True


async def _defer_interaction(interaction: discord.Interaction) -> bool:
    """Defer an interaction without crashing if Discord already expired it."""
    try:
        await interaction.response.defer()
        return True
    except discord.NotFound:
        log.warning("Interaction expired before it could be deferred")
        return False


class InventoryCog(commands.Cog, name="Inventory"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /inventory
    # ------------------------------------------------------------------

    inventory_group = app_commands.Group(name="inventory", description="Manage your hardware inventory")

    @inventory_group.command(name="list", description="List all inventory items")
    @app_commands.describe(
        category="Filter by hardware category (gpu, cpu, ram, storage, …)",
        search="Search by product name",
    )
    async def inventory_list(
        self,
        interaction: discord.Interaction,
        category: str | None = None,
        search: str | None = None,
    ) -> None:
        with get_session() as session:
            results = service.get_inventory(session, category_slug=category, search=search)
        title = "Inventory"
        if category:
            title += f" — {category.upper()}"
        if search:
            title += f" — search: {search}"
        embed = embed_inventory_list(results, title=title)
        await interaction.response.send_message(embed=embed)

    @inventory_group.command(name="summary", description="Show inventory summary and totals")
    async def inventory_summary(self, interaction: discord.Interaction) -> None:
        with get_session() as session:
            summary = service.get_inventory_summary(session)
        await interaction.response.send_message(embed=embed_summary(summary))

    @inventory_group.command(name="add", description="Add components to inventory")
    @app_commands.describe(
        product="Product name or description",
        quantity="Number of units to add",
        condition="Condition: new, used, refurbished, broken",
        purchase_price="Purchase price per unit (optional)",
        notes="Additional notes (optional)",
    )
    async def inventory_add(
        self,
        interaction: discord.Interaction,
        product: str,
        quantity: int = 1,
        condition: str = "used",
        purchase_price: float | None = None,
        notes: str | None = None,
    ) -> None:
        if not await _require_auth(interaction):
            return

        if quantity <= 0:
            await interaction.response.send_message(
                embed=embed_error("Quantity must be a positive number."), ephemeral=True
            )
            return

        condition_value = _parse_condition(condition)
        if condition_value is None:
            await interaction.response.send_message(
                embed=embed_error(f"Invalid condition '{condition}'. Use: new, used, refurbished, broken."),
                ephemeral=True,
            )
            return

        if not await _defer_interaction(interaction):
            return

        with get_session() as session:
            match = find_product(session, product)

            if match is None:
                # Create a new unrecognized product under "Miscellaneous"
                misc_cat = session.query(Category).filter_by(slug="misc").first()
                new_product = create_product(
                    session=session,
                    category=misc_cat,
                    manufacturer=None,
                    model=product.strip(),
                    aliases=[product.strip().lower()],
                )
                item = service.add_inventory(
                    session=session,
                    product=new_product,
                    quantity=quantity,
                    condition=condition_value,
                    purchase_price=purchase_price,
                    notes=notes,
                    discord_user_id=str(interaction.user.id),
                )
                embed = embed_add_success(item, new_product, quantity)
                embed.set_footer(text="⚠️ Product not recognized — added as Miscellaneous. Use /product alias to link it.")
                _refresh_dashboard()
                await interaction.followup.send(embed=embed)
            else:
                item = service.add_inventory(
                    session=session,
                    product=match.product,
                    quantity=quantity,
                    condition=condition_value,
                    purchase_price=purchase_price,
                    notes=notes,
                    discord_user_id=str(interaction.user.id),
                )
                _refresh_dashboard()
                await interaction.followup.send(embed=embed_add_success(item, match.product, quantity))

    @inventory_group.command(name="remove", description="Remove components from inventory")
    @app_commands.describe(
        product="Product name or description",
        quantity="Number of units to remove",
        condition="Condition: new, used, refurbished, broken",
    )
    async def inventory_remove(
        self,
        interaction: discord.Interaction,
        product: str,
        quantity: int = 1,
        condition: str = "used",
    ) -> None:
        if not await _require_auth(interaction):
            return

        if quantity <= 0:
            await interaction.response.send_message(
                embed=embed_error("Quantity must be a positive number."), ephemeral=True
            )
            return

        condition_value = _parse_condition(condition)
        if condition_value is None:
            await interaction.response.send_message(
                embed=embed_error(f"Invalid condition '{condition}'."), ephemeral=True
            )
            return

        if not await _defer_interaction(interaction):
            return

        with get_session() as session:
            match = find_product(session, product)
            if match is None:
                await interaction.followup.send(embed=embed_product_not_found(product))
                return

            try:
                item = service.remove_inventory(
                    session=session,
                    product=match.product,
                    quantity=quantity,
                    condition=condition_value,
                    discord_user_id=str(interaction.user.id),
                )
                _refresh_dashboard()
                await interaction.followup.send(embed=embed_remove_success(item, match.product, quantity))
            except ValueError as exc:
                await interaction.followup.send(embed=embed_error(str(exc)))

    @inventory_group.command(name="history", description="Show recent transaction history")
    @app_commands.describe(product="Product name (optional — shows all if omitted)")
    async def inventory_history(
        self,
        interaction: discord.Interaction,
        product: str | None = None,
    ) -> None:
        with get_session() as session:
            product_id: int | None = None
            if product:
                match = find_product(session, product)
                if match is None:
                    await interaction.response.send_message(
                        embed=embed_product_not_found(product), ephemeral=True
                    )
                    return
                product_id = match.product.id

            txs = service.get_transaction_history(session, limit=20, product_id=product_id)

        await interaction.response.send_message(embed=embed_transaction_history(txs))

    # ------------------------------------------------------------------
    # /product
    # ------------------------------------------------------------------

    product_group = app_commands.Group(name="product", description="Manage product catalog")

    @product_group.command(name="alias", description="Add an alias for a product")
    @app_commands.describe(
        product="Product name to add alias for",
        alias="Short alias to link to this product",
    )
    async def product_alias(
        self,
        interaction: discord.Interaction,
        product: str,
        alias: str,
    ) -> None:
        if not await _require_auth(interaction):
            return

        with get_session() as session:
            match = find_product(session, product)
            if match is None:
                await interaction.response.send_message(
                    embed=embed_product_not_found(product), ephemeral=True
                )
                return

            result = service.add_alias(session, match.product, alias)
            if result is None:
                await interaction.response.send_message(
                    embed=embed_warning(f"Alias **{alias}** already exists."), ephemeral=True
                )
                return

            _refresh_dashboard()
            await interaction.response.send_message(
                embed=embed_info(
                    "✅ Alias Added",
                    f"**{alias}** → {match.product.display_name}",
                )
            )

    @product_group.command(name="create", description="Create a new product in the catalog")
    @app_commands.describe(
        model="Product model name",
        category="Category slug (gpu, cpu, ram, storage, psu, case, cooling, monitor, peripheral, networking, misc)",
        manufacturer="Manufacturer name (optional)",
        variant="Variant / sub-model (optional)",
        alias="Quick-reference alias (optional)",
    )
    async def product_create(
        self,
        interaction: discord.Interaction,
        model: str,
        category: str = "misc",
        manufacturer: str | None = None,
        variant: str | None = None,
        alias: str | None = None,
    ) -> None:
        if not await _require_auth(interaction):
            return

        with get_session() as session:
            cat = session.query(Category).filter_by(slug=category.lower()).first()
            if cat is None:
                await interaction.response.send_message(
                    embed=embed_error(f"Unknown category '{category}'."), ephemeral=True
                )
                return

            aliases = [alias] if alias else []
            new_product = create_product(
                session=session,
                category=cat,
                manufacturer=manufacturer,
                model=model,
                variant=variant,
                aliases=aliases,
            )
            _refresh_dashboard()
            await interaction.response.send_message(
                embed=embed_info(
                    "✅ Product Created",
                    f"**{new_product.display_name}** added to {cat.name}.",
                )
            )

    # ------------------------------------------------------------------
    # /ask  — natural language Q&A
    # ------------------------------------------------------------------

    ask_group = app_commands.Group(name="ask", description="Ask questions about your inventory")

    @ask_group.command(name="question", description="Ask anything about your inventory in plain English")
    @app_commands.describe(question="Your question, e.g. 'How many GPUs do I own?'")
    async def ask_question(self, interaction: discord.Interaction, question: str) -> None:
        if not ai_client.is_available():
            await interaction.response.send_message(
                embed=embed_error(
                    "AI is not configured. Add `GEMINI_API_KEY` to your `.env` file."
                ),
                ephemeral=True,
            )
            return

        if not await _defer_interaction(interaction):
            return

        with get_session() as session:
            results = service.get_inventory(session)

        context = build_inventory_context(results)
        answer = answer_question(question, context)

        if answer is None:
            await interaction.followup.send(
                embed=embed_error("AI request failed. Check logs for details.")
            )
            return

        embed = discord.Embed(
            title=f"💬 {question[:100]}",
            description=answer[:4000],
            colour=discord.Colour.from_rgb(88, 101, 242),
        )
        await interaction.followup.send(embed=embed)

    # ------------------------------------------------------------------
    # /export
    # ------------------------------------------------------------------

    export_group = app_commands.Group(name="export", description="Export inventory data")

    @export_group.command(name="csv", description="Export inventory as a CSV file")
    async def export_csv(self, interaction: discord.Interaction) -> None:
        if not await _defer_interaction(interaction):
            return

        with get_session() as session:
            results = service.get_inventory(session, include_zero=False)

        csv_bytes = _build_csv(results)
        file = discord.File(fp=io.BytesIO(csv_bytes), filename="inventory.csv")
        await interaction.followup.send(
            content=f"📄 Inventory export — **{len(results)}** item(s)",
            file=file,
        )

    @export_group.command(name="html", description="Generate a self-contained HTML inventory dashboard")
    async def export_html(self, interaction: discord.Interaction) -> None:
        if not await _defer_interaction(interaction):
            return

        from partvault.dashboard.generator import render_dashboard
        from partvault.inventory.models import PriceRecord

        with get_session() as session:
            results = service.get_inventory(session, include_zero=False)
            price_records = session.query(PriceRecord).all()
            html = render_dashboard(results, price_records)

        file = discord.File(
            fp=io.BytesIO(html.encode("utf-8")),
            filename="partvault_inventory.html",
        )
        await interaction.followup.send(
            content=f"🖥️ Dashboard export — **{len(results)}** item(s). Open the file in your browser.",
            file=file,
        )

    @app_commands.command(name="dashboard", description="Get the public inventory dashboard link")
    async def dashboard_link(self, interaction: discord.Interaction) -> None:
        _refresh_dashboard()

        if settings.DASHBOARD_PUBLIC_URL:
            embed = embed_info(
                "🖥️ Inventory Dashboard",
                f"Open the live dashboard here:\n{settings.DASHBOARD_PUBLIC_URL}",
            )
        else:
            embed = embed_warning(
                "Dashboard URL is not configured. Set `DASHBOARD_PUBLIC_URL` in `.env`, "
                "then configure GitHub Pages to publish from `/docs` on your main branch."
            )

        await interaction.response.send_message(embed=embed)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_condition(raw: str) -> Condition | None:
    mapping = {
        "new": Condition.NEW,
        "used": Condition.USED,
        "refurb": Condition.REFURBISHED,
        "refurbished": Condition.REFURBISHED,
        "broken": Condition.BROKEN,
        "damaged": Condition.BROKEN,
    }
    return mapping.get(raw.lower())


def _build_csv(results: list) -> bytes:
    import csv
    import io as _io

    buf = _io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Category", "Manufacturer", "Model", "Variant",
        "Condition", "Quantity", "Purchase Price",
        "Storage Location", "Notes",
    ])
    for r in results:
        p = r.product
        i = r.item
        writer.writerow([
            r.category.name,
            p.manufacturer or "",
            p.model,
            p.variant or "",
            i.condition,
            i.quantity,
            i.purchase_price if i.purchase_price is not None else "",
            i.storage_location or "",
            i.notes or "",
        ])
    return buf.getvalue().encode("utf-8")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InventoryCog(bot))
