from __future__ import annotations

import json
import sqlite3

from app.db import (
    add_rate,
    change_manager_pin,
    connect,
    create_manager_pin,
    create_material_type,
    get_material_by_key,
    get_setting,
    init_db,
    list_audit_entries,
    set_material_active,
    update_material_type,
    verify_manager_pin,
)


def test_create_manager_pin_stores_salted_hash_not_plain_text(conn: sqlite3.Connection) -> None:
    create_manager_pin(conn, "1234")

    stored = get_setting(conn, "manager_pin_hash")

    assert stored is not None
    assert stored.startswith("pbkdf2_sha256$")
    assert "1234" not in stored
    assert verify_manager_pin(conn, "1234")
    assert not verify_manager_pin(conn, "9999")


def test_change_manager_pin(conn: sqlite3.Connection) -> None:
    create_manager_pin(conn, "1234")

    change_manager_pin(conn, "1234", "5678")

    assert not verify_manager_pin(conn, "1234")
    assert verify_manager_pin(conn, "5678")
    actions = [row["action_type"] for row in list_audit_entries(conn, entity_type="settings")]
    assert actions == ["manager_pin_changed", "manager_pin_created"]


def test_material_create_edit_deactivate_writes_audit_log(conn: sqlite3.Connection) -> None:
    material_id = create_material_type(
        conn,
        display_name="Lead scrap by weight",
        category="Scrap Metal",
        report_grouping="Non-CRV Lead",
        crv_eligible=False,
        unit_type="weight",
        notes="initial",
    )
    update_material_type(
        conn,
        material_id,
        display_name="Lead scrap custom",
        category="Scrap Metal",
        report_grouping="Non-CRV Lead",
        crv_eligible=False,
        unit_type="weight",
        active=True,
        notes="edited",
    )
    set_material_active(conn, material_id, False)

    rows = list_audit_entries(conn, entity_type="material_type")
    actions = [row["action_type"] for row in rows]

    assert actions == ["material_deactivated", "material_edited", "material_created"]
    edit_row = rows[1]
    before = json.loads(edit_row["before_value"])
    after = json.loads(edit_row["after_value"])
    assert before["display_name"] == "Lead scrap by weight"
    assert after["display_name"] == "Lead scrap custom"
    assert json.loads(rows[0]["after_value"])["active"] == 0


def test_rate_create_and_replacement_writes_audit_log(conn: sqlite3.Connection) -> None:
    material = get_material_by_key(conn, "scrap_aluminum_weight")

    new_rate_id = add_rate(
        conn,
        material_type_id=material.id,
        rate_cents_per_unit=90,
        effective_from="2026-08-01",
        replace_current=True,
    )

    rows = list_audit_entries(conn, entity_type="rate")
    actions = [row["action_type"] for row in rows]

    assert actions == ["rate_created", "rate_replaced_end_dated"]
    created_after = json.loads(rows[0]["after_value"])
    replaced_before = json.loads(rows[1]["before_value"])
    replaced_after = json.loads(rows[1]["after_value"])
    assert created_after["id"] == new_rate_id
    assert replaced_before["effective_to"] is None
    assert replaced_after["effective_to"] == "2026-07-31"


def test_audit_log_preserves_before_and_after_values(conn: sqlite3.Connection) -> None:
    material = get_material_by_key(conn, "plastic_crv_count_small")

    set_material_active(conn, material.id, False)

    audit_row = list_audit_entries(conn, entity_type="material_type")[0]
    before = json.loads(audit_row["before_value"])
    after = json.loads(audit_row["after_value"])

    assert before["active"] == 1
    assert after["active"] == 0
    assert before["display_name"] == after["display_name"]


def test_init_db_migrates_existing_database_schema() -> None:
    conn = connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE material_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            category TEXT NOT NULL,
            crv_eligible INTEGER NOT NULL DEFAULT 0,
            unit_type TEXT NOT NULL,
            default_rate_cents_per_unit INTEGER NOT NULL DEFAULT 0,
            report_grouping TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_type_id INTEGER NOT NULL,
            rate_kind TEXT NOT NULL,
            rate_cents_per_unit INTEGER NOT NULL,
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    init_db(conn)

    material_columns = {row["name"] for row in conn.execute("PRAGMA table_info(material_types)")}
    rate_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rates)")}
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }

    assert {"sort_order", "notes"}.issubset(material_columns)
    assert "active" in rate_columns
    assert {"app_settings", "audit_log"}.issubset(tables)
    create_manager_pin(conn, "1234")
    assert verify_manager_pin(conn, "1234")
