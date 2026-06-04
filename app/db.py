from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.models import LineItemInput, MaterialType, TransactionInput
from app.pricing import cents_for_quantity
from app.receipt import build_receipt_text


DEFAULT_DB_PATH = Path("data/recycling_pos.sqlite3")


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
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_rates_material_effective
            ON rates(material_type_id, effective_from, effective_to);

        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            operator_initials TEXT NOT NULL,
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
        """
    )
    conn.commit()


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
    )


def list_materials(conn: sqlite3.Connection, active_only: bool = True) -> list[MaterialType]:
    sql = "SELECT * FROM material_types"
    params: tuple[object, ...] = ()
    if active_only:
        sql += " WHERE active = ?"
        params = (1,)
    sql += " ORDER BY report_grouping, display_name"
    return [material_from_row(row) for row in conn.execute(sql, params)]


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
          AND effective_from <= ?
          AND (effective_to IS NULL OR effective_to >= ?)
        ORDER BY effective_from DESC, id DESC
        LIMIT 1
        """,
        (material_type_id, as_of, as_of),
    ).fetchone()
    if row is None:
        material = conn.execute(
            "SELECT default_rate_cents_per_unit FROM material_types WHERE id = ?",
            (material_type_id,),
        ).fetchone()
        if material is None:
            raise ValueError(f"Unknown material_type_id: {material_type_id}")
        return int(material["default_rate_cents_per_unit"])
    return int(row["rate_cents_per_unit"])


def create_transaction(
    conn: sqlite3.Connection,
    payload: TransactionInput,
    created_at: datetime | None = None,
) -> str:
    if not payload.line_items:
        raise ValueError("A transaction must include at least one line item.")

    created_at = created_at or datetime.now()
    transaction_id = str(uuid4())
    line_rows: list[dict[str, object]] = []
    total_cents = 0

    with conn:
        conn.execute(
            """
            INSERT INTO transactions (
                id, created_at, operator_initials, payout_method, notes, status, total_cents
            )
            VALUES (?, ?, ?, ?, ?, 'active', 0)
            """,
            (
                transaction_id,
                created_at.isoformat(timespec="seconds"),
                payload.operator_initials.strip().upper() or "NA",
                payload.payout_method.strip() or "cash",
                payload.notes.strip(),
            ),
        )

        for item in payload.line_items:
            material = get_material(conn, item.material_type_id)
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
                "operator_initials": payload.operator_initials.strip().upper() or "NA",
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

