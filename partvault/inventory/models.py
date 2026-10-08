from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Condition(str, PyEnum):
    NEW = "new"
    USED = "used"
    REFURBISHED = "refurbished"
    BROKEN = "broken"


class TransactionAction(str, PyEnum):
    ADD = "add"
    REMOVE = "remove"
    EDIT = "edit"


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    products: Mapped[list[Product]] = relationship("Product", back_populates="category")

    def __repr__(self) -> str:
        return f"<Category {self.name}>"


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    variant: Mapped[str | None] = mapped_column(String(256))
    specifications: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    category: Mapped[Category] = relationship("Category", back_populates="products")
    aliases: Mapped[list[ProductAlias]] = relationship(
        "ProductAlias", back_populates="product", cascade="all, delete-orphan"
    )
    inventory_items: Mapped[list[InventoryItem]] = relationship(
        "InventoryItem", back_populates="product", cascade="all, delete-orphan"
    )
    price_records: Mapped[list[PriceRecord]] = relationship(
        "PriceRecord", back_populates="product", cascade="all, delete-orphan"
    )

    @property
    def display_name(self) -> str:
        parts = []
        if self.manufacturer:
            parts.append(self.manufacturer)
        parts.append(self.model)
        if self.variant:
            parts.append(self.variant)
        return " ".join(parts)

    def __repr__(self) -> str:
        return f"<Product {self.display_name}>"


# ---------------------------------------------------------------------------
# ProductAlias
# ---------------------------------------------------------------------------

class ProductAlias(Base):
    __tablename__ = "product_aliases"
    __table_args__ = (UniqueConstraint("alias_text"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    alias_text: Mapped[str] = mapped_column(String(256), nullable=False)

    product: Mapped[Product] = relationship("Product", back_populates="aliases")

    def __repr__(self) -> str:
        return f"<ProductAlias {self.alias_text!r} -> {self.product_id}>"


# ---------------------------------------------------------------------------
# InventoryItem
# ---------------------------------------------------------------------------

class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (UniqueConstraint("product_id", "condition", name="uq_product_condition"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    condition: Mapped[str] = mapped_column(
        Enum(Condition), default=Condition.USED, nullable=False
    )
    purchase_price: Mapped[float | None] = mapped_column(Float)
    purchase_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    storage_location: Mapped[str | None] = mapped_column(String(256))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    product: Mapped[Product] = relationship("Product", back_populates="inventory_items")
    transactions: Mapped[list[InventoryTransaction]] = relationship(
        "InventoryTransaction", back_populates="inventory_item", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<InventoryItem product={self.product_id} qty={self.quantity} cond={self.condition}>"


# ---------------------------------------------------------------------------
# InventoryTransaction
# ---------------------------------------------------------------------------

class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(Enum(TransactionAction), nullable=False)
    quantity_change: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(512))
    discord_user_id: Mapped[str | None] = mapped_column(String(32))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    inventory_item: Mapped[InventoryItem] = relationship(
        "InventoryItem", back_populates="transactions"
    )

    def __repr__(self) -> str:
        return f"<Transaction {self.action} {self.quantity_change:+d} on item {self.inventory_item_id}>"


# ---------------------------------------------------------------------------
# PriceRecord (stub — populated in Phase 3)
# ---------------------------------------------------------------------------

class PriceRecord(Base):
    __tablename__ = "price_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    condition: Mapped[str] = mapped_column(Enum(Condition), nullable=False)
    price_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "new" | "used"
    currency: Mapped[str] = mapped_column(String(8), default="CAD", nullable=False)
    estimated_price: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[str | None] = mapped_column(String(16))
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    product: Mapped[Product] = relationship("Product", back_populates="price_records")

    def __repr__(self) -> str:
        return f"<PriceRecord product={self.product_id} {self.price_type} {self.estimated_price} {self.currency}>"
