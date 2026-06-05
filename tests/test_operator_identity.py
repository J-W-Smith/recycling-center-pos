from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal

import pytest

from app.db import (
    add_rate,
    change_manager_pin,
    connect,
    create_manager_pin,
    create_material_type,
    create_operator,
    create_transaction,
    fetch_transaction,
    get_operator,
    get_material_by_key,
    init_db,
    list_audit_entries,
    list_operators,
    set_operator_active,
    update_operator,
)
from app.models import LineItemInput, TransactionInput
from app.reports import generate_daily_report
from app.seed_data import seed_materials


def test_first_operator_creation() -> None:
    conn = connect(":memory:")
    init_db(conn)

    operator_id = create_operator(
        conn,
        display_name="First Manager",
        initials="FM",
        role="manager",
        audit=False,
    )

    operators = list_operators(conn)
    conn.close()
    assert operator_id > 0
    assert operators[0].display_name == "First Manager"
    assert operators[0].initials == "FM"
    assert operators[0].role == "manager"


def test_operator_records_migrate_into_existing_database() -> None:
    conn = connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE transactions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            operator_initials TEXT NOT NULL,
            payout_method TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            total_cents INTEGER NOT NULL DEFAULT 0,
            receipt_snapshot_text TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO transactions (
            id, created_at, operator_initials, payout_method, total_cents
        )
        VALUES ('legacy', '2026-06-04T08:00:00', 'LG', 'cash', 0);
        """
    )

    init_db(conn)

    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'operators'"
        )
    }
    tx = conn.execute("SELECT * FROM transactions WHERE id = 'legacy'").fetchone()
    conn.close()
    assert "operators" in tables
    assert tx["operator_id"] is None
    assert tx["operator_initials_snapshot"] == "LG"


def test_inactive_operators_do_not_appear_in_active_list(conn: sqlite3.Connection) -> None:
    inactive_id = create_operator(
        conn,
        display_name="Inactive Operator",
        initials="IO",
        role="operator",
        active=False,
        audit=False,
    )

    assert inactive_id not in {operator.id for operator in list_operators(conn)}
    assert inactive_id in {operator.id for operator in list_operators(conn, active_only=False)}


def test_transaction_cannot_save_without_operator(conn: sqlite3.Connection) -> None:
    material = get_material_by_key(conn, "aluminum_crv_count_small")

    with pytest.raises(ValueError, match="active operator"):
        create_transaction(
            conn,
            TransactionInput(line_items=[LineItemInput(material.id, Decimal("1"))]),
            created_at=datetime(2026, 6, 4, 9, 0, 0),
        )


def test_transaction_saves_operator_snapshots(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    material = get_material_by_key(conn, "aluminum_crv_count_small")

    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("2"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 9, 0, 0),
    )

    tx = fetch_transaction(conn, tx_id)
    assert tx["operator_id"] == operator_id
    assert tx["operator_display_name_snapshot"] == "Test Operator"
    assert tx["operator_initials_snapshot"] == "TO"
    assert "Operator: Test Operator (TO)" in tx["receipt_snapshot_text"]


def test_renaming_operator_does_not_change_old_receipt_snapshot(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    material = get_material_by_key(conn, "large_crv_count")
    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("1"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 9, 0, 0),
    )
    before = fetch_transaction(conn, tx_id)["receipt_snapshot_text"]

    update_operator(
        conn,
        operator_id,
        display_name="Renamed Operator",
        initials="RO",
        role="manager",
        active=True,
        audit=False,
    )

    after = fetch_transaction(conn, tx_id)["receipt_snapshot_text"]
    assert after == before
    assert "Operator: Test Operator (TO)" in after


def test_daily_report_summarizes_by_operator(conn: sqlite3.Connection, operator_id: int) -> None:
    second_operator_id = create_operator(
        conn,
        display_name="Second Operator",
        initials="SO",
        role="operator",
        audit=False,
    )
    material = get_material_by_key(conn, "plastic_crv_count_small")
    create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("10"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 9, 0, 0),
    )
    create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("20"))],
            operator_id=second_operator_id,
        ),
        created_at=datetime(2026, 6, 4, 10, 0, 0),
    )

    report = generate_daily_report(conn, "2026-06-04")
    summaries = {item["operator_label"]: item for item in report["operator_summaries"]}

    assert summaries["Test Operator (TO)"]["transaction_count"] == 1
    assert summaries["Test Operator (TO)"]["total_cents"] == 50
    assert summaries["Second Operator (SO)"]["transaction_count"] == 1
    assert summaries["Second Operator (SO)"]["total_cents"] == 100


def test_admin_audit_entries_use_selected_operator(conn: sqlite3.Connection) -> None:
    create_manager_pin(conn, "1234", operator="Test Operator (TO)")
    change_manager_pin(conn, "1234", "5678", operator="Test Operator (TO)")
    material_id = create_material_type(
        conn,
        display_name="Audited material",
        category="Audit",
        report_grouping="Audit",
        crv_eligible=False,
        unit_type="manual",
        operator="Test Operator (TO)",
    )
    add_rate(
        conn,
        material_type_id=material_id,
        rate_cents_per_unit=100,
        effective_from="2026-06-01",
        operator="Test Operator (TO)",
    )

    operators = {row["operator"] for row in list_audit_entries(conn)}
    assert "Test Operator (TO)" in operators
    assert "manager" not in operators


def test_deactivating_operator_preserves_historical_transaction(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    create_operator(
        conn,
        display_name="Backup Manager",
        initials="BM",
        role="manager",
        audit=False,
    )
    material = get_material_by_key(conn, "glass_crv_count_small")
    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("5"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 9, 0, 0),
    )

    set_operator_active(conn, operator_id, False, audit=False)

    tx = fetch_transaction(conn, tx_id)
    assert operator_id not in {operator.id for operator in list_operators(conn)}
    assert tx["operator_display_name_snapshot"] == "Test Operator"
    assert tx["operator_initials_snapshot"] == "TO"
    assert "Operator: Test Operator (TO)" in tx["receipt_snapshot_text"]


def test_cannot_deactivate_last_active_manager_admin(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    with pytest.raises(ValueError, match="At least one active manager or admin"):
        set_operator_active(conn, operator_id, False, audit=False)


def test_cannot_demote_last_active_manager_admin(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    with pytest.raises(ValueError, match="At least one active manager or admin"):
        update_operator(
            conn,
            operator_id,
            display_name="Test Operator",
            initials="TO",
            role="operator",
            active=True,
            audit=False,
        )


def test_can_demote_manager_when_another_manager_exists(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    create_operator(
        conn,
        display_name="Backup Manager",
        initials="BM",
        role="admin",
        audit=False,
    )

    update_operator(
        conn,
        operator_id,
        display_name="Test Operator",
        initials="TO",
        role="operator",
        active=True,
        audit=False,
    )

    assert get_operator(conn, operator_id).role == "operator"
