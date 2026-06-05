from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.models import LineItemInput, MaterialType, Operator, Rate, TransactionInput
from app.pricing import cents_for_quantity
from app.receipt import build_receipt_text


DEFAULT_DB_PATH = Path("data/recycling_pos.sqlite3")
PIN_HASH_ITERATIONS = 260_000
MANAGER_PIN_SETTING_KEY = "manager_pin_hash"


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    if path != Path(":memory:"):
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS material_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            category TEXT NOT NULL,
            crv_eligible INTEGER NOT NULL DEFAULT 0,
            unit_type TEXT NOT NULL CHECK (unit_type IN ('weight', 'count', 'manual')),
            default_rate_cents_per_unit INTEGER NOT NULL DEFAULT 0,
            report_grouping TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_type_id INTEGER NOT NULL REFERENCES material_types(id),
            rate_kind TEXT NOT NULL,
            rate_cents_per_unit INTEGER NOT NULL,
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            notes TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_rates_material_effective
            ON rates(material_type_id, effective_from, effective_to);

        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            operator_id INTEGER REFERENCES operators(id),
            operator_initials TEXT NOT NULL,
            operator_display_name_snapshot TEXT NOT NULL DEFAULT '',
            operator_initials_snapshot TEXT NOT NULL DEFAULT '',
            payout_method TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'voided', 'corrected')),
            voided_at TEXT,
            void_reason TEXT,
            correction_of_transaction_id TEXT REFERENCES transactions(id),
            total_cents INTEGER NOT NULL DEFAULT 0,
            receipt_snapshot_text TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_transactions_created_status
            ON transactions(created_at, status);

        CREATE TABLE IF NOT EXISTS transaction_line_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT NOT NULL REFERENCES transactions(id),
            material_type_id INTEGER NOT NULL REFERENCES material_types(id),
            description TEXT NOT NULL DEFAULT '',
            quantity TEXT NOT NULL,
            unit_type TEXT NOT NULL,
            rate_cents_per_unit INTEGER NOT NULL,
            subtotal_cents INTEGER NOT NULL,
            crv_eligible INTEGER NOT NULL DEFAULT 0,
            report_grouping TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS receipt_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT NOT NULL REFERENCES transactions(id),
            snapshot_text TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS daily_report_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT NOT NULL,
            generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            operator_initials TEXT,
            notes TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            initials TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS operators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name TEXT NOT NULL,
            initials TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL DEFAULT 'operator'
                CHECK (role IN ('operator', 'manager', 'admin')),
            active INTEGER NOT NULL DEFAULT 1,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            operator TEXT NOT NULL DEFAULT 'manager',
            action_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            before_value TEXT,
            after_value TEXT,
            notes TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
            ON audit_log(timestamp);

        CREATE INDEX IF NOT EXISTS idx_audit_log_entity
            ON audit_log(entity_type, entity_id);
        """
    )
    _ensure_column(conn, "material_types", "sort_order", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_types", "notes", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "rates", "active", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "transactions", "operator_id", "INTEGER REFERENCES operators(id)")
    _ensure_column(
        conn,
        "transactions",
        "operator_display_name_snapshot",
        "TEXT NOT NULL DEFAULT ''",
    )
    _ensure_column(
        conn,
        "transactions",
        "operator_initials_snapshot",
        "TEXT NOT NULL DEFAULT ''",
    )
    conn.execute(
        """
        UPDATE transactions
        SET operator_initials_snapshot = operator_initials
        WHERE operator_initials_snapshot = '' AND operator_initials != ''
        """
    )
    conn.commit()


def has_manager_pin(conn: sqlite3.Connection) -> bool:
    return get_setting(conn, MANAGER_PIN_SETTING_KEY) is not None


def create_manager_pin(conn: sqlite3.Connection, pin: str, operator: str = "manager") -> None:
    if has_manager_pin(conn):
        raise ValueError("Manager PIN already exists.")
    _validate_pin_input(pin)
    with conn:
        set_setting(conn, MANAGER_PIN_SETTING_KEY, _hash_pin(pin))
        add_audit_entry(
            conn,
            action_type="manager_pin_created",
            entity_type="settings",
            entity_id=MANAGER_PIN_SETTING_KEY,
            before_value=None,
            after_value={"manager_pin_hash": "set"},
            operator=operator,
            notes="Manager PIN created.",
        )


def change_manager_pin(
    conn: sqlite3.Connection,
    current_pin: str,
    new_pin: str,
    operator: str = "manager",
) -> None:
    if not verify_manager_pin(conn, current_pin):
        raise ValueError("Current manager PIN is incorrect.")
    _validate_pin_input(new_pin)
    with conn:
        before = {"manager_pin_hash": "set"}
        set_setting(conn, MANAGER_PIN_SETTING_KEY, _hash_pin(new_pin))
        add_audit_entry(
            conn,
            action_type="manager_pin_changed",
            entity_type="settings",
            entity_id=MANAGER_PIN_SETTING_KEY,
            before_value=before,
            after_value={"manager_pin_hash": "changed"},
            operator=operator,
            notes="Manager PIN changed.",
        )


def verify_manager_pin(conn: sqlite3.Connection, pin: str) -> bool:
    stored_hash = get_setting(conn, MANAGER_PIN_SETTING_KEY)
    if stored_hash is None:
        return False
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            pin.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return None if row is None else row["value"]


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, value),
    )


def _hash_pin(pin: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), salt, PIN_HASH_ITERATIONS
    )
    return f"pbkdf2_sha256${PIN_HASH_ITERATIONS}${salt.hex()}${digest.hex()}"


def _validate_pin_input(pin: str) -> None:
    if len(pin.strip()) < 4:
        raise ValueError("Manager PIN must be at least 4 characters.")


def add_audit_entry(
    conn: sqlite3.Connection,
    *,
    action_type: str,
    entity_type: str,
    entity_id: str | int | None = None,
    before_value: object | None = None,
    after_value: object | None = None,
    notes: str = "",
    operator: str = "manager",
) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (
            timestamp, operator, action_type, entity_type, entity_id,
            before_value, after_value, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            operator.strip() or "manager",
            action_type,
            entity_type,
            None if entity_id is None else str(entity_id),
            _json_or_none(before_value),
            _json_or_none(after_value),
            notes.strip(),
        ),
    )


def record_admin_access_denied(
    conn: sqlite3.Connection,
    *,
    permission: str,
    reason: str,
    operator: str = "unknown",
    action_label: str = "Admin action",
) -> None:
    add_audit_entry(
        conn,
        action_type="admin_access_denied",
        entity_type="settings",
        before_value=None,
        after_value={"permission": permission, "reason": reason},
        operator=operator,
        notes=f"Denied: {action_label}",
    )


def list_audit_entries(
    conn: sqlite3.Connection, entity_type: str | None = None, limit: int = 200
) -> list[sqlite3.Row]:
    sql = "SELECT * FROM audit_log"
    params: list[object] = []
    if entity_type:
        sql += " WHERE entity_type = ?"
        params.append(entity_type)
    sql += " ORDER BY timestamp DESC, id DESC LIMIT ?"
    params.append(limit)
    return list(conn.execute(sql, params))


def _json_or_none(value: object | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _ensure_column(
    conn: sqlite3.Connection, table_name: str, column_name: str, definition: str
) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def material_from_row(row: sqlite3.Row) -> MaterialType:
    return MaterialType(
        id=row["id"],
        key=row["key"],
        display_name=row["display_name"],
        category=row["category"],
        crv_eligible=bool(row["crv_eligible"]),
        unit_type=row["unit_type"],
        report_grouping=row["report_grouping"],
        active=bool(row["active"]),
        sort_order=int(row["sort_order"]),
        notes=row["notes"],
    )


def operator_from_row(row: sqlite3.Row) -> Operator:
    return Operator(
        id=row["id"],
        display_name=row["display_name"],
        initials=row["initials"],
        role=row["role"],
        active=bool(row["active"]),
        notes=row["notes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_operators(conn: sqlite3.Connection, active_only: bool = True) -> list[Operator]:
    sql = "SELECT * FROM operators"
    params: tuple[object, ...] = ()
    if active_only:
        sql += " WHERE active = ?"
        params = (1,)
    sql += " ORDER BY active DESC, display_name, initials"
    return [operator_from_row(row) for row in conn.execute(sql, params)]


def get_operator(conn: sqlite3.Connection, operator_id: int) -> Operator:
    row = conn.execute("SELECT * FROM operators WHERE id = ?", (operator_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown operator_id: {operator_id}")
    return operator_from_row(row)


def has_active_operator(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT 1 FROM operators WHERE active = 1 LIMIT 1").fetchone()
    return row is not None


def create_operator(
    conn: sqlite3.Connection,
    *,
    display_name: str,
    initials: str,
    role: str = "operator",
    active: bool = True,
    notes: str = "",
    audit: bool = True,
    operator: str = "manager",
    audit_notes: str = "",
) -> int:
    _validate_operator_role(role)
    normalized_initials = initials.strip().upper()
    if not display_name.strip():
        raise ValueError("Operator display name is required.")
    if not normalized_initials:
        raise ValueError("Operator initials are required.")
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO operators (
                display_name, initials, role, active, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                display_name.strip(),
                normalized_initials,
                role,
                1 if active else 0,
                notes.strip(),
            ),
        )
        operator_id = int(cursor.lastrowid)
        if audit:
            add_audit_entry(
                conn,
                action_type="operator_created",
                entity_type="operator",
                entity_id=operator_id,
                before_value=None,
                after_value=_operator_snapshot(conn, operator_id),
                operator=operator,
                notes=audit_notes,
            )
    return operator_id


def update_operator(
    conn: sqlite3.Connection,
    operator_id: int,
    *,
    display_name: str,
    initials: str,
    role: str,
    active: bool,
    notes: str = "",
    audit: bool = True,
    operator: str = "manager",
    audit_notes: str = "",
) -> None:
    _validate_operator_role(role)
    normalized_initials = initials.strip().upper()
    if not display_name.strip():
        raise ValueError("Operator display name is required.")
    if not normalized_initials:
        raise ValueError("Operator initials are required.")
    existing = get_operator(conn, operator_id)
    if (
        existing.active
        and existing.role in {"manager", "admin"}
        and (not active or role == "operator")
        and _active_admin_operator_count(conn, exclude_operator_id=operator_id) == 0
    ):
        raise ValueError("At least one active manager or admin operator is required.")
    with conn:
        before = _operator_snapshot(conn, operator_id)
        result = conn.execute(
            """
            UPDATE operators
            SET display_name = ?, initials = ?, role = ?, active = ?, notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                display_name.strip(),
                normalized_initials,
                role,
                1 if active else 0,
                notes.strip(),
                operator_id,
            ),
        )
        if result.rowcount and audit:
            after = _operator_snapshot(conn, operator_id)
            action_type = "operator_edited"
            if before and after and before["active"] != after["active"]:
                action_type = "operator_reactivated" if after["active"] else "operator_deactivated"
            add_audit_entry(
                conn,
                action_type=action_type,
                entity_type="operator",
                entity_id=operator_id,
                before_value=before,
                after_value=after,
                operator=operator,
                notes=audit_notes,
            )
    if result.rowcount == 0:
        raise ValueError(f"Unknown operator_id: {operator_id}")


