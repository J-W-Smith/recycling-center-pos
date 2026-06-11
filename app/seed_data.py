from __future__ import annotations

import json
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
        "sort_order": 10,
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
        "sort_order": 20,
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
        "sort_order": 30,
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
        "sort_order": 40,
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
        "sort_order": 50,
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
        "sort_order": 60,
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
        "sort_order": 70,
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
        "sort_order": 80,
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
        "sort_order": 90,
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
        "sort_order": 100,
    },
]


CA_CRV_PACK = {
    "pack_key": "ca_crv",
    "display_name": "California CRV Compliance Pack",
    "jurisdiction": "California",
    "version": "2026.06-planning",
    "description": (
        "Configurable support rules for California CRV redemption workflows. "
        "Review current CalRecycle guidance and certification requirements before production use."
    ),
    "source_notes": (
        "Initial defaults reflect CalRecycle public guidance reviewed 2026-06-11: "
        "5/10/25 cent count refund values, count-payment request limits, CRV daily load "
        "limits, and recordkeeping expectations. This is compliance support only."
    ),
}


CA_CRV_RULES = [
    {
        "rule_key": "count_refund_small_container",
        "display_name": "CRV count refund: less than 24 oz",
        "rule_type": "payout_value",
        "severity": "info",
        "config": {
            "unit_type": "count",
            "refund_cents": 5,
            "container_size": "less_than_24_oz",
            "material_keys": [
                "aluminum_crv_count_small",
                "plastic_crv_count_small",
                "glass_crv_count_small",
            ],
        },
    },
    {
        "rule_key": "count_refund_large_container",
        "display_name": "CRV count refund: 24 oz or larger",
        "rule_type": "payout_value",
        "severity": "info",
        "config": {
            "unit_type": "count",
            "refund_cents": 10,
            "container_size": "24_oz_or_larger",
            "material_keys": ["large_crv_count"],
        },
    },
    {
        "rule_key": "count_refund_wine_liquor_box_pouch",
        "display_name": "CRV count refund: wine/liquor box or pouch",
        "rule_type": "payout_value",
        "severity": "info",
        "config": {
            "unit_type": "count",
            "refund_cents": 25,
            "container_categories": [
                "bag-in-box",
                "multi-layer pouch",
                "paperboard carton",
                "plastic pouch",
            ],
            "material_keys": ["wine_liquor_box_pouch_count"],
        },
    },
    {
        "rule_key": "daily_load_limit_aluminum",
        "display_name": "Daily CRV load limit: aluminum",
        "rule_type": "daily_load_limit",
        "severity": "warning",
        "config": {
            "report_grouping": "CRV Aluminum",
            "unit_type": "weight",
            "limit_quantity": "100",
            "unit_label": "lb",
        },
    },
    {
        "rule_key": "daily_load_limit_plastic",
        "display_name": "Daily CRV load limit: plastic",
        "rule_type": "daily_load_limit",
        "severity": "warning",
        "config": {
            "report_grouping": "CRV Plastic",
            "unit_type": "weight",
            "limit_quantity": "100",
            "unit_label": "lb",
        },
    },
    {
        "rule_key": "daily_load_limit_glass",
        "display_name": "Daily CRV load limit: glass",
        "rule_type": "daily_load_limit",
        "severity": "warning",
        "config": {
            "report_grouping": "CRV Glass",
            "unit_type": "weight",
            "limit_quantity": "1000",
            "unit_label": "lb",
        },
    },
    {
        "rule_key": "daily_load_limit_bag_in_box",
        "display_name": "Daily CRV load limit: bag-in-box",
        "rule_type": "daily_load_limit",
        "severity": "warning",
        "config": {
            "report_grouping": "CRV Bag-in-Box",
            "unit_type": "weight",
            "limit_quantity": "50",
            "unit_label": "lb",
        },
    },
    {
        "rule_key": "daily_load_limit_multilayer_pouch",
        "display_name": "Daily CRV load limit: multilayer pouches",
        "rule_type": "daily_load_limit",
        "severity": "warning",
        "config": {
            "report_grouping": "CRV Multilayer Pouches",
            "unit_type": "weight",
            "limit_quantity": "25",
            "unit_label": "lb",
        },
    },
    {
        "rule_key": "daily_load_limit_paperboard_carton",
        "display_name": "Daily CRV load limit: paperboard cartons",
        "rule_type": "daily_load_limit",
        "severity": "warning",
        "config": {
            "report_grouping": "CRV Paperboard Cartons",
            "unit_type": "weight",
            "limit_quantity": "25",
            "unit_label": "lb",
        },
    },
    {
        "rule_key": "count_payment_limit_standard_crv",
        "display_name": "CRV count-payment request limit",
        "rule_type": "count_payment_limit",
        "severity": "warning",
        "config": {
            "limit_quantity": "50",
            "unit_label": "containers",
            "material_keys": [
                "aluminum_crv_count_small",
                "plastic_crv_count_small",
                "glass_crv_count_small",
                "large_crv_count",
            ],
            "message_note": (
                "Customers may request per-container payment up to the configured "
                "limit for each material type per transaction."
            ),
        },
    },
    {
        "rule_key": "count_payment_limit_wine_spirits",
        "display_name": "Wine/liquor count-payment request limit",
        "rule_type": "count_payment_limit",
        "severity": "warning",
        "config": {
            "limit_quantity": "25",
            "unit_label": "containers",
            "material_keys": ["wine_liquor_box_pouch_count"],
            "message_note": (
                "Special wine and distilled spirits bag-in-box, multilayer pouch, "
                "and paperboard carton limits require final review."
            ),
        },
    },
    {
        "rule_key": "crv_recordkeeping_required",
        "display_name": "CRV transaction recordkeeping required",
        "rule_type": "audit_requirement",
        "severity": "block",
        "config": {
            "requires_operator_snapshot": True,
            "requires_receipt_snapshot": True,
            "message": "CRV transactions require operator and receipt snapshots.",
        },
    },
    {
        "rule_key": "new_crv_categories_acceptance_note",
        "display_name": "New CRV categories acceptance note",
        "rule_type": "warning",
        "severity": "info",
        "config": {
            "message": (
                "Newer CRV beverage/container categories and labeling rules may affect "
                "acceptance workflows. Certified centers should review current CalRecycle guidance."
            )
        },
    },
    {
        "rule_key": "receipt_disclosure_ca_crv",
        "display_name": "California CRV receipt disclosure",
        "rule_type": "receipt_disclosure",
        "severity": "info",
        "config": {
            "text": (
                "California CRV Compliance Pack enabled. Payout based on configured "
                "material/rate rules. Not a compliance certification."
            )
        },
    },
    {
        "rule_key": "report_disclosure_ca_crv",
        "display_name": "California CRV report disclosure",
        "rule_type": "report_requirement",
        "severity": "info",
        "config": {
            "text": (
                "California CRV compliance pack enabled. Review daily load limits, "
                "count-payment requests, and recordkeeping requirements. Not compliance-certified."
            )
        },
    },
]


