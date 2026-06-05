from __future__ import annotations

import sqlite3

import pytest

from app.db import connect, create_operator, init_db
from app.seed_data import seed_materials


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = connect(":memory:")
    init_db(connection)
    seed_materials(connection, effective_from="2026-01-01")
    create_operator(
        connection,
        display_name="Test Operator",
        initials="TO",
        role="manager",
        audit=False,
    )
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def operator_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM operators WHERE initials = 'TO'").fetchone()
    return int(row["id"])
