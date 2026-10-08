from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from partvault.inventory.models import Category, Product, ProductAlias


# ---------------------------------------------------------------------------
# Category keyword mapping
# Used to infer category from a free-text product description.
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "gpu": [
        "gpu", "graphics", "video card", "videocard",
        "radeon", "geforce", "gtx", "rtx", "rx",
        "9070", "9060", "9080", "9090",
        "4090", "4080", "4070", "4060", "4050",
        "5090", "5080", "5070", "5060",
        "7900", "7800", "7700", "7600",
        "vega", "navi", "arc",
    ],
    "cpu": [
        "cpu", "processor",
        "ryzen", "intel", "core", "xeon", "threadripper",
        "i3", "i5", "i7", "i9",
        "x3d", "9950x", "9900x", "9800x", "9700x",
        "7950x", "7900x", "7800x", "7700x",
        "14900", "14700", "14600", "14400",
        "285k", "265k", "245k",
    ],
    "motherboard": [
        "motherboard", "mobo", "mainboard",
        "x870", "x670", "b650", "b550", "a620",
        "z790", "z690", "b760", "h770",
        "atx", "matx", "itx", "eatx",
        "asus", "gigabyte", "msi", "asrock", "evga",
    ],
    "ram": [
        "ram", "memory", "ddr4", "ddr5",
        "dimm", "sodimm",
        "vengeance", "trident", "fury",
        "32gb", "64gb", "16gb", "8gb",
        "6000mhz", "6400mhz", "5600mhz", "4800mhz",
    ],
    "storage": [
        "ssd", "hdd", "nvme", "m.2", "sata",
        "990 pro", "980 pro", "970 evo", "870 evo",
        "sn850", "sn770", "sn580",
        "firecuda", "barracuda",
        "1tb", "2tb", "4tb", "500gb", "512gb",
        "samsung", "wd", "seagate", "kingston", "crucial",
    ],
    "psu": [
        "psu", "power supply", "watt",
        "650w", "750w", "850w", "1000w", "1200w",
        "modular", "semi-modular",
        "corsair", "evga", "seasonic", "be quiet",
    ],
    "case": [
        "case", "chassis", "tower",
        "atx", "matx", "itx",
        "mid tower", "full tower", "mini itx",
        "fractal", "nzxt", "lian li", "phanteks",
    ],
    "cooling": [
        "cooling", "cooler", "heatsink", "fan",
        "aio", "liquid cooling", "water cooling",
        "thermal paste", "noctua", "be quiet", "arctic",
        "120mm", "240mm", "280mm", "360mm",
    ],
    "monitor": [
        "monitor", "display", "screen",
        "1080p", "1440p", "4k", "ultrawide",
        "hz", "144hz", "165hz", "240hz",
        "ips", "va", "oled", "qd-oled",
    ],
    "peripheral": [
        "keyboard", "mouse", "headset", "headphones",
        "mousepad", "webcam", "microphone",
        "mechanical", "gaming",
    ],
    "networking": [
        "router", "switch", "network", "ethernet",
        "wifi", "pcie wifi", "network card",
        "2.5g", "10g",
    ],
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


# ---------------------------------------------------------------------------
# Match result
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    product: Product
    score: float
    matched_via: str  # "alias_exact" | "alias_fuzzy" | "name_fuzzy"


# ---------------------------------------------------------------------------
# Core matching logic
# ---------------------------------------------------------------------------

def find_product(
    session: Session,
    query: str,
    threshold: int = 70,
) -> MatchResult | None:
    """
    Try to match a free-text query to an existing Product.

    Strategy:
    1. Exact alias match (case-insensitive).
    2. Fuzzy alias match (token_set_ratio).
    3. Fuzzy product display-name match.

    Returns the best match above `threshold`, or None.
    """
    normalized = _normalize(query)

    # 1. Exact alias match
    alias = (
        session.query(ProductAlias)
        .filter(ProductAlias.alias_text == normalized)
        .first()
    )
    if alias:
        return MatchResult(
            product=alias.product,
            score=100.0,
            matched_via="alias_exact",
        )

    # 2. Gather all aliases for fuzzy matching
    all_aliases: list[ProductAlias] = session.query(ProductAlias).all()
    alias_texts = [a.alias_text for a in all_aliases]
    alias_map = {a.alias_text: a for a in all_aliases}

    if alias_texts:
        best_alias = process.extractOne(
            normalized,
            alias_texts,
            scorer=fuzz.token_set_ratio,
            score_cutoff=threshold,
        )
        if best_alias:
            matched_text, score, _ = best_alias
            return MatchResult(
                product=alias_map[matched_text].product,
                score=float(score),
                matched_via="alias_fuzzy",
            )

    # 3. Fuzzy match against product display names
    all_products: list[Product] = session.query(Product).all()
    product_names = [p.display_name for p in all_products]
    product_map = {p.display_name: p for p in all_products}

    if product_names:
        best_product = process.extractOne(
            normalized,
            product_names,
            scorer=fuzz.token_set_ratio,
            score_cutoff=threshold,
        )
        if best_product:
            matched_name, score, _ = best_product
            return MatchResult(
                product=product_map[matched_name],
                score=float(score),
                matched_via="name_fuzzy",
            )

    return None


def infer_category(
    session: Session,
    query: str,
) -> Category | None:
    """Guess the most likely Category for a free-text product description."""
    normalized = _normalize(query)
    scores: dict[str, int] = {}

    for slug, keywords in CATEGORY_KEYWORDS.items():
        hit_count = sum(1 for kw in keywords if kw in normalized)
        if hit_count:
            scores[slug] = hit_count

    if not scores:
        return None

    best_slug = max(scores, key=lambda s: scores[s])
    return session.query(Category).filter_by(slug=best_slug).first()


# ---------------------------------------------------------------------------
# Command parser for quick commands (+4 9070xt, -2 9070xt)
# ---------------------------------------------------------------------------

_QUICK_CMD_RE = re.compile(r"^([+\-])(\d+)\s+(.+)$", re.DOTALL)
_CONDITION_MAP = {
    "new": "new",
    "used": "used",
    "refurb": "refurbished",
    "refurbished": "refurbished",
    "broken": "broken",
    "dmg": "broken",
    "damaged": "broken",
}


@dataclass
class ParsedQuickCommand:
    action: str          # "add" | "remove"
    quantity: int
    product_query: str
    condition: str       # Condition value


def parse_quick_command(text: str) -> ParsedQuickCommand | None:
    """
    Parse a quick inventory command like '+4 9070xt' or '-2 used rtx 4090'.
    Returns None if the text does not match the expected pattern.
    """
    text = text.strip()
    match = _QUICK_CMD_RE.match(text)
    if not match:
        return None

    sign, qty_str, rest = match.groups()
    action = "add" if sign == "+" else "remove"
    quantity = int(qty_str)
    if quantity == 0:
        return None

    # Check for condition prefix in product query
    tokens = rest.strip().split()
    condition = "used"
    if tokens and tokens[0].lower() in _CONDITION_MAP:
        condition = _CONDITION_MAP[tokens[0].lower()]
        product_query = " ".join(tokens[1:]).strip()
    else:
        product_query = rest.strip()

    if not product_query:
        return None

    return ParsedQuickCommand(
        action=action,
        quantity=quantity,
        product_query=product_query,
        condition=condition,
    )