def set_operator_active(
    conn: sqlite3.Connection,
    operator_id: int,
    active: bool,
    *,
    audit: bool = True,
    operator: str = "manager",
    audit_notes: str = "",
) -> None:
    existing = get_operator(conn, operator_id)
    if (
        existing.active
        and existing.role in {"manager", "admin"}
        and not active
        and _active_admin_operator_count(conn, exclude_operator_id=operator_id) == 0
    ):
        raise ValueError("At least one active manager or admin operator is required.")
    with conn:
        before = _operator_snapshot(conn, operator_id)
        result = conn.execute(
            """
            UPDATE operators
            SET active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (1 if active else 0, operator_id),
        )
        if result.rowcount and audit:
            add_audit_entry(
                conn,
                action_type="operator_reactivated" if active else "operator_deactivated",
                entity_type="operator",
                entity_id=operator_id,
                before_value=before,
                after_value=_operator_snapshot(conn, operator_id),
                operator=operator,
                notes=audit_notes,
            )
    if result.rowcount == 0:
        raise ValueError(f"Unknown operator_id: {operator_id}")


def format_operator_label(operator: Operator) -> str:
    return f"{operator.display_name} ({operator.initials})"


def _operator_snapshot(conn: sqlite3.Connection, operator_id: int) -> dict[str, object] | None:
    row = conn.execute("SELECT * FROM operators WHERE id = ?", (operator_id,)).fetchone()
    return _row_to_dict(row)


def _active_admin_operator_count(
    conn: sqlite3.Connection, exclude_operator_id: int | None = None
) -> int:
    sql = """
        SELECT COUNT(*) AS count
        FROM operators
        WHERE active = 1 AND role IN ('manager', 'admin')
    """
    params: tuple[object, ...] = ()
    if exclude_operator_id is not None:
        sql += " AND id != ?"
        params = (exclude_operator_id,)
    return int(conn.execute(sql, params).fetchone()["count"])


def _validate_operator_role(role: str) -> None:
    if role not in {"operator", "manager", "admin"}:
        raise ValueError("operator role must be operator, manager, or admin.")


def list_materials(conn: sqlite3.Connection, active_only: bool = True) -> list[MaterialType]:
    sql = "SELECT * FROM material_types"
    params: tuple[object, ...] = ()
    if active_only:
        sql += " WHERE active = ?"
        params = (1,)
    sql += " ORDER BY sort_order, report_grouping, display_name"
    return [material_from_row(row) for row in conn.execute(sql, params)]


def rate_from_row(row: sqlite3.Row) -> Rate:
    return Rate(
        id=row["id"],
        material_type_id=row["material_type_id"],
        rate_kind=row["rate_kind"],
        rate_cents_per_unit=int(row["rate_cents_per_unit"]),
        effective_from=row["effective_from"],
        effective_to=row["effective_to"],
        notes=row["notes"],
        active=bool(row["active"]),
    )


def get_material(conn: sqlite3.Connection, material_type_id: int) -> MaterialType:
    row = conn.execute("SELECT * FROM material_types WHERE id = ?", (material_type_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown material_type_id: {material_type_id}")
    return material_from_row(row)


def get_material_by_key(conn: sqlite3.Connection, key: str) -> MaterialType:
    row = conn.execute("SELECT * FROM material_types WHERE key = ?", (key,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown material key: {key}")
    return material_from_row(row)


def get_current_rate(
    conn: sqlite3.Connection, material_type_id: int, as_of: str | None = None
) -> int:
    as_of = as_of or datetime.now().date().isoformat()
    row = conn.execute(
        """
        SELECT rate_cents_per_unit
        FROM rates
        WHERE material_type_id = ?
          AND active = 1
          AND effective_from <= ?
          AND (effective_to IS NULL OR effective_to >= ?)
        ORDER BY effective_from DESC, id DESC
        LIMIT 1
        """,
        (material_type_id, as_of, as_of),
    ).fetchone()
    if row is None:
        material = get_material(conn, material_type_id)
        raise ValueError(
            f"No active rate is effective for {material.display_name} on {as_of}."
        )
    return int(row["rate_cents_per_unit"])


def create_material_type(
    conn: sqlite3.Connection,
    *,
    display_name: str,
    category: str,
    report_grouping: str,
    crv_eligible: bool,
    unit_type: str,
    active: bool = True,
    sort_order: int = 0,
    notes: str = "",
    key: str | None = None,
    default_rate_cents_per_unit: int = 0,
    audit: bool = True,
    operator: str = "manager",
    audit_notes: str = "",
) -> int:
    key = key or _unique_material_key(conn, display_name)
    _validate_unit_type(unit_type)
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO material_types (
                key, display_name, category, crv_eligible, unit_type,
                default_rate_cents_per_unit, report_grouping, active, sort_order, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                display_name.strip(),
                category.strip(),
                1 if crv_eligible else 0,
                unit_type,
                default_rate_cents_per_unit,
                report_grouping.strip() or category.strip(),
                1 if active else 0,
                int(sort_order),
                notes.strip(),
            ),
        )
        material_id = int(cursor.lastrowid)
        if audit:
            add_audit_entry(
                conn,
                action_type="material_created",
                entity_type="material_type",
                entity_id=material_id,
                before_value=None,
                after_value=_material_snapshot(conn, material_id),
                operator=operator,
                notes=audit_notes,
            )
    return material_id


def update_material_type(
    conn: sqlite3.Connection,
    material_type_id: int,
    *,
    display_name: str,
    category: str,
    report_grouping: str,
    crv_eligible: bool,
    unit_type: str,
    active: bool,
    sort_order: int = 0,
    notes: str = "",
    audit: bool = True,
    operator: str = "manager",
    audit_notes: str = "",
) -> None:
    _validate_unit_type(unit_type)
    with conn:
        before = _material_snapshot(conn, material_type_id)
        result = conn.execute(
            """
            UPDATE material_types
            SET display_name = ?, category = ?, report_grouping = ?, crv_eligible = ?,
                unit_type = ?, active = ?, sort_order = ?, notes = ?
            WHERE id = ?
            """,
            (
                display_name.strip(),
                category.strip(),
                report_grouping.strip() or category.strip(),
                1 if crv_eligible else 0,
                unit_type,
                1 if active else 0,
                int(sort_order),
                notes.strip(),
                material_type_id,
            ),
        )
        if result.rowcount:
            after = _material_snapshot(conn, material_type_id)
            action_type = "material_edited"
            if before and after and before["active"] != after["active"]:
                action_type = (
                    "material_reactivated" if after["active"] else "material_deactivated"
                )
            if audit:
                add_audit_entry(
                    conn,
                    action_type=action_type,
                    entity_type="material_type",
                    entity_id=material_type_id,
                    before_value=before,
                    after_value=after,
                    operator=operator,
                    notes=audit_notes,
                )
    if result.rowcount == 0:
        raise ValueError(f"Unknown material_type_id: {material_type_id}")


def set_material_active(
    conn: sqlite3.Connection,
    material_type_id: int,
    active: bool,
    *,
    audit: bool = True,
    operator: str = "manager",
    audit_notes: str = "",
) -> None:
    with conn:
        before = _material_snapshot(conn, material_type_id)
        result = conn.execute(
            "UPDATE material_types SET active = ? WHERE id = ?",
            (1 if active else 0, material_type_id),
        )
        if result.rowcount and audit:
            after = _material_snapshot(conn, material_type_id)
            add_audit_entry(
                conn,
                action_type="material_reactivated" if active else "material_deactivated",
                entity_type="material_type",
                entity_id=material_type_id,
                before_value=before,
                after_value=after,
                operator=operator,
                notes=audit_notes,
            )
    if result.rowcount == 0:
        raise ValueError(f"Unknown material_type_id: {material_type_id}")


def _material_snapshot(conn: sqlite3.Connection, material_type_id: int) -> dict[str, object] | None:
    row = conn.execute("SELECT * FROM material_types WHERE id = ?", (material_type_id,)).fetchone()
    return _row_to_dict(row)


def _unique_material_key(conn: sqlite3.Connection, display_name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", display_name.strip().lower()).strip("_") or "material"
    candidate = base
    suffix = 2
    while conn.execute("SELECT 1 FROM material_types WHERE key = ?", (candidate,)).fetchone():
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def _validate_unit_type(unit_type: str) -> None:
    if unit_type not in {"weight", "count", "manual"}:
        raise ValueError("unit_type must be weight, count, or manual.")


def list_rates(conn: sqlite3.Connection, material_type_id: int | None = None) -> list[sqlite3.Row]:
    sql = """
        SELECT
            r.*,
            mt.display_name AS material_display_name,
            mt.unit_type AS unit_type
        FROM rates r
        JOIN material_types mt ON mt.id = r.material_type_id
    """
    params: tuple[object, ...] = ()
    if material_type_id is not None:
        sql += " WHERE r.material_type_id = ?"
        params = (material_type_id,)
    sql += " ORDER BY mt.sort_order, mt.display_name, r.effective_from DESC, r.id DESC"
    return list(conn.execute(sql, params))


def get_rate(conn: sqlite3.Connection, rate_id: int) -> Rate:
    row = conn.execute("SELECT * FROM rates WHERE id = ?", (rate_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown rate_id: {rate_id}")
    return rate_from_row(row)


def add_rate(
    conn: sqlite3.Connection,
    *,
    material_type_id: int,
    rate_cents_per_unit: int,
    effective_from: str,
    effective_to: str | None = None,
    active: bool = True,
    notes: str = "",
    rate_kind: str | None = None,
    replace_current: bool = False,
    audit: bool = True,
    operator: str = "manager",
    audit_notes: str = "",
) -> int:
    material = get_material(conn, material_type_id)
    start = _parse_date(effective_from, "effective_from")
    end = _parse_optional_date(effective_to, "effective_to")
    if end is not None and end < start:
        raise ValueError("effective_to cannot be before effective_from.")

    with conn:
        replaced_before: list[dict[str, object]] = []
        if active and replace_current:
            previous_end = (start - timedelta(days=1)).isoformat()
            replaced_rows = conn.execute(
                """
                SELECT *
                FROM rates
                WHERE material_type_id = ?
                  AND active = 1
                  AND effective_from < ?
                  AND (effective_to IS NULL OR effective_to >= ?)
                """,
                (material_type_id, effective_from, effective_from),
            ).fetchall()
            replaced_before = [
                snapshot for row in replaced_rows if (snapshot := _row_to_dict(row))
            ]
            conn.execute(
                """
                UPDATE rates
                SET effective_to = ?
                WHERE material_type_id = ?
                  AND active = 1
                  AND effective_from < ?
                  AND (effective_to IS NULL OR effective_to >= ?)
                """,
                (previous_end, material_type_id, effective_from, effective_from),
            )
            if audit:
                for before in replaced_before:
                    after = _rate_snapshot(conn, int(before["id"]))
                    add_audit_entry(
                        conn,
                        action_type="rate_replaced_end_dated",
                        entity_type="rate",
                        entity_id=before["id"],
                        before_value=before,
                        after_value=after,
                        operator=operator,
                        notes=audit_notes or "End-dated by replacement rate.",
                    )
        if active and rate_overlaps(
            conn,
            material_type_id=material_type_id,
            effective_from=effective_from,
            effective_to=effective_to,
        ):
            raise ValueError(
                f"Active rate period overlaps another rate for {material.display_name}."
            )
        cursor = conn.execute(
            """
            INSERT INTO rates (
                material_type_id, rate_kind, rate_cents_per_unit,
                effective_from, effective_to, notes, active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                material_type_id,
                rate_kind or material.unit_type,
                int(rate_cents_per_unit),
                effective_from,
                effective_to or None,
                notes.strip(),
                1 if active else 0,
            ),
        )
        rate_id = int(cursor.lastrowid)
        if audit:
            add_audit_entry(
                conn,
                action_type="rate_created",
                entity_type="rate",
                entity_id=rate_id,
                before_value=None,
                after_value=_rate_snapshot(conn, rate_id),
                operator=operator,
                notes=audit_notes,
            )
    return rate_id


