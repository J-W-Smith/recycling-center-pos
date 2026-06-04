from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal

from app.db import add_rate, create_transaction, fetch_transaction, get_material_by_key
from app.models import LineItemInput, TransactionInput
from app.receipt import receipt_text_to_html


def test_receipt_snapshot_preserved_after_rate_change(conn: sqlite3.Connection) -> None:
    material = get_material_by_key(conn, "large_crv_count")
    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("3"))],
            operator_initials="EF",
            payout_method="cash",
            notes="snapshot test",
        ),
        created_at=datetime(2026, 6, 4, 12, 0, 0),
    )
    before = fetch_transaction(conn, tx_id)["receipt_snapshot_text"]

    add_rate(
        conn,
        material_type_id=material.id,
        rate_cents_per_unit=999,
        effective_from="2026-06-05",
        notes="test future rate",
        replace_current=True,
    )

    after = fetch_transaction(conn, tx_id)["receipt_snapshot_text"]
    receipt_records = conn.execute(
        "SELECT COUNT(*) AS count FROM receipt_records WHERE transaction_id = ?", (tx_id,)
    ).fetchone()["count"]

    assert before == after
    assert "TOTAL PAID: $0.30" in after
    assert receipt_records == 1


def test_receipt_html_escapes_snapshot_text() -> None:
    html = receipt_text_to_html("Manual <review> & print")
    assert "Manual &lt;review&gt; &amp; print" in html
