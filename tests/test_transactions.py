from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal

import pytest

from app.db import (
    REQUIRE_OPERATOR_PIN_ADMIN_KEY,
    connect,
    create_manager_pin,
    create_operator,
    create_transaction,
    fetch_transaction,
    get_material_by_key,
    init_db,
    list_audit_entries,
    set_bool_setting,
    set_operator_pin,
    void_transaction,
)
from app.models import LineItemInput, TransactionInput
from app.receipt import mark_voided_receipt_text


def test_mixed_transaction_total(conn: sqlite3.Connection, operator_id: int) -> None:
    small = get_material_by_key(conn, "aluminum_crv_count_small")
    scrap = get_material_by_key(conn, "scrap_aluminum_weight")

    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[
                LineItemInput(small.id, Decimal("10")),
                LineItemInput(scrap.id, Decimal("2.5")),
            ],
            operator_id=operator_id,
            payout_method="cash",
            notes="mixed test",
        ),
        created_at=datetime(2026, 6, 4, 10, 0, 0),
    )

    tx = fetch_transaction(conn, tx_id)
    assert tx["total_cents"] == 250
    assert tx["operator_initials_snapshot"] == "TO"
    assert "TOTAL PAID: $2.50" in tx["receipt_snapshot_text"]


def test_voided_transaction_is_marked_not_deleted(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    create_manager_pin(conn, "1234", operator="Test Operator (TO)")
    material = get_material_by_key(conn, "plastic_crv_count_small")
    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("5"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 11, 0, 0),
    )
    before_receipt = fetch_transaction(conn, tx_id)["receipt_snapshot_text"]

    void_transaction(
        conn,
        tx_id,
        "wrong material",
        acting_operator_id=operator_id,
        manager_pin="1234",
        operator="Test Operator (TO)",
    )
    tx = fetch_transaction(conn, tx_id)

    assert tx["status"] == "voided"
    assert tx["void_reason"] == "wrong material"
    assert tx["voided_by_operator_id"] == operator_id
    assert tx["voided_by_operator_name_snapshot"] == "Test Operator"
    assert tx["receipt_snapshot_text"] == before_receipt
    assert "VOIDED TRANSACTION" in mark_voided_receipt_text(
        tx["receipt_snapshot_text"],
        voided_at=tx["voided_at"],
        reason=tx["void_reason"],
    )


def test_plain_operator_cannot_void_transaction(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    create_manager_pin(conn, "1234", operator="Test Operator (TO)")
    plain_id = create_operator(
        conn,
        display_name="Plain Operator",
        initials="PO",
        role="operator",
        audit=False,
    )
    material = get_material_by_key(conn, "plastic_crv_count_small")
    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("5"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 11, 0, 0),
    )

    with pytest.raises(PermissionError, match="cannot void"):
        void_transaction(
            conn,
            tx_id,
            "wrong material",
            acting_operator_id=plain_id,
            manager_pin="1234",
            operator="Plain Operator (PO)",
        )

    assert fetch_transaction(conn, tx_id)["status"] == "active"


def test_void_requires_reason(conn: sqlite3.Connection, operator_id: int) -> None:
    create_manager_pin(conn, "1234", operator="Test Operator (TO)")
    material = get_material_by_key(conn, "plastic_crv_count_small")
    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("5"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 11, 0, 0),
    )

    with pytest.raises(ValueError, match="void reason"):
        void_transaction(
            conn,
            tx_id,
            " ",
            acting_operator_id=operator_id,
            manager_pin="1234",
            operator="Test Operator (TO)",
        )


def test_void_requires_manager_pin(conn: sqlite3.Connection, operator_id: int) -> None:
    create_manager_pin(conn, "1234", operator="Test Operator (TO)")
    material = get_material_by_key(conn, "plastic_crv_count_small")
    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("5"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 11, 0, 0),
    )

    with pytest.raises(PermissionError, match="Manager PIN"):
        void_transaction(
            conn,
            tx_id,
            "wrong material",
            acting_operator_id=operator_id,
            manager_pin="9999",
            operator="Test Operator (TO)",
        )


def test_void_respects_operator_pin_admin_enforcement(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    create_manager_pin(conn, "1234", operator="Test Operator (TO)")
    set_operator_pin(conn, operator_id, "2468", operator="Test Operator (TO)")
    set_bool_setting(conn, REQUIRE_OPERATOR_PIN_ADMIN_KEY, True, audit=False)
    material = get_material_by_key(conn, "plastic_crv_count_small")
    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("5"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 11, 0, 0),
    )

    with pytest.raises(PermissionError, match="Operator PIN verification"):
        void_transaction(
            conn,
            tx_id,
            "wrong material",
            acting_operator_id=operator_id,
            manager_pin="1234",
            operator_verified=False,
            operator="Test Operator (TO)",
        )

    void_transaction(
        conn,
        tx_id,
        "wrong material",
        acting_operator_id=operator_id,
        manager_pin="1234",
        operator_verified=True,
        operator="Test Operator (TO)",
    )
    assert fetch_transaction(conn, tx_id)["status"] == "voided"


def test_void_action_writes_audit_log(conn: sqlite3.Connection, operator_id: int) -> None:
    create_manager_pin(conn, "1234", operator="Test Operator (TO)")
    material = get_material_by_key(conn, "plastic_crv_count_small")
    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("5"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 11, 0, 0),
    )

    void_transaction(
        conn,
        tx_id,
        "wrong material",
        acting_operator_id=operator_id,
        manager_pin="1234",
        operator="Test Operator (TO)",
    )

    rows = list_audit_entries(conn, entity_type="transaction")
    actions = [row["action_type"] for row in rows]
    assert actions[:2] == ["transaction_void_completed", "transaction_void_attempted"]
    assert rows[0]["entity_id"] == tx_id
    assert rows[0]["operator"] == "Test Operator (TO)"
    assert rows[0]["notes"] == "wrong material"


def test_void_operator_columns_migrate_into_existing_database() -> None:
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
            voided_at TEXT,
            void_reason TEXT,
            total_cents INTEGER NOT NULL DEFAULT 0,
            receipt_snapshot_text TEXT NOT NULL DEFAULT ''
        );
        """
    )

    init_db(conn)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(transactions)")}
    conn.close()
    assert {
        "voided_by_operator_id",
        "voided_by_operator_name_snapshot",
        "voided_by_operator_initials_snapshot",
    }.issubset(columns)
