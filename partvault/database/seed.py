from __future__ import annotations

from partvault.database.connection import get_session
from partvault.inventory.models import Category, Product, ProductAlias

CATEGORIES: list[dict] = [
    {"name": "Graphics Cards", "slug": "gpu"},
    {"name": "Processors", "slug": "cpu"},
    {"name": "Motherboards", "slug": "motherboard"},
    {"name": "Memory", "slug": "ram"},
    {"name": "Storage", "slug": "storage"},
    {"name": "Power Supplies", "slug": "psu"},
    {"name": "Cases", "slug": "case"},
    {"name": "Cooling", "slug": "cooling"},
    {"name": "Monitors", "slug": "monitor"},
    {"name": "Peripherals", "slug": "peripheral"},
    {"name": "Networking", "slug": "networking"},
    {"name": "Miscellaneous", "slug": "misc"},
]

# Seed products: (category_slug, manufacturer, model, variant, aliases)
SEED_PRODUCTS: list[tuple[str, str, str, str | None, list[str]]] = [
    # GPUs
    ("gpu", "AMD", "Radeon RX 9070 XT", None, ["9070xt", "rx9070xt", "rx 9070 xt", "9070 xt"]),
    ("gpu", "AMD", "Radeon RX 9070", None, ["9070", "rx9070", "rx 9070"]),
    ("gpu", "AMD", "Radeon RX 7900 XTX", None, ["7900xtx", "rx7900xtx", "rx 7900 xtx"]),
    ("gpu", "AMD", "Radeon RX 7900 XT", None, ["7900xt", "rx7900xt"]),
    ("gpu", "AMD", "Radeon RX 7800 XT", None, ["7800xt", "rx7800xt"]),
    ("gpu", "AMD", "Radeon RX 7700 XT", None, ["7700xt", "rx7700xt"]),
    ("gpu", "NVIDIA", "GeForce RTX 5090", None, ["5090", "rtx5090", "rtx 5090"]),
    ("gpu", "NVIDIA", "GeForce RTX 5080", None, ["5080", "rtx5080", "rtx 5080"]),
    ("gpu", "NVIDIA", "GeForce RTX 5070 Ti", None, ["5070ti", "rtx5070ti", "rtx 5070 ti"]),
    ("gpu", "NVIDIA", "GeForce RTX 5070", None, ["5070", "rtx5070", "rtx 5070"]),
    ("gpu", "NVIDIA", "GeForce RTX 4090", None, ["4090", "rtx4090", "rtx 4090"]),
    ("gpu", "NVIDIA", "GeForce RTX 4080 Super", None, ["4080s", "rtx4080s", "rtx 4080 super", "4080 super"]),
    ("gpu", "NVIDIA", "GeForce RTX 4080", None, ["4080", "rtx4080", "rtx 4080"]),
    ("gpu", "NVIDIA", "GeForce RTX 4070 Ti Super", None, ["4070tis", "rtx 4070 ti super", "4070 ti super"]),
    ("gpu", "NVIDIA", "GeForce RTX 4070 Ti", None, ["4070ti", "rtx4070ti", "rtx 4070 ti"]),
    ("gpu", "NVIDIA", "GeForce RTX 4070 Super", None, ["4070s", "rtx 4070 super", "4070 super"]),
    ("gpu", "NVIDIA", "GeForce RTX 4070", None, ["4070", "rtx4070", "rtx 4070"]),
    ("gpu", "NVIDIA", "GeForce RTX 4060 Ti", None, ["4060ti", "rtx4060ti", "rtx 4060 ti"]),
    ("gpu", "NVIDIA", "GeForce RTX 4060", None, ["4060", "rtx4060", "rtx 4060"]),
    # CPUs
    ("cpu", "AMD", "Ryzen 9 9950X", None, ["9950x", "r9 9950x"]),
    ("cpu", "AMD", "Ryzen 9 9900X", None, ["9900x", "r9 9900x"]),
    ("cpu", "AMD", "Ryzen 9 9800X3D", None, ["9800x3d", "r9 9800x3d", "ryzen 9800x3d"]),
    ("cpu", "AMD", "Ryzen 7 9700X", None, ["9700x", "r7 9700x"]),
    ("cpu", "AMD", "Ryzen 7 7800X3D", None, ["7800x3d", "r7 7800x3d", "ryzen 7800x3d"]),
    ("cpu", "AMD", "Ryzen 9 7950X3D", None, ["7950x3d", "r9 7950x3d"]),
    ("cpu", "AMD", "Ryzen 9 7900X3D", None, ["7900x3d", "r9 7900x3d"]),
    ("cpu", "Intel", "Core i9-14900K", None, ["i9-14900k", "14900k", "i9 14900k"]),
    ("cpu", "Intel", "Core i9-14900KF", None, ["i9-14900kf", "14900kf"]),
    ("cpu", "Intel", "Core i7-14700K", None, ["i7-14700k", "14700k"]),
    ("cpu", "Intel", "Core i5-14600K", None, ["i5-14600k", "14600k"]),
    ("cpu", "Intel", "Core Ultra 9 285K", None, ["285k", "ultra 9 285k", "core ultra 285k"]),
    ("cpu", "Intel", "Core Ultra 7 265K", None, ["265k", "ultra 7 265k"]),
    # Storage
    ("storage", "Samsung", "990 PRO 1TB", None, ["990 pro 1tb", "samsung 990 pro 1tb", "990pro 1tb"]),
    ("storage", "Samsung", "990 PRO 2TB", None, ["990 pro 2tb", "samsung 990 pro 2tb", "990pro 2tb"]),
    ("storage", "Samsung", "990 PRO 4TB", None, ["990 pro 4tb", "samsung 990 pro 4tb", "990pro 4tb"]),
    ("storage", "Samsung", "980 PRO 1TB", None, ["980 pro 1tb", "samsung 980 pro 1tb"]),
    ("storage", "Samsung", "980 PRO 2TB", None, ["980 pro 2tb", "samsung 980 pro 2tb"]),
    ("storage", "WD", "Black SN850X 1TB", None, ["sn850x 1tb", "wd sn850x 1tb", "sn850x1tb"]),
    ("storage", "WD", "Black SN850X 2TB", None, ["sn850x 2tb", "wd sn850x 2tb"]),
    ("storage", "WD", "Black SN850X 4TB", None, ["sn850x 4tb", "wd sn850x 4tb"]),
    ("storage", "Seagate", "FireCuda 530 1TB", None, ["firecuda 530 1tb", "fc530 1tb"]),
    ("storage", "Seagate", "FireCuda 530 2TB", None, ["firecuda 530 2tb", "fc530 2tb"]),
    # RAM
    ("ram", "Corsair", "Vengeance DDR5 32GB Kit", None, ["corsair vengeance 32gb ddr5", "vengeance 32gb ddr5"]),
    ("ram", "Corsair", "Vengeance DDR5 64GB Kit", None, ["corsair vengeance 64gb ddr5", "vengeance 64gb ddr5"]),
    ("ram", "G.Skill", "Trident Z5 DDR5 32GB Kit", None, ["trident z5 32gb", "trident z5 ddr5 32gb"]),
    ("ram", "G.Skill", "Trident Z5 DDR5 64GB Kit", None, ["trident z5 64gb", "trident z5 ddr5 64gb"]),
    ("ram", "Kingston", "Fury Beast DDR5 32GB Kit", None, ["fury beast 32gb ddr5", "kingston fury beast ddr5 32gb"]),
]


