from __future__ import annotations

import logging
from aiohttp import web

from partvault.config import settings

log = logging.getLogger(__name__)
_app: web.Application | None = None
_runner: web.AppRunner | None = None


async def _handle_dashboard(request: web.Request) -> web.Response:
    from partvault.dashboard.generator import render_dashboard
    from partvault.database.connection import get_session
    from partvault.inventory import service
    from partvault.inventory.models import PriceRecord

    with get_session() as session:
        results = service.get_inventory(session, include_zero=False)
        price_records = session.query(PriceRecord).all()
        html = render_dashboard(results, price_records)

    return web.Response(text=html, content_type="text/html", charset="utf-8")


async def start_dashboard_server() -> None:
    global _app, _runner

    _app = web.Application()
    _app.router.add_get("/", _handle_dashboard)
    _app.router.add_get("/dashboard", _handle_dashboard)

    _runner = web.AppRunner(_app)
    await _runner.setup()

    site = web.TCPSite(_runner, settings.DASHBOARD_HOST, settings.DASHBOARD_PORT)
    await site.start()

    log.info(
        "Dashboard available at http://%s:%d/",
        settings.DASHBOARD_HOST,
        settings.DASHBOARD_PORT,
    )


async def stop_dashboard_server() -> None:
    if _runner:
        await _runner.cleanup()


def dashboard_url() -> str:
    return f"http://{settings.DASHBOARD_HOST}:{settings.DASHBOARD_PORT}/"
