from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from partvault.inventory.models import (
    Category,
    Condition,
    InventoryItem,
    InventoryTransaction,
    Product,
    ProductAlias,
    TransactionAction,
)
from partvault.inventory.transactions import log_transaction


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

@dataclass
class InventoryResult:
    item: InventoryItem
    product: Product
    category: Category


@dataclass
class InventorySummary:
    total_components: int
    unique_products: int
    items: list[InventoryResult]


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------

def add_inventory(
    session: Session,
    product: Product,
    quantity: int,
    condition: Condition = Condition.USED,
    purchase_price: float | None = None,
    purchase_date: datetime | None = None,
    storage_location: str | None = None,
    notes: str | None = None,
    discord_user_id: str | None = None,
) -> InventoryItem:
    if quantity <= 0:
        raise ValueError("Quantity must be positive.")

    item = (
        session.query(InventoryItem)
        .filter_by(product_id=product.id, condition=condition)
        .first()
    )

    if item is None:
        item = InventoryItem(
            product_id=product.id,
            quantity=quantity,
            condition=condition,
            purchase_price=purchase_price,
            purchase_date=purchase_date,
            storage_location=storage_location,
            notes=notes,
        )
        session.add(item)
        session.flush()
    else:
        item.quantity += quantity
        if purchase_price is not None and item.purchase_price is None:
            item.purchase_price = purchase_price

    log_transaction(
        session=session,
        inventory_item_id=item.id,
        action=TransactionAction.ADD,
        quantity_change=quantity,
        discord_user_id=discord_user_id,
    )

    return item


def remove_inventory(
    session: Session,
    product: Product,
    quantity: int,
    condition: Condition = Condition.USED,
    discord_user_id: str | None = None,
) -> InventoryItem:
    if quantity <= 0:
        raise ValueError("Quantity must be positive.")

    item = (
        session.query(InventoryItem)
        .filter_by(product_id=product.id, condition=condition)
        .first()
    )

    if item is None or item.quantity == 0:
        raise ValueError(
            f"No {condition} units of '{product.display_name}' in inventory."
        )

    if item.quantity < quantity:
        raise ValueError(
            f"Only {item.quantity} {condition} unit(s) of '{product.display_name}' in inventory; "
            f"cannot remove {quantity}."
        )

    item.quantity -= quantity

    log_transaction(
        session=session,
        inventory_item_id=item.id,
        action=TransactionAction.REMOVE,
        quantity_change=-quantity,
        discord_user_id=discord_user_id,
    )

    return item


def get_inventory(
    session: Session,
    category_slug: str | None = None,
    search: str | None = None,
    include_zero: bool = False,
) -> list[InventoryResult]:
    q = (
        session.query(InventoryItem)
        .join(Product, InventoryItem.product_id == Product.id)
        .join(Category, Product.category_id == Category.id)
    )

    if not include_zero:
        q = q.filter(InventoryItem.quantity > 0)

    if category_slug:
        q = q.filter(Category.slug == category_slug)

    if search:
        term = f"%{search.lower()}%"
        q = q.filter(
            (Product.model.ilike(term))
            | (Product.manufacturer.ilike(term))
            | (Product.variant.ilike(term))
        )

    items = q.order_by(Category.name, Product.manufacturer, Product.model).all()
    return [
        InventoryResult(item=i, product=i.product, category=i.product.category)
        for i in items
    ]


def get_inventory_summary(session: Session) -> InventorySummary:
    results = get_inventory(session)
    total_components = sum(r.item.quantity for r in results)
    unique_products = len({r.product.id for r in results})
    return InventorySummary(
        total_components=total_components,
        unique_products=unique_products,
        items=results,
    )


def get_item_by_id(session: Session, item_id: int) -> InventoryItem | None:
    return session.query(InventoryItem).filter_by(id=item_id).first()


def edit_inventory_item(
    session: Session,
    item: InventoryItem,
    notes: str | None = None,
    storage_location: str | None = None,
    purchase_price: float | None = None,
    purchase_date: datetime | None = None,
    discord_user_id: str | None = None,
) -> InventoryItem:
    if notes is not None:
        item.notes = notes
    if storage_location is not None:
        item.storage_location = storage_location
    if purchase_price is not None:
        item.purchase_price = purchase_price
    if purchase_date is not None:
        item.purchase_date = purchase_date

    log_transaction(
        session=session,
        inventory_item_id=item.id,
        action=TransactionAction.EDIT,
        quantity_change=0,
        discord_user_id=discord_user_id,
    )
    return item


def get_categories(session: Session) -> list[Category]:
    return session.query(Category).order_by(Category.name).all()


def create_product(
    session: Session,
    category: Category,
    manufacturer: str | None,
    model: str,
    variant: str | None = None,
    specifications: str | None = None,
    aliases: list[str] | None = None,
) -> Product:
    product = Product(
        category_id=category.id,
        manufacturer=manufacturer,
        model=model,
        variant=variant,
        specifications=specifications,
    )
    session.add(product)
    session.flush()

    for alias_text in (aliases or []):
        normalized = alias_text.lower().strip()
        existing = session.query(ProductAlias).filter_by(alias_text=normalized).first()
        if not existing:
            session.add(ProductAlias(product_id=product.id, alias_text=normalized))

    return product


def add_alias(session: Session, product: Product, alias_text: str) -> ProductAlias | None:
    normalized = alias_text.lower().strip()
    existing = session.query(ProductAlias).filter_by(alias_text=normalized).first()
    if existing:
        return None
    alias = ProductAlias(product_id=product.id, alias_text=normalized)
    session.add(alias)
    session.flush()
    return alias


def get_transaction_history(
    session: Session,
    limit: int = 20,
    product_id: int | None = None,
) -> list[InventoryTransaction]:
    q = (
        session.query(InventoryTransaction)
        .join(InventoryItem, InventoryTransaction.inventory_item_id == InventoryItem.id)
    )
    if product_id is not None:
        q = q.filter(InventoryItem.product_id == product_id)
    return q.order_by(InventoryTransaction.timestamp.desc()).limit(limit).all()