def update_rate_metadata(
    conn: sqlite3.Connection,
    rate_id: int,
    *,
    effective_to: str | None,
    active: bool,
    notes: str,
    audit: bool = True,
    operator: str = "manager",
    audit_notes: str = "",
) -> None:
    rate = get_rate(conn, rate_id)
    if _parse_optional_date(effective_to, "effective_to") is not None:
        end = _parse_optional_date(effective_to, "effective_to")
        start = _parse_date(rate.effective_from, "effective_from")
        if end is not None and end < start:
            raise ValueError("effective_to cannot be before effective_from.")
    if active and rate_overlaps(
        conn,
        material_type_id=rate.material_type_id,
        effective_from=rate.effective_from,
        effective_to=effective_to,
        exclude_rate_id=rate.id,
    ):
        material = get_material(conn, rate.material_type_id)
        raise ValueError(
            f"Active rate period overlaps another rate for {material.display_name}."
        )
    with conn:
        before = _rate_snapshot(conn, rate_id)
        conn.execute(
            """
            UPDATE rates
            SET effective_to = ?, active = ?, notes = ?
            WHERE id = ?
            """,
            (effective_to or None, 1 if active else 0, notes.strip(), rate_id),
        )
        if audit:
            add_audit_entry(
                conn,
                action_type="rate_edited",
                entity_type="rate",
                entity_id=rate_id,
                before_value=before,
                after_value=_rate_snapshot(conn, rate_id),
                operator=operator,
                notes=audit_notes,
            )


