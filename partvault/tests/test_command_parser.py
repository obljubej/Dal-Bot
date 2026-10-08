import pytest

from partvault.inventory.matcher import parse_quick_command


class TestParseQuickCommand:
    def test_add_basic(self):
        result = parse_quick_command("+4 9070xt")
        assert result is not None
        assert result.action == "add"
        assert result.quantity == 4
        assert result.product_query == "9070xt"
        assert result.condition == "used"

    def test_remove_basic(self):
        result = parse_quick_command("-2 9070xt")
        assert result is not None
        assert result.action == "remove"
        assert result.quantity == 2
        assert result.product_query == "9070xt"

    def test_add_multiword_product(self):
        result = parse_quick_command("+1 samsung 990 pro 1tb")
        assert result is not None
        assert result.action == "add"
        assert result.quantity == 1
        assert result.product_query == "samsung 990 pro 1tb"

    def test_condition_prefix_new(self):
        result = parse_quick_command("+2 new rtx 4090")
        assert result is not None
        assert result.condition == "new"
        assert result.product_query == "rtx 4090"

    def test_condition_prefix_broken(self):
        result = parse_quick_command("+1 broken rx 7900 xtx")
        assert result is not None
        assert result.condition == "broken"
        assert result.product_query == "rx 7900 xtx"

    def test_condition_prefix_refurb(self):
        result = parse_quick_command("+3 refurb corsair psu")
        assert result is not None
        assert result.condition == "refurbished"
        assert result.product_query == "corsair psu"

    def test_no_match_plain_text(self):
        assert parse_quick_command("hello world") is None

    def test_no_match_missing_quantity(self):
        assert parse_quick_command("+ 9070xt") is None

    def test_no_match_zero_quantity(self):
        assert parse_quick_command("+0 9070xt") is None

    def test_whitespace_trimmed(self):
        result = parse_quick_command("  +1   ryzen 9800x3d  ")
        assert result is not None
        assert result.product_query == "ryzen 9800x3d"

    def test_large_quantity(self):
        result = parse_quick_command("+100 some part")
        assert result is not None
        assert result.quantity == 100
