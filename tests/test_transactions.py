from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal

from app.db import create_transaction, fetch_transaction, get_material_by_key, void_transaction
from app.models import LineItemInput, TransactionInput


def test_mixed_transaction_total(conn: sqlite3.Connection) -> None:
    small = get_material_by_key(conn, "aluminum_crv_count_small")
    scrap = get_material_by_key(conn, "scrap_aluminum_weight")

    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[
                LineItemInput(small.id, Decimal("10")),
                LineItemInput(scrap.id, Decimal("2.5")),
            ],
            operator_initials="ab",
            payout_method="cash",
            notes="mixed test",
        ),
        created_at=datetime(2026, 6, 4, 10, 0, 0),
    )

    tx = fetch_transaction(conn, tx_id)
    assert tx["total_cents"] == 250
    assert tx["operator_initials"] == "AB"
    assert "TOTAL PAID: $2.50" in tx["receipt_snapshot_text"]


def test_voided_transaction_is_marked_not_deleted(conn: sqlite3.Connection) -> None:
    material = get_material_by_key(conn, "plastic_crv_count_small")
    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("5"))],
            operator_initials="CD",
        ),
        created_at=datetime(2026, 6, 4, 11, 0, 0),
    )

    void_transaction(conn, tx_id, "wrong material")
    tx = fetch_transaction(conn, tx_id)

    assert tx["status"] == "voided"
    assert tx["void_reason"] == "wrong material"
    assert tx["receipt_snapshot_text"]

