from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from partvault.config import settings
from partvault.dashboard.generator import export_dashboard

log = logging.getLogger(__name__)

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.reactions = True


class PartVaultBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix="!",
            intents=INTENTS,
            help_command=None,
        )
        self._scheduler_task: asyncio.Task | None = None

    async def setup_hook(self) -> None:
        await self.load_extension("partvault.bot.commands.inventory")
        await self.load_extension("partvault.bot.commands.pricing")
        await self.load_extension("partvault.bot.events.messages")

        if settings.GUILD_ID:
            guild = discord.Object(id=settings.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Slash commands synced to guild %d", settings.GUILD_ID)
        else:
            await self.tree.sync()
            log.info("Slash commands synced globally (may take up to 1 hour)")

    async def on_ready(self) -> None:
        log.info("Logged in as %s (ID: %d)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="your hardware inventory",
            )
        )

        try:
            export_dashboard()
        except Exception as exc:
            log.error("Dashboard export failed on startup: %s", exc)

        # Start background price scheduler if eBay is configured
        if settings.EBAY_APP_ID and self._scheduler_task is None:
            from partvault.pricing.scheduler import run_price_scheduler
            self._scheduler_task = asyncio.create_task(run_price_scheduler())
            log.info("Price scheduler started.")

    async def close(self) -> None:
        if self._scheduler_task:
            self._scheduler_task.cancel()
        await super().close()


def create_bot() -> PartVaultBot:
    return PartVaultBot()
