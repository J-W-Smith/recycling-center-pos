from __future__ import annotations

import sqlite3


SEED_MATERIALS = [
    {
        "key": "aluminum_crv_weight",
        "display_name": "Aluminum CRV by weight",
        "category": "Aluminum CRV",
        "crv_eligible": 1,
        "unit_type": "weight",
        "default_rate_cents_per_unit": 165,
        "report_grouping": "CRV Aluminum",
        "rate_kind": "weight",
        "notes": "Planning placeholder. Verify current certified CRV per-pound rate.",
    },
    {
        "key": "plastic_crv_weight",
        "display_name": "Plastic CRV by weight",
        "category": "Plastic CRV",
        "crv_eligible": 1,
        "unit_type": "weight",
        "default_rate_cents_per_unit": 130,
        "report_grouping": "CRV Plastic",
        "rate_kind": "weight",
        "notes": "Planning placeholder. Verify current certified CRV per-pound rate.",
    },
    {
        "key": "glass_crv_weight",
        "display_name": "Glass CRV by weight",
        "category": "Glass CRV",
        "crv_eligible": 1,
        "unit_type": "weight",
        "default_rate_cents_per_unit": 12,
        "report_grouping": "CRV Glass",
        "rate_kind": "weight",
        "notes": "Planning placeholder. Verify current certified CRV per-pound rate.",
    },
    {
        "key": "aluminum_crv_count_small",
        "display_name": "Aluminum CRV by count, small container",
        "category": "Aluminum CRV",
        "crv_eligible": 1,
        "unit_type": "count",
        "default_rate_cents_per_unit": 5,
        "report_grouping": "CRV Aluminum",
        "rate_kind": "count_small",
        "notes": "Initial CRV assumption: containers less than 24 ounces.",
    },
    {
        "key": "plastic_crv_count_small",
        "display_name": "Plastic CRV by count, small container",
        "category": "Plastic CRV",
        "crv_eligible": 1,
        "unit_type": "count",
        "default_rate_cents_per_unit": 5,
        "report_grouping": "CRV Plastic",
        "rate_kind": "count_small",
        "notes": "Initial CRV assumption: containers less than 24 ounces.",
    },
    {
        "key": "glass_crv_count_small",
        "display_name": "Glass CRV by count, small container",
        "category": "Glass CRV",
        "crv_eligible": 1,
        "unit_type": "count",
        "default_rate_cents_per_unit": 5,
        "report_grouping": "CRV Glass",
        "rate_kind": "count_small",
        "notes": "Initial CRV assumption: containers less than 24 ounces.",
    },
    {
        "key": "large_crv_count",
        "display_name": "Large CRV container by count",
        "category": "CRV Large",
        "crv_eligible": 1,
        "unit_type": "count",
        "default_rate_cents_per_unit": 10,
        "report_grouping": "CRV Large Containers",
        "rate_kind": "count_large",
        "notes": "Initial CRV assumption: containers 24 ounces or larger.",
    },
    {
        "key": "wine_liquor_box_pouch_count",
        "display_name": "Wine/liquor box/pouch CRV by count",
        "category": "Wine/Liquor CRV",
        "crv_eligible": 1,
        "unit_type": "count",
        "default_rate_cents_per_unit": 25,
        "report_grouping": "CRV Wine/Liquor",
        "rate_kind": "count_wine_liquor_box_pouch",
        "notes": "Initial CRV assumption for eligible boxes, bladders, or pouches.",
    },
    {
        "key": "scrap_aluminum_weight",
        "display_name": "Scrap aluminum by weight, non-CRV",
        "category": "Scrap Metal",
        "crv_eligible": 0,
        "unit_type": "weight",
        "default_rate_cents_per_unit": 80,
        "report_grouping": "Non-CRV Scrap Aluminum",
        "rate_kind": "weight",
        "notes": "Planning placeholder. Replace with shop rate.",
    },
    {
        "key": "custom_manual_payout",
        "display_name": "Custom/manual payout",
        "category": "Manual",
        "crv_eligible": 0,
        "unit_type": "manual",
        "default_rate_cents_per_unit": 100,
        "report_grouping": "Manual Adjustments",
        "rate_kind": "manual",
        "notes": "Manual payout records should require operator notes in production.",
    },
]


def seed_materials(conn: sqlite3.Connection, effective_from: str = "2026-01-01") -> None:
    with conn:
        for item in SEED_MATERIALS:
            conn.execute(
                """
                INSERT INTO material_types (
                    key, display_name, category, crv_eligible, unit_type,
                    default_rate_cents_per_unit, report_grouping, active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(key) DO UPDATE SET
                    display_name = excluded.display_name,
                    category = excluded.category,
                    crv_eligible = excluded.crv_eligible,
                    unit_type = excluded.unit_type,
                    default_rate_cents_per_unit = excluded.default_rate_cents_per_unit,
                    report_grouping = excluded.report_grouping,
                    active = excluded.active
                """,
                (
                    item["key"],
                    item["display_name"],
                    item["category"],
                    item["crv_eligible"],
                    item["unit_type"],
                    item["default_rate_cents_per_unit"],
                    item["report_grouping"],
                ),
            )
            material_id = conn.execute(
                "SELECT id FROM material_types WHERE key = ?", (item["key"],)
            ).fetchone()["id"]
            existing = conn.execute(
                """
                SELECT id FROM rates
                WHERE material_type_id = ? AND effective_from = ? AND effective_to IS NULL
                """,
                (material_id, effective_from),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO rates (
                        material_type_id, rate_kind, rate_cents_per_unit,
                        effective_from, effective_to, notes
                    )
                    VALUES (?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        material_id,
                        item["rate_kind"],
                        item["default_rate_cents_per_unit"],
                        effective_from,
                        item["notes"],
                    ),
                )

