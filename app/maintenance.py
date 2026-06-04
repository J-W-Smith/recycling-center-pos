from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from pathlib import Path

from app.db import add_audit_entry, connect, list_audit_entries


EXPECTED_DATABASE_TABLES = {
    "transactions",
    "transaction_line_items",
    "material_types",
    "rates",
    "app_settings",
    "audit_log",
}


def timestamp_for_filename(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y-%m-%d_%H%M%S")


def default_audit_export_name(now: datetime | None = None) -> str:
    return f"audit_log_{timestamp_for_filename(now)}.csv"


def default_backup_name(now: datetime | None = None) -> str:
    return f"recycling_pos_backup_{timestamp_for_filename(now)}.sqlite3"


def default_pre_restore_backup_name(now: datetime | None = None) -> str:
    return f"recycling_pos_pre_restore_backup_{timestamp_for_filename(now)}.sqlite3"


def get_connection_db_path(conn: sqlite3.Connection) -> Path | None:
    row = conn.execute("PRAGMA database_list").fetchone()
    if row is None or not row["file"]:
        return None
    return Path(row["file"])


def export_audit_log_csv(
    conn: sqlite3.Connection,
    output_path: str | Path,
    *,
    entity_type: str | None = None,
    operator: str = "manager",
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list_audit_entries(conn, entity_type=entity_type, limit=100_000)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "timestamp",
                "operator",
                "action",
                "entity_type",
                "entity_id",
                "before_json",
                "after_json",
                "notes",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["timestamp"],
                    row["operator"],
                    row["action_type"],
                    row["entity_type"],
                    row["entity_id"] or "",
                    row["before_value"] or "",
                    row["after_value"] or "",
                    row["notes"],
                ]
            )
    with conn:
        add_audit_entry(
            conn,
            action_type="audit_log_exported",
            entity_type="settings",
            before_value=None,
            after_value={"path": str(path), "entity_type": entity_type or "all"},
            operator=operator,
            notes="Audit log exported to CSV.",
        )
    return path


def validate_recycling_pos_database(db_path: str | Path) -> None:
    path = Path(db_path)
    if not path.exists() or not path.is_file():
        raise ValueError("Selected restore file does not exist.")
    try:
        conn = sqlite3.connect(path)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise ValueError("Selected file is not a valid SQLite database.") from exc
    missing = EXPECTED_DATABASE_TABLES - tables
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"Selected database is missing expected tables: {missing_list}.")


def create_database_backup(
    conn: sqlite3.Connection,
    output_path: str | Path,
    *,
    operator: str = "manager",
    notes: str = "Database backup created.",
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with conn:
        add_audit_entry(
            conn,
            action_type="database_backup_created",
            entity_type="settings",
            before_value=None,
            after_value={"path": str(path)},
            operator=operator,
            notes=notes,
        )
    _copy_database(conn, path)
    validate_recycling_pos_database(path)
    return path


def restore_database_from_backup(
    conn: sqlite3.Connection,
    restore_path: str | Path,
    pre_restore_backup_path: str | Path,
    *,
    operator: str = "manager",
) -> Path:
    restore_file = Path(restore_path)
    pre_restore_file = Path(pre_restore_backup_path)
    try:
        with conn:
            add_audit_entry(
                conn,
                action_type="database_restore_attempted",
                entity_type="settings",
                before_value=None,
                after_value={"restore_path": str(restore_file)},
                operator=operator,
                notes="Database restore attempted.",
            )
        validate_recycling_pos_database(restore_file)
        create_database_backup(
            conn,
            pre_restore_file,
            operator=operator,
            notes="Pre-restore backup created automatically.",
        )
        source_conn = connect(restore_file)
        try:
            source_conn.backup(conn)
        finally:
            source_conn.close()
        with conn:
            add_audit_entry(
                conn,
                action_type="database_restore_attempted",
                entity_type="settings",
                before_value=None,
                after_value={"restore_path": str(restore_file)},
                operator=operator,
                notes="Database restore attempted.",
            )
            add_audit_entry(
                conn,
                action_type="database_restore_completed",
                entity_type="settings",
                before_value=None,
                after_value={
                    "restore_path": str(restore_file),
                    "pre_restore_backup_path": str(pre_restore_file),
                },
                operator=operator,
                notes="Database restore completed. Restart recommended.",
            )
    except Exception as exc:
        with conn:
            add_audit_entry(
                conn,
                action_type="database_restore_failed",
                entity_type="settings",
                before_value=None,
                after_value={"restore_path": str(restore_file), "error": str(exc)},
                operator=operator,
                notes="Database restore failed.",
            )
        raise
    return pre_restore_file


def _copy_database(conn: sqlite3.Connection, output_path: Path) -> None:
    destination = sqlite3.connect(output_path)
    try:
        conn.backup(destination)
    finally:
        destination.close()
