from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

from app.db import create_manager_pin, create_transaction, get_material_by_key, void_transaction
from app.models import LineItemInput, TransactionInput
from app.reports import export_daily_report_csv, generate_daily_report, render_daily_report_html


def test_daily_report_grouping_by_material_type(
    conn: sqlite3.Connection, operator_id: int, tmp_path
) -> None:
    aluminum = get_material_by_key(conn, "aluminum_crv_count_small")
    scrap = get_material_by_key(conn, "scrap_aluminum_weight")

    create_transaction(
        conn,
        TransactionInput(
            line_items=[
                LineItemInput(aluminum.id, Decimal("10")),
                LineItemInput(scrap.id, Decimal("4")),
            ],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 9, 0, 0),
    )
    create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(aluminum.id, Decimal("15"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 13, 0, 0),
    )

    report = generate_daily_report(conn, date(2026, 6, 4))
    groups = {group["description"]: group for group in report["groups"]}

    assert groups["Aluminum CRV by count, small container"]["quantity_total"] == "25"
    assert groups["Aluminum CRV by count, small container"]["total_cents"] == 125
    assert groups["Aluminum CRV by count, small container"]["transaction_count"] == 2
    assert groups["Scrap aluminum by weight, non-CRV"]["quantity_total"] == "4"
    assert groups["Scrap aluminum by weight, non-CRV"]["total_cents"] == 320
    assert report["grand_total_cents"] == 445
    assert report["operator_summaries"][0]["operator_label"] == "Test Operator (TO)"
    assert report["operator_summaries"][0]["transaction_count"] == 2

    csv_path = export_daily_report_csv(report, tmp_path / "daily.csv")
    html = render_daily_report_html(report)

    assert csv_path.read_text(encoding="utf-8").startswith("Daily Report,2026-06-04")
    assert "Grand Total: $4.45" in html


def test_voided_transactions_excluded_and_separately_shown(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    create_manager_pin(conn, "1234", operator="Test Operator (TO)")
    material = get_material_by_key(conn, "plastic_crv_count_small")
    active_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("10"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 14, 0, 0),
    )
    voided_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("10"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 15, 0, 0),
    )
    void_transaction(
        conn,
        voided_id,
        "duplicate ticket",
        acting_operator_id=operator_id,
        manager_pin="1234",
        operator="Test Operator (TO)",
    )

    report = generate_daily_report(conn, "2026-06-04")

    assert active_id
    assert report["grand_total_cents"] == 50
    assert report["void_count"] == 1
    assert report["voided_total_cents"] == 50
    assert len(report["voided_transactions"]) == 1
    assert report["voided_transactions"][0]["transaction_id"] == voided_id
    assert report["voided_transactions"][0]["operator"] == "Test Operator (TO)"
    assert report["voided_transactions"][0]["line_total_cents"] == 50
