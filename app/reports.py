from __future__ import annotations

import csv
import sqlite3
from collections import defaultdict
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

from app.pricing import format_cents


def generate_daily_report(conn: sqlite3.Connection, report_date: date | str) -> dict[str, Any]:
    day = report_date.isoformat() if isinstance(report_date, date) else report_date
    rows = conn.execute(
        """
        SELECT
            t.id AS transaction_id,
            t.status,
            t.total_cents AS transaction_total_cents,
            t.void_reason,
            li.description,
            li.quantity,
            li.unit_type,
            li.subtotal_cents,
            li.crv_eligible,
            li.report_grouping
        FROM transactions t
        JOIN transaction_line_items li ON li.transaction_id = t.id
        WHERE date(t.created_at) = ?
        ORDER BY li.report_grouping, li.description, t.created_at
        """,
        (day,),
    ).fetchall()

    groups: dict[tuple[str, str, str, bool], dict[str, Any]] = defaultdict(
        lambda: {
            "report_grouping": "",
            "description": "",
            "unit_type": "",
            "crv_eligible": False,
            "quantity_total": "0",
            "total_cents": 0,
            "transaction_ids": set(),
        }
    )
    voided: dict[str, dict[str, Any]] = {}
    grand_total_cents = 0

    for row in rows:
        if row["status"] == "voided":
            voided.setdefault(
                row["transaction_id"],
                {
                    "transaction_id": row["transaction_id"],
                    "reason": row["void_reason"] or "",
                    "line_total_cents": 0,
                },
            )
            voided[row["transaction_id"]]["line_total_cents"] += int(row["subtotal_cents"])
            continue

        key = (
            row["report_grouping"],
            row["description"],
            row["unit_type"],
            bool(row["crv_eligible"]),
        )
        group = groups[key]
        group["report_grouping"] = row["report_grouping"]
        group["description"] = row["description"]
        group["unit_type"] = row["unit_type"]
        group["crv_eligible"] = bool(row["crv_eligible"])
        group["quantity_total"] = str(
            _decimal_string_add(group["quantity_total"], row["quantity"])
        )
        group["total_cents"] += int(row["subtotal_cents"])
        group["transaction_ids"].add(row["transaction_id"])
        grand_total_cents += int(row["subtotal_cents"])

    group_list = []
    for group in groups.values():
        group_list.append(
            {
                "report_grouping": group["report_grouping"],
                "description": group["description"],
                "unit_type": group["unit_type"],
                "crv_eligible": group["crv_eligible"],
                "quantity_total": group["quantity_total"],
                "total_cents": group["total_cents"],
                "transaction_count": len(group["transaction_ids"]),
            }
        )
    group_list.sort(key=lambda g: (g["report_grouping"], g["description"]))

    return {
        "date": day,
        "groups": group_list,
        "grand_total_cents": grand_total_cents,
        "voided_transactions": list(voided.values()),
    }


def _decimal_string_add(left: str, right: str) -> str:
    from decimal import Decimal

    return str(Decimal(left) + Decimal(right))


def export_daily_report_csv(report: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Daily Report", report["date"]])
        writer.writerow([])
        writer.writerow(
            [
                "Grouping",
                "Description",
                "CRV",
                "Unit",
                "Quantity",
                "Transactions",
                "Total Paid",
            ]
        )
        for group in report["groups"]:
            writer.writerow(
                [
                    group["report_grouping"],
                    group["description"],
                    "yes" if group["crv_eligible"] else "no",
                    group["unit_type"],
                    group["quantity_total"],
                    group["transaction_count"],
                    format_cents(group["total_cents"]),
                ]
            )
        writer.writerow([])
        writer.writerow(["Grand Total", format_cents(report["grand_total_cents"])])
        writer.writerow([])
        writer.writerow(["Voided/Corrected Transactions"])
        writer.writerow(["Transaction ID", "Reason", "Voided Line Total"])
        for voided in report["voided_transactions"]:
            writer.writerow(
                [
                    voided["transaction_id"],
                    voided["reason"],
                    format_cents(voided["line_total_cents"]),
                ]
            )
    return path


def render_daily_report_html(report: dict[str, Any]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{escape(group['report_grouping'])}</td>"
        f"<td>{escape(group['description'])}</td>"
        f"<td>{'yes' if group['crv_eligible'] else 'no'}</td>"
        f"<td>{escape(group['unit_type'])}</td>"
        f"<td>{escape(group['quantity_total'])}</td>"
        f"<td>{group['transaction_count']}</td>"
        f"<td>{format_cents(group['total_cents'])}</td>"
        "</tr>"
        for group in report["groups"]
    )
    voided_rows = "\n".join(
        "<tr>"
        f"<td>{escape(item['transaction_id'])}</td>"
        f"<td>{escape(item['reason'])}</td>"
        f"<td>{format_cents(item['line_total_cents'])}</td>"
        "</tr>"
        for item in report["voided_transactions"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Daily Report {escape(report['date'])}</title>
  <style>
    body {{ font-family: Arial, sans-serif; font-size: 13px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
    th, td {{ border: 1px solid #777; padding: 4px 6px; text-align: left; }}
    th {{ background: #ddd; }}
    @media print {{ .no-print {{ display: none; }} }}
  </style>
</head>
<body>
  <button class="no-print" onclick="window.print()">Print</button>
  <h1>Daily Report {escape(report['date'])}</h1>
  <table>
    <thead>
      <tr>
        <th>Grouping</th><th>Description</th><th>CRV</th><th>Unit</th>
        <th>Quantity</th><th>Transactions</th><th>Total Paid</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <h2>Grand Total: {format_cents(report['grand_total_cents'])}</h2>
  <h2>Voided/Corrected Transactions</h2>
  <table>
    <thead><tr><th>Transaction ID</th><th>Reason</th><th>Voided Line Total</th></tr></thead>
    <tbody>{voided_rows}</tbody>
  </table>
  <p>PDF export and certified processor reporting are future extension points.</p>
</body>
</html>
"""

