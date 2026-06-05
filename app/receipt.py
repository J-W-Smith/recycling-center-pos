from __future__ import annotations

from html import escape
from typing import Mapping, Sequence

from app.pricing import format_cents


BUSINESS_NAME_PLACEHOLDER = "RECYCLING CENTER NAME"


def build_receipt_text(
    transaction: Mapping[str, object],
    line_items: Sequence[Mapping[str, object]],
    business_name: str = BUSINESS_NAME_PLACEHOLDER,
) -> str:
    lines = [
        business_name,
        "CUSTOMER RECEIPT / INTERNAL COPY",
        "-" * 42,
        f"Date/Time: {transaction['created_at']}",
        f"Transaction ID: {transaction['id']}",
        f"Operator: {_operator_label(transaction)}",
        f"Payout Method: {transaction['payout_method']}",
        "-" * 42,
    ]
    for item in line_items:
        crv_label = "CRV" if item["crv_eligible"] else "NON-CRV"
        lines.extend(
            [
                str(item["description"]),
                f"  Type: {crv_label} / {item['report_grouping']}",
                f"  Qty: {item['quantity']} {item['unit_type']}",
                f"  Rate: {format_cents(int(item['rate_cents_per_unit']))} per unit",
                f"  Subtotal: {format_cents(int(item['subtotal_cents']))}",
            ]
        )
    lines.extend(
        [
            "-" * 42,
            f"TOTAL PAID: {format_cents(int(transaction['total_cents']))}",
            "",
            f"Notes: {transaction.get('notes', '')}",
            "",
            "Compliance Notes:",
            "CRV rules, load limits, recordkeeping, and certification requirements",
            "must be reviewed against current CalRecycle guidance before use.",
            "",
            "Printer Extension: thermal printer support not implemented in MVP.",
        ]
    )
    return "\n".join(lines)


def _operator_label(transaction: Mapping[str, object]) -> str:
    display_name = str(transaction.get("operator_display_name", "")).strip()
    initials = str(transaction.get("operator_initials", "")).strip()
    if display_name and initials:
        return f"{display_name} ({initials})"
    return initials or display_name or "Unknown"


def receipt_text_to_html(receipt_text: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Receipt</title>
  <style>
    body {{ font-family: "Courier New", monospace; font-size: 12px; }}
    pre {{ white-space: pre-wrap; }}
    @media print {{ .no-print {{ display: none; }} }}
  </style>
</head>
<body>
  <button class="no-print" onclick="window.print()">Print Two Copies</button>
  <pre>{escape(receipt_text)}</pre>
</body>
</html>
"""
