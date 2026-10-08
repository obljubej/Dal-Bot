import pytest

from partvault.inventory.matcher import find_product, infer_category


class TestFindProduct:
    def test_exact_alias_match(self, session):
        result = find_product(session, "9070xt")
        assert result is not None
        assert "9070 XT" in result.product.model or "9070 XT" in result.product.display_name
        assert result.matched_via == "alias_exact"
        assert result.score == 100.0

    def test_case_insensitive_alias(self, session):
        result = find_product(session, "9070XT")
        assert result is not None

    def test_alias_with_spaces(self, session):
        result = find_product(session, "rx 9070 xt")
        assert result is not None

    def test_fuzzy_alias_match(self, session):
        # "9800x3d" is a seeded alias for Ryzen 9 9800X3D
        result = find_product(session, "9800x3d")
        assert result is not None
        assert "9800X3D" in result.product.model

    def test_no_match_for_garbage(self, session):
        result = find_product(session, "zzz not a real product xyzzy 99999")
        assert result is None

    def test_samsung_990_pro_1tb(self, session):
        result = find_product(session, "samsung 990 pro 1tb")
        assert result is not None
        assert "990 PRO 1TB" in result.product.model

    def test_ryzen_9800x3d_fuzzy(self, session):
        result = find_product(session, "ryzen 9800x3d")
        assert result is not None

    def test_rtx_4090(self, session):
        result = find_product(session, "rtx 4090")
        assert result is not None
        assert "4090" in result.product.model


class TestInferCategory:
    def test_gpu_keywords(self, session):
        cat = infer_category(session, "rtx 4090 graphics card")
        assert cat is not None
        assert cat.slug == "gpu"

    def test_cpu_keywords(self, session):
        cat = infer_category(session, "ryzen 9800x3d processor")
        assert cat is not None
        assert cat.slug == "cpu"

    def test_storage_keywords(self, session):
        cat = infer_category(session, "samsung 990 pro ssd 1tb nvme")
        assert cat is not None
        assert cat.slug == "storage"

    def test_ram_keywords(self, session):
        cat = infer_category(session, "32gb ddr5 ram kit")
        assert cat is not None
        assert cat.slug == "ram"

    def test_unknown_returns_none(self, session):
        cat = infer_category(session, "something totally unknown zzzz")
        assert cat is None
