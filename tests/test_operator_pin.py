from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from decimal import Decimal

import pytest

from app.db import (
    REQUIRE_OPERATOR_PIN_ADMIN_KEY,
    REQUIRE_OPERATOR_PIN_TRANSACTIONS_KEY,
    clear_operator_pin,
    connect,
    create_manager_pin,
    create_operator,
    create_transaction,
    fetch_transaction,
    get_bool_setting,
    get_material_by_key,
    get_operator,
    init_db,
    list_audit_entries,
    set_bool_setting,
    set_operator_pin,
    verify_manager_pin,
    verify_operator_pin,
)
from app.models import LineItemInput, TransactionInput
from app.permissions import has_permission


def test_operator_pin_is_stored_hashed_not_plain_text(conn: sqlite3.Connection) -> None:
    set_operator_pin(conn, 1, "2468", operator="Test Operator (TO)")

    row = conn.execute("SELECT pin_hash FROM operators WHERE id = 1").fetchone()
    stored = row["pin_hash"]

    assert stored != "2468"
    assert stored.startswith("pbkdf2_sha256$")
    assert verify_operator_pin(conn, 1, "2468")
    assert not verify_operator_pin(conn, 1, "9999")


def test_operator_pin_can_be_set_changed_and_cleared(
    conn: sqlite3.Connection,
) -> None:
    set_operator_pin(conn, 1, "2468", operator="Test Operator (TO)")
    assert get_operator(conn, 1).pin_set
    assert verify_operator_pin(conn, 1, "2468")

    set_operator_pin(conn, 1, "1357", operator="Test Operator (TO)")
    assert not verify_operator_pin(conn, 1, "2468")
    assert verify_operator_pin(conn, 1, "1357")

    clear_operator_pin(conn, 1, operator="Test Operator (TO)")
    assert not get_operator(conn, 1).pin_set
    assert not verify_operator_pin(conn, 1, "1357")


def test_operator_pin_audit_entries_do_not_include_pin_values(
    conn: sqlite3.Connection,
) -> None:
    set_operator_pin(conn, 1, "2468", operator="Test Operator (TO)")
    set_operator_pin(conn, 1, "1357", operator="Test Operator (TO)")
    clear_operator_pin(conn, 1, operator="Test Operator (TO)")

    rows = list_audit_entries(conn, entity_type="operator")
    actions = [row["action_type"] for row in rows]
    serialized = "\n".join(
        f"{row['before_value'] or ''}\n{row['after_value'] or ''}\n{row['notes']}"
        for row in rows
    )

    assert actions[:3] == [
        "operator_pin_cleared",
        "operator_pin_changed",
        "operator_pin_set",
    ]
    assert "2468" not in serialized
    assert "1357" not in serialized
    assert "pbkdf2_sha256" not in serialized
    assert json.loads(rows[0]["after_value"])["pin_set"] is False


def test_existing_operators_without_pin_work_when_enforcement_disabled(
    conn: sqlite3.Connection,
) -> None:
    material = get_material_by_key(conn, "aluminum_crv_count_small")

    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("1"))],
            operator_id=1,
        ),
        created_at=datetime(2026, 6, 4, 9, 0, 0),
    )

    tx = fetch_transaction(conn, tx_id)
    assert tx["operator_verified"] == 0


def test_transaction_requires_verified_operator_when_enforced(
    conn: sqlite3.Connection,
) -> None:
    material = get_material_by_key(conn, "aluminum_crv_count_small")
    set_operator_pin(conn, 1, "2468", operator="Test Operator (TO)")
    set_bool_setting(conn, REQUIRE_OPERATOR_PIN_TRANSACTIONS_KEY, True, audit=False)

    with pytest.raises(ValueError, match="PIN verification is required"):
        create_transaction(
            conn,
            TransactionInput(
                line_items=[LineItemInput(material.id, Decimal("1"))],
                operator_id=1,
            ),
            created_at=datetime(2026, 6, 4, 9, 0, 0),
        )

    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("1"))],
            operator_id=1,
            operator_verified=True,
        ),
        created_at=datetime(2026, 6, 4, 9, 0, 0),
    )

    tx = fetch_transaction(conn, tx_id)
    assert tx["operator_verified"] == 1


def test_transaction_enforcement_rejects_operator_without_pin(
    conn: sqlite3.Connection,
) -> None:
    material = get_material_by_key(conn, "aluminum_crv_count_small")
    set_bool_setting(conn, REQUIRE_OPERATOR_PIN_TRANSACTIONS_KEY, True, audit=False)

    with pytest.raises(ValueError, match="operator has no PIN"):
        create_transaction(
            conn,
            TransactionInput(
                line_items=[LineItemInput(material.id, Decimal("1"))],
                operator_id=1,
                operator_verified=True,
            ),
            created_at=datetime(2026, 6, 4, 9, 0, 0),
        )


def test_operator_pin_settings_are_audited(conn: sqlite3.Connection) -> None:
    set_bool_setting(
        conn,
        REQUIRE_OPERATOR_PIN_TRANSACTIONS_KEY,
        True,
        operator="Test Operator (TO)",
    )
    set_bool_setting(
        conn,
        REQUIRE_OPERATOR_PIN_ADMIN_KEY,
        True,
        operator="Test Operator (TO)",
    )

    rows = list_audit_entries(conn, entity_type="settings")
    actions = [row["action_type"] for row in rows]

    assert actions[:2] == [
        "operator_pin_enforcement_changed",
        "operator_pin_enforcement_changed",
    ]
    assert get_bool_setting(conn, REQUIRE_OPERATOR_PIN_TRANSACTIONS_KEY)
    assert get_bool_setting(conn, REQUIRE_OPERATOR_PIN_ADMIN_KEY)


def test_protected_admin_action_primitives_check_role_manager_pin_and_operator_pin(
    conn: sqlite3.Connection,
) -> None:
    create_manager_pin(conn, "1234", operator="Test Operator (TO)")
    set_operator_pin(conn, 1, "2468", operator="Test Operator (TO)")
    set_bool_setting(conn, REQUIRE_OPERATOR_PIN_ADMIN_KEY, True, audit=False)
    plain_id = create_operator(
        conn,
        display_name="Plain Operator",
        initials="PO",
        role="operator",
        audit=False,
    )

    assert has_permission(get_operator(conn, 1), "access_admin_settings")
    assert verify_manager_pin(conn, "1234")
    assert verify_operator_pin(conn, 1, "2468")
    assert not has_permission(get_operator(conn, plain_id), "access_admin_settings")


def test_operator_pin_columns_migrate_into_existing_database() -> None:
    conn = connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE operators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name TEXT NOT NULL,
            initials TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL DEFAULT 'operator',
            active INTEGER NOT NULL DEFAULT 1,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO operators (display_name, initials, role)
        VALUES ('Legacy Manager', 'LM', 'manager');
        """
    )

    init_db(conn)

    operator = get_operator(conn, 1)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(operators)")}
    conn.close()
    assert {"pin_hash", "pin_updated_at"}.issubset(columns)
    assert operator.display_name == "Legacy Manager"
    assert operator.pin_set is False
    assert operator.pin_updated_at is None


def test_create_operator_can_store_initial_pin(conn: sqlite3.Connection) -> None:
    operator_id = create_operator(
        conn,
        display_name="Pinned Operator",
        initials="PN",
        role="operator",
        initial_pin="8642",
        audit=False,
    )

    assert get_operator(conn, operator_id).pin_set
    assert verify_operator_pin(conn, operator_id, "8642")
