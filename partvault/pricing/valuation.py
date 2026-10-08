from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass

from partvault.ai import client as ai_client
from partvault.ai.prompts import LISTING_CLASSIFIER_SYSTEM
from partvault.pricing.sources.ebay import EbayListing

log = logging.getLogger(__name__)


@dataclass
class PriceEstimate:
    estimated_price: float | None
    confidence: str          # "high" | "medium" | "low" | "unavailable"
    source_count: int
    currency: str
    raw_prices: list[float]


def _classify_listing_ai(listing: EbayListing, target_product: str) -> bool:
    """
    Use AI to decide whether a listing is a valid comparable for the target product.
    Falls back to True (include) if AI is unavailable.
    """
    if not ai_client.is_available():
        return True

    user_msg = (
        f"Target product: {target_product}\n"
        f"Listing title: {listing.title}\n"
        f"Listing price: {listing.price} {listing.currency}\n"
        f"Condition: {listing.condition}"
    )
    response = ai_client.chat(
        messages=[
            {"role": "system", "content": LISTING_CLASSIFIER_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.0,
        max_tokens=128,
        json_mode=True,
    )
    if not response:
        return True

    try:
        text = response.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])
        data = json.loads(text)
        return bool(data.get("is_valid", True))
    except Exception:
        return True


def filter_listings(
    listings: list[EbayListing],
    target_product: str,
    use_ai: bool = True,
) -> list[EbayListing]:
    """Remove listings that are not valid comparables for the target product."""
    valid: list[EbayListing] = []
    for listing in listings:
        if use_ai:
            if _classify_listing_ai(listing, target_product):
                valid.append(listing)
        else:
            valid.append(listing)
    return valid


def calculate_estimate(prices: list[float], currency: str) -> PriceEstimate:
    """
    Calculate a representative market price from a list of comparable prices.
    Trims extreme outliers (>2 std devs from mean) and uses the median.
    """
    if not prices:
        return PriceEstimate(
            estimated_price=None,
            confidence="unavailable",
            source_count=0,
            currency=currency,
            raw_prices=[],
        )

    filtered = _trim_outliers(prices)
    estimated = round(statistics.median(filtered), 2)

    if len(filtered) >= 5:
        confidence = "high"
    elif len(filtered) >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return PriceEstimate(
        estimated_price=estimated,
        confidence=confidence,
        source_count=len(filtered),
        currency=currency,
        raw_prices=filtered,
    )


def _trim_outliers(prices: list[float]) -> list[float]:
    if len(prices) < 4:
        return prices
    mean = statistics.mean(prices)
    stdev = statistics.stdev(prices)
    if stdev == 0:
        return prices
    return [p for p in prices if abs(p - mean) <= 2 * stdev]
