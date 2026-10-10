from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Discord
DISCORD_TOKEN: str = os.environ["DISCORD_TOKEN"]
INVENTORY_CHANNEL_IDS: list[int] = [
    int(x.strip())
    for x in os.getenv("INVENTORY_CHANNEL_IDS", "").split(",")
    if x.strip()
]
AUTHORIZED_USER_IDS: list[int] = [
    int(x.strip())
    for x in os.getenv("AUTHORIZED_USER_IDS", "").split(",")
    if x.strip()
]
GUILD_ID: int | None = (
    int(os.environ["GUILD_ID"]) if os.getenv("GUILD_ID") else None
)

# Database
DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "partvault.db"))

# Matching
FUZZY_MATCH_THRESHOLD: int = int(os.getenv("FUZZY_MATCH_THRESHOLD", "70"))

# AI
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
AI_MODEL: str = os.getenv("AI_MODEL", "gemini-2.0-flash")
AI_ENABLED: bool = os.getenv("AI_ENABLED", "true").lower() not in ("false", "0", "no")

# Pricing
EBAY_APP_ID: str = os.getenv("EBAY_APP_ID", "")
PRICE_REFRESH_DAYS: int = int(os.getenv("PRICE_REFRESH_DAYS", "7"))

# Currency
DEFAULT_CURRENCY: str = os.getenv("DEFAULT_CURRENCY", "CAD")

# Dashboard / GitHub Pages
DASHBOARD_EXPORT_PATH: str = os.getenv("DASHBOARD_EXPORT_PATH", str(BASE_DIR / "docs" / "index.html"))
DASHBOARD_PUBLIC_URL: str = os.getenv("DASHBOARD_PUBLIC_URL", "")
