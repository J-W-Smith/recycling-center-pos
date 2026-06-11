from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

import json

import pytest

from app.db import (
    REQUIRE_OPERATOR_PIN_ADMIN_KEY,
    create_manager_pin,
    create_operator,
    create_transaction,
    get_material_by_key,
    set_bool_setting,
    set_operator_pin,
    void_transaction,
)
from app.models import LineItemInput, TransactionInput
from app.reports import (
    export_daily_report_csv,
    export_feet_closeout_csv,
    export_feet_closeout_pdf,
    generate_daily_report,
    generate_feet_closeout_report,
    record_feet_closeout,
    render_daily_report_html,
)


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
    assert report["total_transactions"] == 2
    assert report["total_crv_paid_cents"] == 125
    assert report["total_non_crv_paid_cents"] == 320
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
    assert report["voided_transactions"][0]["approved_by"] == "Test Operator (TO)"
    assert report["voided_transactions"][0]["line_total_cents"] == 50


def test_feet_closeout_totals_exports_and_snapshot(
    conn: sqlite3.Connection, operator_id: int, tmp_path
) -> None:
    create_manager_pin(conn, "1234", operator="Test Operator (TO)")
    aluminum = get_material_by_key(conn, "aluminum_crv_count_small")
    scrap = get_material_by_key(conn, "scrap_aluminum_weight")
    plastic = get_material_by_key(conn, "plastic_crv_count_small")
    create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(aluminum.id, Decimal("10"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 9, 0, 0),
    )
    create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(scrap.id, Decimal("4"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 10, 0, 0),
    )
    voided_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(plastic.id, Decimal("10"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 11, 0, 0),
    )
    void_transaction(
        conn,
        voided_id,
        "duplicate ticket",
        acting_operator_id=operator_id,
        manager_pin="1234",
        operator="Test Operator (TO)",
    )

    report = generate_feet_closeout_report(
        conn,
        "2026-06-04",
        business_name="Demo Recycling",
        expected_cash_cents=370,
        actual_cash_cents=365,
        discrepancy_notes="short drawer review",
        operator_attestation="Operator reviewed totals",
        manager_approval="Manager approved",
    )
    closeout_id = record_feet_closeout(
        conn,
        report,
        generated_by_operator_id=operator_id,
        manager_pin="1234",
        operator_label="Test Operator (TO)",
    )
    csv_path = export_feet_closeout_csv(report, tmp_path / "feet.csv")
    pdf_path = export_feet_closeout_pdf(report, tmp_path / "feet.pdf")
    row = conn.execute(
        "SELECT * FROM feet_closeout_reports WHERE id = ?", (closeout_id,)
    ).fetchone()
    snapshot = json.loads(row["report_snapshot_json"])

    assert report["total_transactions"] == 2
    assert report["total_paid_cents"] == 370
    assert report["total_crv_paid_cents"] == 50
    assert report["total_non_crv_paid_cents"] == 320
    assert report["void_count"] == 1
    assert report["voided_total_cents"] == 50
    assert report["discrepancy_cents"] == -5
    assert snapshot["business_name"] == "Demo Recycling"
    assert snapshot["total_paid_cents"] == 370
    assert "FEET End-of-Day Closeout,2026-06-04" in csv_path.read_text(encoding="utf-8")
    assert pdf_path.read_bytes().startswith(b"%PDF-1.4")


def test_feet_closeout_permission_and_operator_pin_enforcement(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    create_manager_pin(conn, "1234", operator="Test Operator (TO)")
    plain_operator_id = create_operator(
        conn,
        display_name="Plain Operator",
        initials="PO",
        role="operator",
        audit=False,
    )
    report = generate_feet_closeout_report(conn, "2026-06-04")

    with pytest.raises(PermissionError):
        record_feet_closeout(
            conn,
            report,
            generated_by_operator_id=plain_operator_id,
            manager_pin="1234",
        )

    set_operator_pin(conn, operator_id, "9999", audit=False)
    set_bool_setting(conn, REQUIRE_OPERATOR_PIN_ADMIN_KEY, True, audit=False)
    with pytest.raises(PermissionError):
        record_feet_closeout(
            conn,
            report,
            generated_by_operator_id=operator_id,
            manager_pin="1234",
            operator_verified=False,
        )

    assert record_feet_closeout(
        conn,
        report,
        generated_by_operator_id=operator_id,
        manager_pin="1234",
        operator_verified=True,
    )
