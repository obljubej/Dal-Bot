from __future__ import annotations

from sqlalchemy.orm import Session

from partvault.inventory.models import InventoryTransaction, TransactionAction


def log_transaction(
    session: Session,
    inventory_item_id: int,
    action: TransactionAction,
    quantity_change: int,
    reason: str | None = None,
    discord_user_id: str | None = None,
) -> InventoryTransaction:
    tx = InventoryTransaction(
        inventory_item_id=inventory_item_id,
        action=action,
        quantity_change=quantity_change,
        reason=reason,
        discord_user_id=discord_user_id,
    )
    session.add(tx)
    return tx


def get_recent_transactions(
    session: Session,
    limit: int = 20,
    inventory_item_id: int | None = None,
) -> list[InventoryTransaction]:
    q = session.query(InventoryTransaction)
    if inventory_item_id is not None:
        q = q.filter(InventoryTransaction.inventory_item_id == inventory_item_id)
    return q.order_by(InventoryTransaction.timestamp.desc()).limit(limit).all()
