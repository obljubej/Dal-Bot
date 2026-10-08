from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from partvault.bot.ui.embeds import embed_error, embed_info, embed_warning
from partvault.config import settings
from partvault.database.connection import get_session
from partvault.inventory.matcher import find_product
from partvault.inventory.models import Condition
from partvault.pricing.engine import get_latest_price, get_price_history, refresh_price


def _is_authorized(interaction: discord.Interaction) -> bool:
    return not settings.AUTHORIZED_USER_IDS or interaction.user.id in settings.AUTHORIZED_USER_IDS


class PricingCog(commands.Cog, name="Pricing"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    price_group = app_commands.Group(name="price", description="Market pricing commands")

    @price_group.command(name="check", description="Show current market price for a product")
    @app_commands.describe(
        product="Product name or alias",
        currency="Currency: CAD or USD",
    )
    async def price_check(
        self,
        interaction: discord.Interaction,
        product: str,
        currency: str = "",
    ) -> None:
        await interaction.response.defer()
        currency = currency.upper() or settings.DEFAULT_CURRENCY

        with get_session() as session:
            match = find_product(session, product)
            if match is None:
                await interaction.followup.send(
                    embed=embed_error(f"Product not found: **{product}**")
                )
                return

            used_record = get_latest_price(session, match.product, "used", currency)
            new_record = get_latest_price(session, match.product, "new", currency)

        embed = discord.Embed(
            title=f"💰 {match.product.display_name}",
            colour=discord.Colour.from_rgb(87, 242, 135),
        )
        embed.add_field(name="Category", value=match.product.category.name, inline=True)

        if used_record:
            embed.add_field(
                name=f"Used ({used_record.confidence} confidence)",
                value=f"**{used_record.estimated_price:.2f} {used_record.currency}**\n"
                      f"Based on {used_record.source_count} listing(s)\n"
                      f"Updated: {used_record.timestamp.strftime('%Y-%m-%d')}",
                inline=True,
            )
        else:
            embed.add_field(name="Used Price", value="Not yet retrieved", inline=True)

        if new_record:
            embed.add_field(
                name=f"New ({new_record.confidence} confidence)",
                value=f"**{new_record.estimated_price:.2f} {new_record.currency}**\n"
                      f"Based on {new_record.source_count} listing(s)\n"
                      f"Updated: {new_record.timestamp.strftime('%Y-%m-%d')}",
                inline=True,
            )
        else:
            embed.add_field(name="New Price", value="Not yet retrieved", inline=True)

        await interaction.followup.send(embed=embed)

    @price_group.command(name="refresh", description="Fetch fresh market pricing for a product")
    @app_commands.describe(
        product="Product name or alias",
        currency="Currency: CAD or USD",
    )
    async def price_refresh(
        self,
        interaction: discord.Interaction,
        product: str,
        currency: str = "",
    ) -> None:
        if not _is_authorized(interaction):
            await interaction.response.send_message(
                embed=embed_error("Not authorized."), ephemeral=True
            )
            return

        if not settings.EBAY_APP_ID:
            await interaction.response.send_message(
                embed=embed_warning(
                    "eBay pricing is not configured.\n"
                    "Add `EBAY_APP_ID` to your `.env` file.\n\n"
                    "See [eBay Developer Program](https://developer.ebay.com/) to register."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        currency = currency.upper() or settings.DEFAULT_CURRENCY

        with get_session() as session:
            match = find_product(session, product)
            if match is None:
                await interaction.followup.send(
                    embed=embed_error(f"Product not found: **{product}**")
                )
                return

            record = await refresh_price(
                session, match.product, currency=currency, force=True
            )

        if record is None:
            await interaction.followup.send(
                embed=embed_warning(f"No pricing data found for **{match.product.display_name}**.")
            )
            return

        await interaction.followup.send(
            embed=embed_info(
                "✅ Price Refreshed",
                f"**{match.product.display_name}**\n"
                f"Estimated used: **{record.estimated_price:.2f} {record.currency}**\n"
                f"Confidence: {record.confidence} | Sources: {record.source_count}",
            )
        )

    @price_group.command(name="refresh-all", description="Refresh prices for all inventory items")
    async def price_refresh_all(self, interaction: discord.Interaction) -> None:
        if not _is_authorized(interaction):
            await interaction.response.send_message(
                embed=embed_error("Not authorized."), ephemeral=True
            )
            return

        if not settings.EBAY_APP_ID:
            await interaction.response.send_message(
                embed=embed_warning("eBay pricing not configured. Add `EBAY_APP_ID` to `.env`."),
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        from partvault.pricing.engine import refresh_all_prices
        with get_session() as session:
            count = await refresh_all_prices(session, force=True)

        await interaction.followup.send(
            embed=embed_info("✅ Prices Refreshed", f"Updated pricing for **{count}** product(s).")
        )

    @price_group.command(name="history", description="Show price history for a product")
    @app_commands.describe(product="Product name or alias")
    async def price_history(
        self,
        interaction: discord.Interaction,
        product: str,
    ) -> None:
        await interaction.response.defer()

        with get_session() as session:
            match = find_product(session, product)
            if match is None:
                await interaction.followup.send(
                    embed=embed_error(f"Product not found: **{product}**")
                )
                return

            history = get_price_history(session, match.product, limit=10)

        if not history:
            await interaction.followup.send(
                embed=embed_warning(f"No price history for **{match.product.display_name}**.")
            )
            return

        embed = discord.Embed(
            title=f"📈 Price History — {match.product.display_name}",
            colour=discord.Colour.from_rgb(88, 101, 242),
        )
        lines = []
        for r in history:
            date = r.timestamp.strftime("%Y-%m-%d")
            lines.append(
                f"`{date}` **{r.price_type.upper()}** "
                f"{r.estimated_price:.2f} {r.currency} "
                f"[{r.confidence}, {r.source_count} src]"
            )
        embed.description = "\n".join(lines)
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PricingCog(bot))
