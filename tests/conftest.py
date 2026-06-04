from __future__ import annotations

import sqlite3

import pytest

from app.db import connect, init_db
from app.seed_data import seed_materials


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = connect(":memory:")
    init_db(connection)
    seed_materials(connection, effective_from="2026-01-01")
    try:
        yield connection
    finally:
        connection.close()