def seed_database() -> None:
    with get_session() as session:
        # Seed categories
        category_map: dict[str, Category] = {}
        for cat_data in CATEGORIES:
            existing = session.query(Category).filter_by(slug=cat_data["slug"]).first()
            if not existing:
                cat = Category(name=cat_data["name"], slug=cat_data["slug"])
                session.add(cat)
                session.flush()
                category_map[cat_data["slug"]] = cat
            else:
                category_map[cat_data["slug"]] = existing

        # Seed products and aliases
        for slug, manufacturer, model, variant, aliases in SEED_PRODUCTS:
            category = category_map.get(slug)
            if not category:
                continue
            existing_product = (
                session.query(Product)
                .filter_by(manufacturer=manufacturer, model=model, variant=variant)
                .first()
            )
            if not existing_product:
                product = Product(
                    category_id=category.id,
                    manufacturer=manufacturer,
                    model=model,
                    variant=variant,
                )
                session.add(product)
                session.flush()
            else:
                product = existing_product

            # Add aliases
            for alias_text in aliases:
                normalized = alias_text.lower().strip()
                existing_alias = (
                    session.query(ProductAlias)
                    .filter_by(alias_text=normalized)
                    .first()
                )
                if not existing_alias:
                    session.add(ProductAlias(product_id=product.id, alias_text=normalized))
