from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal

from app.db import add_rate, create_transaction, fetch_transaction, get_material_by_key
from app.db import set_operator_pin, update_operator
from app.models import LineItemInput, TransactionInput
from app.receipt import export_receipt_pdf, mark_voided_receipt_text, receipt_text_to_html


def test_receipt_snapshot_preserved_after_rate_change(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    material = get_material_by_key(conn, "large_crv_count")
    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("3"))],
            operator_id=operator_id,
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


def test_receipt_includes_copies_line_items_and_operator_snapshot(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    set_operator_pin(conn, operator_id, "1234", audit=False)
    material = get_material_by_key(conn, "aluminum_crv_count_small")
    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("12"))],
            operator_id=operator_id,
            operator_verified=True,
            payout_method="cash",
            notes="customer copy test",
        ),
        created_at=datetime(2026, 6, 4, 10, 0, 0),
    )
    before = fetch_transaction(conn, tx_id)["receipt_snapshot_text"]

    update_operator(
        conn,
        operator_id,
        display_name="Renamed Operator",
        initials="RO",
        role="manager",
        active=True,
        audit=False,
    )
    after = fetch_transaction(conn, tx_id)["receipt_snapshot_text"]

    assert before == after
    assert "CUSTOMER COPY" in after
    assert "OFFICE COPY" in after
    assert "FEET AUDIT RECEIPT SNAPSHOT" in after
    assert "Material: Aluminum CRV by count, small container" in after
    assert "Qty: 12 count" in after
    assert "Rate: $0.05 per unit" in after
    assert "Subtotal: $0.60" in after
    assert "Operator: Test Operator (TO)" in after
    assert "Operator Verified: PIN VERIFIED" in after


def test_voided_receipt_display_adds_void_mark_and_approval() -> None:
    receipt = mark_voided_receipt_text(
        "Transaction ID: demo",
        voided_at="2026-06-04T12:00:00",
        reason="duplicate ticket",
        approved_by="Manager (MG)",
    )

    assert "VOIDED TRANSACTION" in receipt
    assert "Void Reason: duplicate ticket" in receipt
    assert "Approved By: Manager (MG)" in receipt


def test_receipt_pdf_export_writes_valid_pdf(tmp_path) -> None:
    path = export_receipt_pdf("Receipt\nTOTAL PAID: $1.00", tmp_path / "receipt.pdf")

    assert path.read_bytes().startswith(b"%PDF-1.4")


def test_receipt_html_escapes_snapshot_text() -> None:
    html = receipt_text_to_html("Manual <review> & print")
    assert "Manual &lt;review&gt; &amp; print" in html
