from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal

import pytest

from app.db import (
    add_rate,
    create_material_type,
    create_transaction,
    fetch_transaction,
    get_current_rate,
    get_material,
    get_material_by_key,
    list_materials,
    rate_overlaps,
    set_material_active,
)
from app.models import LineItemInput, TransactionInput
from app.reports import generate_daily_report
from app.seed_data import seed_materials


def test_create_custom_material_type(conn: sqlite3.Connection) -> None:
    material_id = create_material_type(
        conn,
        display_name="Copper scrap by weight",
        category="Scrap Metal",
        report_grouping="Non-CRV Copper",
        crv_eligible=False,
        unit_type="weight",
        active=True,
        sort_order=5,
        notes="custom shop material",
    )

    material = get_material(conn, material_id)

    assert material.display_name == "Copper scrap by weight"
    assert material.report_grouping == "Non-CRV Copper"
    assert material.unit_type == "weight"
    assert material.sort_order == 5
    assert material.notes == "custom shop material"


def test_deactivate_material_hides_from_active_list_and_blocks_new_transactions(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    material = get_material_by_key(conn, "scrap_aluminum_weight")

    set_material_active(conn, material.id, False)
    seed_materials(conn, effective_from="2026-01-01")

    assert material.id not in {item.id for item in list_materials(conn, active_only=True)}
    assert material.id in {item.id for item in list_materials(conn, active_only=False)}
    with pytest.raises(ValueError, match="inactive"):
        create_transaction(
            conn,
            TransactionInput(
                line_items=[LineItemInput(material.id, Decimal("2"))],
                operator_id=operator_id,
            ),
            created_at=datetime(2026, 6, 4, 9, 0, 0),
        )


def test_add_effective_dated_rate_replaces_current_rate(conn: sqlite3.Connection) -> None:
    material = get_material_by_key(conn, "scrap_aluminum_weight")

    rate_id = add_rate(
        conn,
        material_type_id=material.id,
        rate_cents_per_unit=95,
        effective_from="2026-06-10",
        notes="new shop rate",
        replace_current=True,
    )

    assert rate_id > 0
    assert get_current_rate(conn, material.id, "2026-06-09") == 80
    assert get_current_rate(conn, material.id, "2026-06-10") == 95


def test_overlapping_active_rate_period_is_detected(conn: sqlite3.Connection) -> None:
    material = get_material_by_key(conn, "aluminum_crv_count_small")

    assert rate_overlaps(
        conn,
        material_type_id=material.id,
        effective_from="2026-06-01",
        effective_to="2026-06-30",
    )
    with pytest.raises(ValueError, match="overlaps"):
        add_rate(
            conn,
            material_type_id=material.id,
            rate_cents_per_unit=7,
            effective_from="2026-06-01",
            effective_to="2026-06-30",
            replace_current=False,
        )


def test_transaction_uses_current_effective_rate(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    material = get_material_by_key(conn, "plastic_crv_count_small")
    add_rate(
        conn,
        material_type_id=material.id,
        rate_cents_per_unit=6,
        effective_from="2026-07-01",
        replace_current=True,
    )

    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("10"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 7, 2, 10, 0, 0),
    )

    tx = fetch_transaction(conn, tx_id)
    assert tx["total_cents"] == 60
    assert "Rate: $0.06 per unit" in tx["receipt_snapshot_text"]


def test_receipt_snapshot_does_not_change_after_later_admin_rate_update(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    material = get_material_by_key(conn, "large_crv_count")
    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("3"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 12, 0, 0),
    )
    before = fetch_transaction(conn, tx_id)["receipt_snapshot_text"]

    add_rate(
        conn,
        material_type_id=material.id,
        rate_cents_per_unit=12,
        effective_from="2026-07-01",
        replace_current=True,
    )

    after = fetch_transaction(conn, tx_id)["receipt_snapshot_text"]
    assert after == before
    assert "TOTAL PAID: $0.30" in after


def test_daily_report_includes_custom_material(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    material_id = create_material_type(
        conn,
        display_name="Brass scrap by weight",
        category="Scrap Metal",
        report_grouping="Non-CRV Brass",
        crv_eligible=False,
        unit_type="weight",
    )
    add_rate(
        conn,
        material_type_id=material_id,
        rate_cents_per_unit=120,
        effective_from="2026-06-01",
    )

    create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material_id, Decimal("2.5"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 13, 0, 0),
    )

    report = generate_daily_report(conn, "2026-06-04")
    groups = {group["description"]: group for group in report["groups"]}

    assert groups["Brass scrap by weight"]["report_grouping"] == "Non-CRV Brass"
    assert groups["Brass scrap by weight"]["quantity_total"] == "2.5"
    assert groups["Brass scrap by weight"]["total_cents"] == 300
