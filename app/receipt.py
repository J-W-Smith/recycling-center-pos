from __future__ import annotations

import os
import tempfile
from html import escape
from pathlib import Path
from typing import Mapping, Sequence

from app.pdf import write_text_pdf
from app.pricing import format_cents


BUSINESS_NAME_PLACEHOLDER = "RECYCLING CENTER NAME"
COPY_CUSTOMER = "CUSTOMER COPY"
COPY_OFFICE = "OFFICE COPY"


class ReceiptPrintUnavailable(RuntimeError):
    pass


def build_receipt_text(
    transaction: Mapping[str, object],
    line_items: Sequence[Mapping[str, object]],
    business_name: str = BUSINESS_NAME_PLACEHOLDER,
    copy_label: str = COPY_CUSTOMER,
) -> str:
    status = str(transaction.get("status", "active")).upper()
    is_voided = status == "VOIDED"
    lines = [
        business_name,
        copy_label,
        "FEET AUDIT RECEIPT SNAPSHOT",
        "-" * 42,
        f"Date/Time: {transaction['created_at']}",
        f"Transaction ID: {transaction['id']}",
        f"Operator: {_operator_label(transaction)}",
        f"Operator Verified: {_verification_label(transaction)}",
        f"Payout Method: {transaction['payout_method']}",
        f"Status: {status}",
        "-" * 42,
    ]
    if is_voided:
        lines.extend(
            [
                "VOID MARK: VOIDED TRANSACTION",
                f"Voided At: {transaction.get('voided_at') or 'not recorded'}",
                f"Approved/Reason: {transaction.get('void_reason') or 'not recorded'}",
                "-" * 42,
            ]
        )
    for item in line_items:
        crv_label = "CRV" if item["crv_eligible"] else "NON-CRV"
        lines.extend(
            [
                f"Material: {item.get('material_display_name') or item['description']}",
                f"  Description: {item['description']}",
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
            "FEET Indicators:",
            f"  Operator verification: {_verification_label(transaction)}",
            f"  Void mark: {'YES' if is_voided else 'NO'}",
            f"  Note/approved reason: {transaction.get('void_reason') or transaction.get('notes') or 'none'}",
            "",
            f"Notes: {transaction.get('notes', '')}",
            "",
            "Local-first demonstration output. Not compliance certified.",
        ]
    )
    return "\n".join(lines)


def build_receipt_copies_text(
    transaction: Mapping[str, object],
    line_items: Sequence[Mapping[str, object]],
    business_name: str = BUSINESS_NAME_PLACEHOLDER,
) -> str:
    return "\n\n".join(
        [
            build_receipt_text(transaction, line_items, business_name, COPY_CUSTOMER),
            build_receipt_text(transaction, line_items, business_name, COPY_OFFICE),
        ]
    )


def export_receipt_pdf(
    receipt_text: str,
    output_path: str | Path,
    *,
    title: str = "Receipt",
) -> Path:
    return write_text_pdf(receipt_text, output_path, title=title)


def export_receipt_text(receipt_text: str, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(receipt_text, encoding="utf-8")
    return path


def print_receipt_text(receipt_text: str) -> Path:
    """Send receipt text to the OS print verb when available.

    The returned path is the temporary print spool file. On non-Windows systems the
    caller can still export PDF/text and print from the viewer.
    """
    if os.name != "nt" or not hasattr(os, "startfile"):
        raise ReceiptPrintUnavailable("OS print verb is only available on Windows.")
    handle = tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        suffix=".txt",
        prefix="recycling-pos-receipt-",
        encoding="utf-8",
    )
    with handle:
        handle.write(receipt_text)
    os.startfile(handle.name, "print")  # type: ignore[attr-defined]
    return Path(handle.name)


def _operator_label(transaction: Mapping[str, object]) -> str:
    display_name = str(transaction.get("operator_display_name", "")).strip()
    initials = str(transaction.get("operator_initials", "")).strip()
    if display_name and initials:
        return f"{display_name} ({initials})"
    return initials or display_name or "Unknown"


def _verification_label(transaction: Mapping[str, object]) -> str:
    return "PIN VERIFIED" if bool(transaction.get("operator_verified")) else "NOT VERIFIED"


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


def mark_voided_receipt_text(
    receipt_text: str, *, voided_at: str = "", reason: str = "", approved_by: str = ""
) -> str:
    lines = [
        "VOIDED TRANSACTION",
        f"Void Date/Time: {voided_at or 'unknown'}",
        f"Void Reason: {reason or 'not recorded'}",
        f"Approved By: {approved_by or 'not recorded'}",
        "-" * 42,
        receipt_text,
    ]
    return "\n".join(lines)
