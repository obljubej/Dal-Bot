from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from partvault.inventory.models import InventoryItem, PriceRecord, Product
from partvault.inventory.service import InventoryResult

TEMPLATE_PATH = Path(__file__).parent / "templates" / "dashboard.html"


def build_inventory_json(results: list[InventoryResult]) -> list[dict]:
    rows = []
    for r in results:
        p: Product = r.product
        i: InventoryItem = r.item
        rows.append({
            "id": i.id,
            "category": r.category.name,
            "manufacturer": p.manufacturer or "",
            "model": p.model,
            "variant": p.variant or "",
            "display_name": p.display_name,
            "condition": i.condition,
            "quantity": i.quantity,
            "purchase_price": i.purchase_price,
            "purchase_date": i.purchase_date.isoformat() if i.purchase_date else None,
            "storage_location": i.storage_location or "",
            "notes": i.notes or "",
            "used_price": None,
            "new_price": None,
            "used_confidence": None,
            "new_confidence": None,
            "price_updated": None,
        })
    return rows


def enrich_with_prices(rows: list[dict], price_records: list[PriceRecord]) -> None:
    """Attach latest price data to each row in-place."""
    used_prices: dict[int, PriceRecord] = {}
    new_prices: dict[int, PriceRecord] = {}

    for rec in price_records:
        if rec.price_type == "used":
            if rec.product_id not in used_prices or rec.timestamp > used_prices[rec.product_id].timestamp:
                used_prices[rec.product_id] = rec
        elif rec.price_type == "new":
            if rec.product_id not in new_prices or rec.timestamp > new_prices[rec.product_id].timestamp:
                new_prices[rec.product_id] = rec

    # Build a product_id map for rows — we need product_id which we can derive from InventoryItem
    # We'll store product_id on the row during generation; patch generator to include it.
    for row in rows:
        pid = row.get("_product_id")
        if pid is None:
            continue
        if pid in used_prices:
            rec = used_prices[pid]
            row["used_price"] = rec.estimated_price
            row["used_confidence"] = rec.confidence
            row["price_updated"] = rec.timestamp.isoformat()
        if pid in new_prices:
            rec = new_prices[pid]
            row["new_price"] = rec.estimated_price
            row["new_confidence"] = rec.confidence


def build_summary(rows: list[dict]) -> dict:
    total_qty = sum(r["quantity"] for r in rows)
    unique_products = len({(r["manufacturer"], r["model"], r["variant"]) for r in rows})

    purchase_cost = sum(
        (r["purchase_price"] or 0) * r["quantity"]
        for r in rows
        if r["purchase_price"] is not None
    )
    used_value = sum(
        (r["used_price"] or 0) * r["quantity"]
        for r in rows
        if r["used_price"] is not None
    )
    new_value = sum(
        (r["new_price"] or 0) * r["quantity"]
        for r in rows
        if r["new_price"] is not None
    )

    by_category: dict[str, int] = {}
    for r in rows:
        by_category[r["category"]] = by_category.get(r["category"], 0) + r["quantity"]

    return {
        "total_components": total_qty,
        "unique_products": unique_products,
        "purchase_cost": round(purchase_cost, 2),
        "estimated_used_value": round(used_value, 2),
        "estimated_new_value": round(new_value, 2),
        "by_category": by_category,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def render_dashboard(results: list[InventoryResult], price_records: list[PriceRecord] | None = None) -> str:
    """Render a self-contained HTML dashboard string."""
    rows = []
    for r in results:
        p: Product = r.product
        i: InventoryItem = r.item
        rows.append({
            "_product_id": p.id,
            "id": i.id,
            "category": r.category.name,
            "manufacturer": p.manufacturer or "",
            "model": p.model,
            "variant": p.variant or "",
            "display_name": p.display_name,
            "condition": i.condition,
            "quantity": i.quantity,
            "purchase_price": i.purchase_price,
            "purchase_date": i.purchase_date.isoformat() if i.purchase_date else None,
            "storage_location": i.storage_location or "",
            "notes": i.notes or "",
            "used_price": None,
            "new_price": None,
            "used_confidence": None,
            "new_confidence": None,
            "price_updated": None,
        })

    if price_records:
        enrich_with_prices(rows, price_records)

    # Strip internal _product_id before embedding
    clean_rows = [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows]

    summary = build_summary(rows)

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = template.replace(
        "/*INVENTORY_DATA*/",
        f"const INVENTORY = {json.dumps(clean_rows, default=str)};\n"
        f"const SUMMARY = {json.dumps(summary, default=str)};",
    )
    return html
