from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from partvault.config import settings
from partvault.database.connection import get_session
from partvault.pricing.engine import refresh_all_prices

log = logging.getLogger(__name__)


async def run_price_scheduler() -> None:
    """
    Background task that refreshes prices every PRICE_REFRESH_DAYS days.
    Designed to run as a long-lived asyncio task alongside the Discord bot.
    """
    interval_seconds = settings.PRICE_REFRESH_DAYS * 86_400

    while True:
        log.info("Price scheduler: starting refresh cycle at %s", datetime.now(timezone.utc).isoformat())
        try:
            with get_session() as session:
                count = await refresh_all_prices(session)
            log.info("Price scheduler: refreshed %d product(s).", count)
        except Exception as exc:
            log.error("Price scheduler error: %s", exc)

        log.info("Price scheduler: sleeping %d days until next run.", settings.PRICE_REFRESH_DAYS)
        await asyncio.sleep(interval_seconds)
