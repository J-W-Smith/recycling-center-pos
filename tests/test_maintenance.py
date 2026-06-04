from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from app.db import (
    add_audit_entry,
    connect,
    create_material_type,
    get_material_by_key,
    init_db,
    list_audit_entries,
)
from app.maintenance import (
    create_database_backup,
    export_audit_log_csv,
    restore_database_from_backup,
    validate_recycling_pos_database,
)
from app.seed_data import seed_materials


def make_file_db(path: Path) -> sqlite3.Connection:
    conn = connect(path)
    init_db(conn)
    seed_materials(conn, effective_from="2026-01-01")
    return conn


def test_audit_log_csv_export_includes_expected_fields(conn: sqlite3.Connection, tmp_path) -> None:
    add_audit_entry(
        conn,
        action_type="manual_test_action",
        entity_type="settings",
        entity_id="test",
        before_value={"before": 1},
        after_value={"after": 2},
        notes="export test",
    )

    csv_path = export_audit_log_csv(conn, tmp_path / "audit.csv")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0].keys() == {
        "timestamp",
        "operator",
        "action",
        "entity_type",
        "entity_id",
        "before_json",
        "after_json",
        "notes",
    }
    assert rows[0]["action"] == "manual_test_action"
    assert rows[0]["before_json"] == '{"before":1}'
    assert rows[0]["after_json"] == '{"after":2}'
    latest_action = list_audit_entries(conn, entity_type="settings")[0]["action_type"]
    assert latest_action == "audit_log_exported"


def test_audit_log_csv_export_respects_entity_filter(
    conn: sqlite3.Connection, tmp_path
) -> None:
    create_material_type(
        conn,
        display_name="Filtered audit material",
        category="Test",
        report_grouping="Test",
        crv_eligible=False,
        unit_type="manual",
    )
    material = get_material_by_key(conn, "scrap_aluminum_weight")
    add_audit_entry(
        conn,
        action_type="manual_rate_action",
        entity_type="rate",
        entity_id=material.id,
    )

    csv_path = export_audit_log_csv(
        conn, tmp_path / "audit_material.csv", entity_type="material_type"
    )

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert {row["entity_type"] for row in rows} == {"material_type"}


def test_database_backup_creates_valid_copy_with_tables_and_data(tmp_path) -> None:
    db_path = tmp_path / "active.sqlite3"
    conn = make_file_db(db_path)
    material_id = create_material_type(
        conn,
        display_name="Backup test material",
        category="Test",
        report_grouping="Test",
        crv_eligible=False,
        unit_type="manual",
    )

    backup_path = create_database_backup(conn, tmp_path / "backup.sqlite3")

    validate_recycling_pos_database(backup_path)
    backup_conn = connect(backup_path)
    try:
        row = backup_conn.execute(
            "SELECT display_name FROM material_types WHERE id = ?", (material_id,)
        ).fetchone()
        backup_actions = [
            row["action_type"] for row in list_audit_entries(backup_conn, entity_type="settings")
        ]
    finally:
        backup_conn.close()
        conn.close()
    assert row["display_name"] == "Backup test material"
    assert "database_backup_created" in backup_actions


def test_restore_rejects_invalid_sqlite_file(tmp_path) -> None:
    conn = make_file_db(tmp_path / "active.sqlite3")
    invalid_file = tmp_path / "not_sqlite.sqlite3"
    invalid_file.write_text("not a sqlite database", encoding="utf-8")

    with pytest.raises(ValueError, match="valid SQLite"):
        restore_database_from_backup(conn, invalid_file, tmp_path / "pre.sqlite3")

    actions = [row["action_type"] for row in list_audit_entries(conn, entity_type="settings")]
    conn.close()
    assert actions[:2] == ["database_restore_failed", "database_restore_attempted"]


def test_restore_rejects_sqlite_file_missing_expected_tables(tmp_path) -> None:
    conn = make_file_db(tmp_path / "active.sqlite3")
    missing_tables = tmp_path / "missing_tables.sqlite3"
    missing_conn = sqlite3.connect(missing_tables)
    try:
        missing_conn.execute("CREATE TABLE only_one (id INTEGER PRIMARY KEY)")
        missing_conn.commit()
    finally:
        missing_conn.close()

    with pytest.raises(ValueError, match="missing expected tables"):
        restore_database_from_backup(conn, missing_tables, tmp_path / "pre.sqlite3")

    actions = [row["action_type"] for row in list_audit_entries(conn, entity_type="settings")]
    conn.close()
    assert actions[:2] == ["database_restore_failed", "database_restore_attempted"]


def test_restore_creates_pre_restore_backup_and_replaces_database(tmp_path) -> None:
    active_conn = make_file_db(tmp_path / "active.sqlite3")
    create_material_type(
        active_conn,
        display_name="Active-only material",
        category="Test",
        report_grouping="Test",
        crv_eligible=False,
        unit_type="manual",
    )
    restore_conn = make_file_db(tmp_path / "restore.sqlite3")
    create_material_type(
        restore_conn,
        display_name="Restored-only material",
        category="Test",
        report_grouping="Test",
        crv_eligible=False,
        unit_type="manual",
    )
    restore_conn.close()
    pre_restore_path = tmp_path / "pre_restore.sqlite3"

    returned_pre_restore = restore_database_from_backup(
        active_conn, tmp_path / "restore.sqlite3", pre_restore_path
    )

    active_names = {
        row["display_name"]
        for row in active_conn.execute("SELECT display_name FROM material_types")
    }
    pre_conn = connect(pre_restore_path)
    try:
        pre_names = {
            row["display_name"]
            for row in pre_conn.execute("SELECT display_name FROM material_types")
        }
    finally:
        pre_conn.close()
        active_conn.close()
    assert returned_pre_restore == pre_restore_path
    assert "Restored-only material" in active_names
    assert "Active-only material" not in active_names
    assert "Active-only material" in pre_names


def test_backup_and_restore_actions_write_audit_log_entries(tmp_path) -> None:
    active_conn = make_file_db(tmp_path / "active.sqlite3")
    restore_conn = make_file_db(tmp_path / "restore.sqlite3")
    restore_conn.close()

    create_database_backup(active_conn, tmp_path / "manual_backup.sqlite3")
    restore_database_from_backup(
        active_conn, tmp_path / "restore.sqlite3", tmp_path / "pre_restore.sqlite3"
    )

    actions = [
        row["action_type"]
        for row in list_audit_entries(active_conn, entity_type="settings")
    ]
    active_conn.close()
    assert "database_restore_completed" in actions
    assert "database_restore_attempted" in actions
