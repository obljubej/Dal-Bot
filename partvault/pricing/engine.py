from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from partvault.config import settings
from partvault.inventory.models import Condition, PriceRecord, Product
from partvault.pricing.sources.ebay import search_active_listings, search_sold_listings
from partvault.pricing.valuation import PriceEstimate, calculate_estimate, filter_listings

log = logging.getLogger(__name__)


async def refresh_price(
    session: Session,
    product: Product,
    condition: str = Condition.USED,
    currency: str | None = None,
    force: bool = False,
) -> PriceRecord | None:
    """
    Fetch current market pricing for a product and store it.
    Returns the created/updated PriceRecord, or None if pricing is unavailable.
    """
    currency = currency or settings.DEFAULT_CURRENCY

    # Skip if recently updated (unless forced)
    if not force:
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.PRICE_REFRESH_DAYS)
        existing = (
            session.query(PriceRecord)
            .filter_by(product_id=product.id, condition=condition, currency=currency)
            .filter(PriceRecord.timestamp >= cutoff)
            .order_by(PriceRecord.timestamp.desc())
            .first()
        )
        if existing:
            log.debug("Price for %s is fresh, skipping refresh.", product.display_name)
            return existing

    search_query = product.display_name
    used_listings = await search_sold_listings(search_query, limit=15, currency=currency)
    valid_used = filter_listings(used_listings, search_query, use_ai=True)
    used_prices = [l.price for l in valid_used]
    used_estimate = calculate_estimate(used_prices, currency)

    new_listings = await search_active_listings(search_query, limit=10, currency=currency)
    valid_new = filter_listings(new_listings, search_query, use_ai=True)
    new_prices = [l.price for l in valid_new]
    new_estimate = calculate_estimate(new_prices, currency)

    records = []
    for price_type, estimate in (("used", used_estimate), ("new", new_estimate)):
        if estimate.estimated_price is None:
            continue
        record = PriceRecord(
            product_id=product.id,
            condition=condition,
            price_type=price_type,
            currency=currency,
            estimated_price=estimate.estimated_price,
            confidence=estimate.confidence,
            source_count=estimate.source_count,
        )
        session.add(record)
        records.append(record)

    session.flush()
    log.info(
        "Price refreshed for %s: used=%s, new=%s (%s)",
        product.display_name,
        used_estimate.estimated_price,
        new_estimate.estimated_price,
        currency,
    )
    return records[0] if records else None


def get_latest_price(
    session: Session,
    product: Product,
    price_type: str = "used",
    currency: str | None = None,
) -> PriceRecord | None:
    currency = currency or settings.DEFAULT_CURRENCY
    return (
        session.query(PriceRecord)
        .filter_by(product_id=product.id, price_type=price_type, currency=currency)
        .order_by(PriceRecord.timestamp.desc())
        .first()
    )


def get_price_history(
    session: Session,
    product: Product,
    price_type: str = "used",
    currency: str | None = None,
    limit: int = 30,
) -> list[PriceRecord]:
    currency = currency or settings.DEFAULT_CURRENCY
    return (
        session.query(PriceRecord)
        .filter_by(product_id=product.id, price_type=price_type, currency=currency)
        .order_by(PriceRecord.timestamp.desc())
        .limit(limit)
        .all()
    )


async def refresh_all_prices(
    session: Session,
    currency: str | None = None,
    force: bool = False,
) -> int:
    """Refresh prices for all products that have inventory. Returns count refreshed."""
    from partvault.inventory.models import InventoryItem

    product_ids = [
        row.product_id
        for row in session.query(InventoryItem.product_id)
        .filter(InventoryItem.quantity > 0)
        .distinct()
        .all()
    ]

    count = 0
    for pid in product_ids:
        product = session.query(Product).filter_by(id=pid).first()
        if product:
            result = await refresh_price(session, product, currency=currency, force=force)
            if result:
                count += 1

    return count
