from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from partvault.config import settings

log = logging.getLogger(__name__)

EBAY_BROWSE_API = "https://api.ebay.com/buy/browse/v1/item_summary/search"
EBAY_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"

# Cache the access token for its lifetime
_token_cache: dict = {}


@dataclass
class EbayListing:
    title: str
    price: float
    currency: str
    condition: str
    url: str
    sold: bool
    listing_date: datetime | None


async def _get_access_token() -> str | None:
    import base64
    now = datetime.now(timezone.utc).timestamp()

    if _token_cache.get("token") and _token_cache.get("expires_at", 0) > now + 30:
        return _token_cache["token"]

    if not settings.EBAY_APP_ID:
        return None

    # eBay uses Client Credentials flow; App ID is "clientId:clientSecret" base64-encoded
    # For the Browse API (sandbox/prod) you need an App access token.
    credentials = base64.b64encode(settings.EBAY_APP_ID.encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = "grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(EBAY_OAUTH_URL, headers=headers, content=data)
            resp.raise_for_status()
            body = resp.json()
            _token_cache["token"] = body["access_token"]
            _token_cache["expires_at"] = now + int(body.get("expires_in", 7200))
            return _token_cache["token"]
    except Exception as exc:
        log.error("eBay OAuth failed: %s", exc)
        return None


async def search_sold_listings(
    query: str,
    limit: int = 10,
    currency: str = "CAD",
) -> list[EbayListing]:
    """
    Search eBay completed/sold listings using the Browse API.
    Returns a list of EbayListing results.
    """
    token = await _get_access_token()
    if not token:
        log.warning("eBay API key not configured — skipping eBay pricing.")
        return []

    params = {
        "q": query,
        "filter": "buyingOptions:{FIXED_PRICE},conditions:{USED}",
        "sort": "endTimeSoonest",
        "limit": str(limit),
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_CA" if currency == "CAD" else "EBAY_US",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(EBAY_BROWSE_API, headers=headers, params=params)
            resp.raise_for_status()
            body = resp.json()
    except Exception as exc:
        log.error("eBay search failed for '%s': %s", query, exc)
        return []

    listings: list[EbayListing] = []
    for item in body.get("itemSummaries", []):
        try:
            price_obj = item.get("price", {})
            price = float(price_obj.get("value", 0))
            if price <= 0:
                continue
            listings.append(EbayListing(
                title=item.get("title", ""),
                price=price,
                currency=price_obj.get("currency", currency),
                condition=item.get("condition", "USED"),
                url=item.get("itemWebUrl", ""),
                sold=False,
                listing_date=None,
            ))
        except (ValueError, TypeError):
            continue

    return listings


async def search_active_listings(
    query: str,
    limit: int = 10,
    currency: str = "CAD",
) -> list[EbayListing]:
    """Search active (unsold) eBay listings for retail-price comparison."""
    token = await _get_access_token()
    if not token:
        return []

    params = {
        "q": query,
        "filter": "buyingOptions:{FIXED_PRICE}",
        "sort": "price",
        "limit": str(limit),
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_CA" if currency == "CAD" else "EBAY_US",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(EBAY_BROWSE_API, headers=headers, params=params)
            resp.raise_for_status()
            body = resp.json()
    except Exception as exc:
        log.error("eBay active search failed for '%s': %s", query, exc)
        return []

    listings: list[EbayListing] = []
    for item in body.get("itemSummaries", []):
        try:
            price_obj = item.get("price", {})
            price = float(price_obj.get("value", 0))
            if price <= 0:
                continue
            listings.append(EbayListing(
                title=item.get("title", ""),
                price=price,
                currency=price_obj.get("currency", currency),
                condition=item.get("condition", "NEW"),
                url=item.get("itemWebUrl", ""),
                sold=False,
                listing_date=None,
            ))
        except (ValueError, TypeError):
            continue

    return listings