CA_CRV_MATERIAL_KEYS = [
    "aluminum_crv_weight",
    "plastic_crv_weight",
    "glass_crv_weight",
    "aluminum_crv_count_small",
    "plastic_crv_count_small",
    "glass_crv_count_small",
    "large_crv_count",
    "wine_liquor_box_pouch_count",
]


def seed_materials(conn: sqlite3.Connection, effective_from: str = "2026-01-01") -> None:
    with conn:
        for item in SEED_MATERIALS:
            conn.execute(
                """
                INSERT INTO material_types (
                    key, display_name, category, crv_eligible, unit_type,
                    default_rate_cents_per_unit, report_grouping, active, sort_order, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(key) DO NOTHING
                """,
                (
                    item["key"],
                    item["display_name"],
                    item["category"],
                    item["crv_eligible"],
                    item["unit_type"],
                    item["default_rate_cents_per_unit"],
                    item["report_grouping"],
                    item["sort_order"],
                    item["notes"],
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
                        effective_from, effective_to, notes, active
                    )
                    VALUES (?, ?, ?, ?, NULL, ?, 1)
                    """,
                    (
                        material_id,
                        item["rate_kind"],
                        item["default_rate_cents_per_unit"],
                        effective_from,
                        item["notes"],
                    ),
                )
        seed_california_crv_pack(conn, effective_from=effective_from)


def seed_california_crv_pack(
    conn: sqlite3.Connection, effective_from: str = "2026-01-01"
) -> int:
    conn.execute(
        """
        INSERT INTO compliance_packs (
            pack_key, display_name, jurisdiction, version, description, source_notes,
            enabled, built_in, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(pack_key) DO UPDATE SET
            display_name = excluded.display_name,
            jurisdiction = excluded.jurisdiction,
            version = excluded.version,
            description = excluded.description,
            source_notes = excluded.source_notes,
            built_in = 1,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            CA_CRV_PACK["pack_key"],
            CA_CRV_PACK["display_name"],
            CA_CRV_PACK["jurisdiction"],
            CA_CRV_PACK["version"],
            CA_CRV_PACK["description"],
            CA_CRV_PACK["source_notes"],
        ),
    )
    row = conn.execute(
        "SELECT id FROM compliance_packs WHERE pack_key = ?",
        (CA_CRV_PACK["pack_key"],),
    ).fetchone()
    pack_id = int(row["id"])
    for rule in CA_CRV_RULES:
        conn.execute(
            """
            INSERT INTO compliance_rules (
                pack_id, rule_key, display_name, rule_type, severity, config_json,
                enabled, effective_start_date, effective_end_date, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(pack_id, rule_key) DO UPDATE SET
                display_name = excluded.display_name,
                rule_type = excluded.rule_type,
                severity = excluded.severity,
                config_json = excluded.config_json,
                effective_start_date = excluded.effective_start_date,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                pack_id,
                rule["rule_key"],
                rule["display_name"],
                rule["rule_type"],
                rule["severity"],
                json.dumps(rule["config"], sort_keys=True),
                effective_from,
            ),
        )
    for material_key in CA_CRV_MATERIAL_KEYS:
        material = conn.execute(
            "SELECT id FROM material_types WHERE key = ?", (material_key,)
        ).fetchone()
        if material is None:
            continue
        conn.execute(
            """
            INSERT INTO material_pack_links (
                pack_id, material_type_id, required, enabled_by_default, enabled,
                notes, created_at, updated_at
            )
            VALUES (?, ?, 0, 1, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(pack_id, material_type_id) DO UPDATE SET
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                pack_id,
                int(material["id"]),
                "Seeded California CRV material link. Disable to hide for new transactions.",
            ),
        )
    return pack_id
