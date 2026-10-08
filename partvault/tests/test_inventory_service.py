import pytest

from partvault.database.connection import get_session
from partvault.inventory import service
from partvault.inventory.matcher import find_product
from partvault.inventory.models import Category, Condition


def _get_gpu_product(session):
    result = find_product(session, "9070xt")
    assert result is not None, "Seed product '9070xt' not found"
    return result.product


class TestAddInventory:
    def test_add_increases_quantity(self, session):
        product = _get_gpu_product(session)
        # Start fresh: check current quantity
        results = service.get_inventory(session, include_zero=True)
        before = next(
            (r.item.quantity for r in results if r.product.id == product.id and r.item.condition == Condition.USED),
            0,
        )

        item = service.add_inventory(session, product, quantity=3, condition=Condition.USED)
        assert item.quantity == before + 3

    def test_add_logs_transaction(self, session):
        product = _get_gpu_product(session)
        service.add_inventory(session, product, quantity=1, condition=Condition.USED)
        txs = service.get_transaction_history(session, limit=5, product_id=product.id)
        assert any(tx.action == "add" for tx in txs)

    def test_add_different_conditions_are_separate_items(self, session):
        product = _get_gpu_product(session)
        service.add_inventory(session, product, quantity=1, condition=Condition.NEW)
        service.add_inventory(session, product, quantity=1, condition=Condition.BROKEN)

        results = service.get_inventory(session, include_zero=True)
        product_items = [r for r in results if r.product.id == product.id]
        conditions = {r.item.condition for r in product_items}
        assert Condition.NEW in conditions
        assert Condition.BROKEN in conditions

    def test_add_zero_raises(self, session):
        product = _get_gpu_product(session)
        with pytest.raises(ValueError, match="Quantity must be positive"):
            service.add_inventory(session, product, quantity=0)

    def test_add_negative_raises(self, session):
        product = _get_gpu_product(session)
        with pytest.raises(ValueError):
            service.add_inventory(session, product, quantity=-5)


class TestRemoveInventory:
    def test_remove_decreases_quantity(self, session):
        product = _get_gpu_product(session)
        service.add_inventory(session, product, quantity=5, condition=Condition.USED)

        results = service.get_inventory(session, include_zero=True)
        before = next(
            r.item.quantity for r in results
            if r.product.id == product.id and r.item.condition == Condition.USED
        )

        service.remove_inventory(session, product, quantity=2, condition=Condition.USED)

        results = service.get_inventory(session, include_zero=True)
        after = next(
            r.item.quantity for r in results
            if r.product.id == product.id and r.item.condition == Condition.USED
        )
        assert after == before - 2

    def test_remove_too_many_raises(self, session):
        product = _get_gpu_product(session)
        # Ensure a non-huge starting quantity
        results = service.get_inventory(session, include_zero=True)
        current = next(
            (r.item.quantity for r in results if r.product.id == product.id and r.item.condition == Condition.USED),
            0,
        )
        with pytest.raises(ValueError, match="cannot remove"):
            service.remove_inventory(session, product, quantity=current + 1000, condition=Condition.USED)

    def test_remove_from_nonexistent_raises(self, session):
        product = _get_gpu_product(session)
        with pytest.raises(ValueError):
            # refurbished stock not seeded
            service.remove_inventory(session, product, quantity=1, condition=Condition.REFURBISHED)

    def test_remove_logs_transaction(self, session):
        product = _get_gpu_product(session)
        service.add_inventory(session, product, quantity=2, condition=Condition.USED)
        service.remove_inventory(session, product, quantity=1, condition=Condition.USED)
        txs = service.get_transaction_history(session, limit=10, product_id=product.id)
        assert any(tx.action == "remove" for tx in txs)


class TestGetInventory:
    def test_returns_list(self, session):
        service.add_inventory(session, _get_gpu_product(session), quantity=1)
        results = service.get_inventory(session)
        assert isinstance(results, list)

    def test_zero_quantity_excluded_by_default(self, session):
        results = service.get_inventory(session, include_zero=False)
        assert all(r.item.quantity > 0 for r in results)

    def test_summary_counts(self, session):
        service.add_inventory(session, _get_gpu_product(session), quantity=2)
        summary = service.get_inventory_summary(session)
        assert summary.total_components >= 2
        assert summary.unique_products >= 1


class TestAliases:
    def test_add_alias(self, session):
        product = _get_gpu_product(session)
        alias = service.add_alias(session, product, "my_custom_gpu_alias_xyz")
        assert alias is not None
        assert alias.alias_text == "my_custom_gpu_alias_xyz"

    def test_duplicate_alias_returns_none(self, session):
        product = _get_gpu_product(session)
        service.add_alias(session, product, "dup_alias_test_abc")
        result = service.add_alias(session, product, "dup_alias_test_abc")
        assert result is None