def _rate_snapshot(conn: sqlite3.Connection, rate_id: int) -> dict[str, object] | None:
    row = conn.execute("SELECT * FROM rates WHERE id = ?", (rate_id,)).fetchone()
    return _row_to_dict(row)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def rate_overlaps(
    conn: sqlite3.Connection,
    *,
    material_type_id: int,
    effective_from: str,
    effective_to: str | None,
    exclude_rate_id: int | None = None,
) -> bool:
    start = _parse_date(effective_from, "effective_from")
    end = _parse_optional_date(effective_to, "effective_to") or date.max
    sql = """
        SELECT id, effective_from, effective_to
        FROM rates
        WHERE material_type_id = ? AND active = 1
    """
    params: list[object] = [material_type_id]
    if exclude_rate_id is not None:
        sql += " AND id != ?"
        params.append(exclude_rate_id)
    for row in conn.execute(sql, params):
        row_start = _parse_date(row["effective_from"], "effective_from")
        row_end = _parse_optional_date(row["effective_to"], "effective_to") or date.max
        if start <= row_end and row_start <= end:
            return True
    return False


def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD format.") from exc


def _parse_optional_date(value: str | None, field_name: str) -> date | None:
    if value is None or value.strip() == "":
        return None
    return _parse_date(value.strip(), field_name)


