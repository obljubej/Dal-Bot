#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import logging
import sys

from partvault.config import settings
from partvault.database.connection import init_db
from partvault.database.seed import seed_database


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


async def main() -> None:
    setup_logging()
    log = logging.getLogger("partvault")

    log.info("Initializing database at %s", settings.DB_PATH)
    init_db(settings.DB_PATH)
    seed_database()
    log.info("Database ready.")

    from partvault.bot.main import create_bot
    bot = create_bot()

    async with bot:
        await bot.start(settings.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
