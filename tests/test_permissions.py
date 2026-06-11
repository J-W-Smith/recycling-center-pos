from __future__ import annotations

import json
import sqlite3

import pytest

from app.db import (
    create_manager_pin,
    create_operator,
    get_operator,
    list_audit_entries,
    record_admin_access_denied,
    verify_manager_pin,
)
from app.permissions import has_permission, require_permission


ADMIN_PERMISSIONS = {
    "access_admin_settings",
    "manage_materials",
    "manage_rates",
    "manage_operators",
    "print_receipt",
    "export_receipt",
    "run_feet_closeout",
    "export_audit_log",
    "create_backup",
    "restore_backup",
    "change_manager_pin",
    "manage_operator_pin_settings",
    "void_transaction",
    "correct_transaction",
    "view_voided_transactions",
    "approve_transaction_adjustment",
    "manage_compliance_packs",
    "override_compliance_warning",
}


def test_permission_helper_behavior_for_roles(conn: sqlite3.Connection) -> None:
    operator_id = create_operator(
        conn,
        display_name="Plain Operator",
        initials="PO",
        role="operator",
        audit=False,
    )
    admin_id = create_operator(
        conn,
        display_name="Admin Operator",
        initials="AO",
        role="admin",
        audit=False,
    )
    operator = get_operator(conn, operator_id)
    manager = get_operator(conn, 1)
    admin = get_operator(conn, admin_id)

    assert not has_permission(operator, "access_admin_settings")
    assert not has_permission(operator, "create_backup")
    assert has_permission(operator, "print_receipt")
    assert has_permission(operator, "export_receipt")
    assert not has_permission(operator, "run_feet_closeout")
    for permission in ADMIN_PERMISSIONS:
        assert has_permission(manager, permission)
        assert has_permission(admin, permission)


def test_operator_role_cannot_access_admin_actions(conn: sqlite3.Connection) -> None:
    operator_id = create_operator(
        conn,
        display_name="Plain Operator",
        initials="PO",
        role="operator",
        audit=False,
    )
    operator = get_operator(conn, operator_id)

    for permission in ADMIN_PERMISSIONS - {"print_receipt", "export_receipt"}:
        with pytest.raises(PermissionError):
            require_permission(operator, permission)


def test_manager_and_admin_can_access_admin_with_correct_pin(
    conn: sqlite3.Connection,
) -> None:
    create_manager_pin(conn, "1234", operator="Test Operator (TO)")
    admin_id = create_operator(
        conn,
        display_name="Admin Operator",
        initials="AO",
        role="admin",
        audit=False,
    )

    assert has_permission(get_operator(conn, 1), "access_admin_settings")
    assert has_permission(get_operator(conn, admin_id), "access_admin_settings")
    assert verify_manager_pin(conn, "1234")


def test_access_denied_creates_audit_entry(conn: sqlite3.Connection) -> None:
    record_admin_access_denied(
        conn,
        permission="access_admin_settings",
        reason="operator role cannot open admin settings.",
        operator="Plain Operator (PO)",
        action_label="open Admin Settings",
    )

    row = list_audit_entries(conn, entity_type="settings")[0]
    after = json.loads(row["after_value"])
    assert row["action_type"] == "admin_access_denied"
    assert row["operator"] == "Plain Operator (PO)"
    assert after["permission"] == "access_admin_settings"


def test_backup_restore_and_audit_export_require_admin_permissions(
    conn: sqlite3.Connection,
) -> None:
    operator_id = create_operator(
        conn,
        display_name="Plain Operator",
        initials="PO",
        role="operator",
        audit=False,
    )
    operator = get_operator(conn, operator_id)
    manager = get_operator(conn, 1)

    for permission in ("create_backup", "restore_backup", "export_audit_log"):
        assert not has_permission(operator, permission)
        assert has_permission(manager, permission)