def create_transaction(
    conn: sqlite3.Connection,
    payload: TransactionInput,
    created_at: datetime | None = None,
) -> str:
    if not payload.line_items:
        raise ValueError("A transaction must include at least one line item.")
    if payload.operator_id is None:
        raise ValueError("An active operator is required to save a transaction.")

    created_at = created_at or datetime.now()
    operator_record = get_operator(conn, payload.operator_id)
    if not operator_record.active:
        raise ValueError(f"Operator {operator_record.display_name} is inactive.")
    operator_initials_snapshot = operator_record.initials
    operator_name_snapshot = operator_record.display_name
    transaction_id = str(uuid4())
    line_rows: list[dict[str, object]] = []
    total_cents = 0

    with conn:
        conn.execute(
            """
            INSERT INTO transactions (
                id, created_at, operator_id, operator_initials,
                operator_display_name_snapshot, operator_initials_snapshot,
                payout_method, notes, status, total_cents
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', 0)
            """,
            (
                transaction_id,
                created_at.isoformat(timespec="seconds"),
                operator_record.id,
                operator_initials_snapshot,
                operator_name_snapshot,
                operator_initials_snapshot,
                payload.payout_method.strip() or "cash",
                payload.notes.strip(),
            ),
        )

        for item in payload.line_items:
            material = get_material(conn, item.material_type_id)
            if not material.active:
                raise ValueError(f"{material.display_name} is inactive for new transactions.")
            quantity = Decimal(item.quantity)
            if quantity <= 0:
                raise ValueError("Line item quantity must be greater than zero.")
            rate_cents = (
                item.rate_cents_per_unit
                if item.rate_cents_per_unit is not None
                else get_current_rate(conn, material.id, created_at.date().isoformat())
            )
            subtotal_cents = cents_for_quantity(quantity, int(rate_cents))
            total_cents += subtotal_cents
            description = item.description.strip() or material.display_name
            conn.execute(
                """
                INSERT INTO transaction_line_items (
                    transaction_id, material_type_id, description, quantity, unit_type,
                    rate_cents_per_unit, subtotal_cents, crv_eligible, report_grouping
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction_id,
                    material.id,
                    description,
                    str(quantity),
                    material.unit_type,
                    int(rate_cents),
                    subtotal_cents,
                    1 if material.crv_eligible else 0,
                    material.report_grouping,
                ),
            )
            line_rows.append(
                {
                    "description": description,
                    "quantity": str(quantity),
                    "unit_type": material.unit_type,
                    "rate_cents_per_unit": int(rate_cents),
                    "subtotal_cents": subtotal_cents,
                    "crv_eligible": material.crv_eligible,
                    "report_grouping": material.report_grouping,
                }
            )

        receipt_text = build_receipt_text(
            transaction={
                "id": transaction_id,
                "created_at": created_at.isoformat(timespec="seconds"),
                "operator_display_name": operator_name_snapshot,
                "operator_initials": operator_initials_snapshot,
                "payout_method": payload.payout_method.strip() or "cash",
                "notes": payload.notes.strip(),
                "total_cents": total_cents,
            },
            line_items=line_rows,
        )
        conn.execute(
            """
            UPDATE transactions
            SET total_cents = ?, receipt_snapshot_text = ?
            WHERE id = ?
            """,
            (total_cents, receipt_text, transaction_id),
        )
        conn.execute(
            """
            INSERT INTO receipt_records (transaction_id, snapshot_text)
            VALUES (?, ?)
            """,
            (transaction_id, receipt_text),
        )

    return transaction_id


def void_transaction(conn: sqlite3.Connection, transaction_id: str, reason: str) -> None:
    with conn:
        row = conn.execute(
            "SELECT status FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown transaction: {transaction_id}")
        if row["status"] == "voided":
            return
        conn.execute(
            """
            UPDATE transactions
            SET status = 'voided', voided_at = ?, void_reason = ?
            WHERE id = ?
            """,
            (datetime.now().isoformat(timespec="seconds"), reason.strip(), transaction_id),
        )


def fetch_transaction(conn: sqlite3.Connection, transaction_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown transaction: {transaction_id}")
    return row


def fetch_transaction_lines(conn: sqlite3.Connection, transaction_id: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT li.*, mt.display_name, mt.category
            FROM transaction_line_items li
            JOIN material_types mt ON mt.id = li.material_type_id
            WHERE li.transaction_id = ?
            ORDER BY li.id
            """,
            (transaction_id,),
        )
    )
