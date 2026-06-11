from __future__ import annotations

import csv
import json
import sqlite3
from collections import defaultdict
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

from app.pdf import write_text_pdf
from app.permissions import has_permission
from app.pricing import format_cents
from app.receipt import BUSINESS_NAME_PLACEHOLDER
from app.compliance import daily_report_compliance_summary, transaction_rule_result_summary


def generate_daily_report(conn: sqlite3.Connection, report_date: date | str) -> dict[str, Any]:
    day = report_date.isoformat() if isinstance(report_date, date) else report_date
    rows = conn.execute(
        """
        SELECT
            t.id AS transaction_id,
            t.status,
            t.total_cents AS transaction_total_cents,
            t.void_reason,
            t.voided_at,
            t.voided_by_operator_name_snapshot,
            t.voided_by_operator_initials_snapshot,
            COALESCE(NULLIF(t.operator_display_name_snapshot, ''), 'Unknown') AS operator_name,
            COALESCE(
                NULLIF(t.operator_initials_snapshot, ''), t.operator_initials
            ) AS operator_initials,
            li.material_type_id,
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
    active_transaction_ids: set[str] = set()
    operator_groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "operator_name": "",
            "operator_initials": "",
            "total_cents": 0,
            "transaction_ids": set(),
        }
    )
    grand_total_cents = 0
    crv_total_cents = 0
    non_crv_total_cents = 0

    for row in rows:
        if row["status"] == "voided":
            voided.setdefault(
                row["transaction_id"],
                {
                    "transaction_id": row["transaction_id"],
                    "reason": row["void_reason"] or "",
                    "operator": _operator_label(row["operator_name"], row["operator_initials"]),
                    "voided_at": row["voided_at"] or "",
                    "approved_by": _operator_label(
                        row["voided_by_operator_name_snapshot"],
                        row["voided_by_operator_initials_snapshot"],
                    ),
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
        active_transaction_ids.add(row["transaction_id"])
        grand_total_cents += int(row["subtotal_cents"])
        if row["crv_eligible"]:
            crv_total_cents += int(row["subtotal_cents"])
        else:
            non_crv_total_cents += int(row["subtotal_cents"])
        operator_key = (row["operator_name"], row["operator_initials"])
        operator_group = operator_groups[operator_key]
        operator_group["operator_name"] = row["operator_name"]
        operator_group["operator_initials"] = row["operator_initials"]
        operator_group["total_cents"] += int(row["subtotal_cents"])
        operator_group["transaction_ids"].add(row["transaction_id"])

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
    operator_list = []
    for group in operator_groups.values():
        operator_list.append(
            {
                "operator_name": group["operator_name"],
                "operator_initials": group["operator_initials"],
                "operator_label": _operator_label(
                    group["operator_name"], group["operator_initials"]
                ),
                "total_cents": group["total_cents"],
                "transaction_count": len(group["transaction_ids"]),
            }
        )
    operator_list.sort(key=lambda g: g["operator_label"])
    voided_list = list(voided.values())
    voided_total_cents = sum(int(item["line_total_cents"]) for item in voided_list)
    database_total_cents = _database_active_total(conn, day)
    if database_total_cents != grand_total_cents:
        raise ValueError(
            "Daily report line totals do not match stored transaction totals "
            f"for {day}: {grand_total_cents} != {database_total_cents}"
        )

    return {
        "date": day,
        "groups": group_list,
        "material_breakdown": group_list,
        "operator_summaries": operator_list,
        "total_transactions": len(active_transaction_ids),
        "total_paid_cents": grand_total_cents,
        "total_crv_paid_cents": crv_total_cents,
        "total_non_crv_paid_cents": non_crv_total_cents,
        "grand_total_cents": grand_total_cents,
        "voided_transactions": voided_list,
        "void_count": len(voided_list),
        "voided_total_cents": voided_total_cents,
        "compliance": daily_report_compliance_summary(conn, day),
        "compliance_rule_results": transaction_rule_result_summary(conn, day),
    }


def generate_feet_closeout_report(
    conn: sqlite3.Connection,
    report_date: date | str,
    *,
    business_name: str = BUSINESS_NAME_PLACEHOLDER,
    period_start: str = "00:00",
    period_end: str = "23:59",
    expected_cash_cents: int | None = None,
    actual_cash_cents: int | None = None,
    discrepancy_notes: str = "",
    operator_attestation: str = "",
    manager_approval: str = "",
) -> dict[str, Any]:
    report = generate_daily_report(conn, report_date)
    discrepancy_cents = None
    if expected_cash_cents is not None and actual_cash_cents is not None:
        discrepancy_cents = int(actual_cash_cents) - int(expected_cash_cents)
    report.update(
        {
            "report_type": "FEET End-of-Day Closeout",
            "business_name": business_name.strip() or BUSINESS_NAME_PLACEHOLDER,
            "period_start": period_start.strip() or "00:00",
            "period_end": period_end.strip() or "23:59",
            "expected_cash_cents": expected_cash_cents,
            "actual_cash_cents": actual_cash_cents,
            "discrepancy_cents": discrepancy_cents,
            "discrepancy_notes": discrepancy_notes.strip(),
            "operator_attestation": operator_attestation.strip(),
            "manager_approval": manager_approval.strip(),
            "feet_principles": [
                "Preserve an audit trail",
                "Capture who took actions",
                "Log reasons for voids/corrections",
                "Provide a final snapshot at closeout",
            ],
            "disclaimer": (
                "Local-first demonstration report. Not production or compliance certified."
            ),
        }
    )
    return report


def record_feet_closeout(
    conn: sqlite3.Connection,
    report: dict[str, Any],
    *,
    generated_by_operator_id: int,
    manager_pin: str,
    operator_verified: bool = False,
    operator_label: str | None = None,
) -> int:
    from app.db import (
        REQUIRE_OPERATOR_PIN_ADMIN_KEY,
        add_audit_entry,
        format_operator_label,
        get_bool_setting,
        get_operator,
        verify_manager_pin,
    )

    operator = get_operator(conn, generated_by_operator_id)
    actor_label = operator_label or format_operator_label(operator)
    if not has_permission(operator, "run_feet_closeout"):
        raise PermissionError("Selected operator cannot run FEET closeout.")
    if not verify_manager_pin(conn, manager_pin):
        raise PermissionError("Manager PIN approval is required to run FEET closeout.")
    if get_bool_setting(conn, REQUIRE_OPERATOR_PIN_ADMIN_KEY):
        if not operator.pin_set:
            raise PermissionError(
                "Operator PIN enforcement is enabled, but this operator has no PIN."
            )
        if not operator_verified:
            raise PermissionError(
                "Operator PIN verification is required to run FEET closeout."
            )

    snapshot = json.dumps(report, sort_keys=True, separators=(",", ":"))
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO feet_closeout_reports (
                report_date, business_name, period_start, period_end,
                generated_by_operator_id, generated_by_operator_name_snapshot,
                generated_by_operator_initials_snapshot, operator_verified,
                expected_cash_cents, actual_cash_cents, discrepancy_cents,
                discrepancy_notes, operator_attestation, manager_approval,
                report_snapshot_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report["date"],
                report["business_name"],
                report["period_start"],
                report["period_end"],
                operator.id,
                operator.display_name,
                operator.initials,
                1 if operator_verified else 0,
                report["expected_cash_cents"],
                report["actual_cash_cents"],
                report["discrepancy_cents"],
                report["discrepancy_notes"],
                report["operator_attestation"],
                report["manager_approval"],
                snapshot,
            ),
        )
        closeout_id = int(cursor.lastrowid)
        add_audit_entry(
            conn,
            action_type="feet_closeout_completed",
            entity_type="feet_closeout_report",
            entity_id=closeout_id,
            before_value=None,
            after_value={
                "report_date": report["date"],
                "total_paid_cents": report["total_paid_cents"],
                "void_count": report["void_count"],
                "operator": actor_label,
            },
            operator=actor_label,
            notes=report["discrepancy_notes"],
        )
    return closeout_id


def _decimal_string_add(left: str, right: str) -> str:
    from decimal import Decimal

    return str(Decimal(left) + Decimal(right))


def _operator_label(name: str, initials: str) -> str:
    name = (name or "").strip()
    initials = (initials or "").strip()
    if name and initials:
        return f"{name} ({initials})"
    return initials or name or "Unknown"


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
        writer.writerow(["Total Transactions", report["total_transactions"]])
        writer.writerow(["Grand Total", format_cents(report["grand_total_cents"])])
        writer.writerow(["CRV Paid", format_cents(report["total_crv_paid_cents"])])
        writer.writerow(["Non-CRV Paid", format_cents(report["total_non_crv_paid_cents"])])
        writer.writerow([])
        writer.writerow(["Operator Summary"])
        writer.writerow(["Operator", "Transactions", "Total Paid"])
        for operator in report["operator_summaries"]:
            writer.writerow(
                [
                    operator["operator_label"],
                    operator["transaction_count"],
                    format_cents(operator["total_cents"]),
                ]
            )
        writer.writerow([])
        writer.writerow(["Voided/Corrected Transactions"])
        writer.writerow(["Void Count", report["void_count"]])
        writer.writerow(["Voided Amount", format_cents(report["voided_total_cents"])])
        writer.writerow(["Transaction ID", "Operator", "Reason", "Voided Line Total"])
        for voided in report["voided_transactions"]:
            writer.writerow(
                [
                    voided["transaction_id"],
                    voided["operator"],
                    voided["reason"],
                    format_cents(voided["line_total_cents"]),
                ]
            )
        _write_compliance_csv_section(writer, report)
    return path


def export_feet_closeout_csv(report: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([report["report_type"], report["date"]])
        writer.writerow(["Business", report["business_name"]])
        writer.writerow(["Period", f"{report['period_start']} - {report['period_end']}"])
        writer.writerow([])
        writer.writerow(["Summary"])
        writer.writerow(["Total Transactions", report["total_transactions"]])
        writer.writerow(["Total Paid", format_cents(report["total_paid_cents"])])
        writer.writerow(["Total CRV Paid", format_cents(report["total_crv_paid_cents"])])
        writer.writerow(["Total Non-CRV Paid", format_cents(report["total_non_crv_paid_cents"])])
        writer.writerow(["Void Count", report["void_count"]])
        writer.writerow(["Voided Amount", format_cents(report["voided_total_cents"])])
        writer.writerow(["Expected Cash", _optional_cents(report["expected_cash_cents"])])
        writer.writerow(["Actual Cash", _optional_cents(report["actual_cash_cents"])])
        writer.writerow(["Discrepancy", _optional_cents(report["discrepancy_cents"])])
        writer.writerow(["Discrepancy Notes", report["discrepancy_notes"]])
        writer.writerow([])
        writer.writerow(["Material Breakdown"])
        writer.writerow(["Grouping", "Material", "CRV", "Unit", "Quantity", "Transactions", "Total Paid"])
        for group in report["material_breakdown"]:
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
        writer.writerow(["Operator Totals"])
        writer.writerow(["Operator", "Transactions", "Total Paid"])
        for operator in report["operator_summaries"]:
            writer.writerow(
                [
                    operator["operator_label"],
                    operator["transaction_count"],
                    format_cents(operator["total_cents"]),
                ]
            )
        writer.writerow([])
        writer.writerow(["Voided Transactions"])
        writer.writerow(["Transaction ID", "Original Operator", "Approved By", "Reason", "Voided Amount"])
        for voided in report["voided_transactions"]:
            writer.writerow(
                [
                    voided["transaction_id"],
                    voided["operator"],
                    voided["approved_by"],
                    voided["reason"],
                    format_cents(voided["line_total_cents"]),
                ]
            )
        writer.writerow([])
        _write_compliance_csv_section(writer, report)
        writer.writerow([])
        writer.writerow(["Operator Attestation", report["operator_attestation"]])
        writer.writerow(["Manager Approval", report["manager_approval"]])
        writer.writerow(["Disclaimer", report["disclaimer"]])
    return path


def _write_compliance_csv_section(writer: csv.writer, report: dict[str, Any]) -> None:
    compliance = report.get("compliance", {})
    packs = compliance.get("enabled_packs", [])
    if not packs:
        return
    writer.writerow([])
    writer.writerow(["Compliance Packs"])
    for pack in packs:
        writer.writerow(
            [
                "Enabled Pack",
                pack["display_name"],
                pack["jurisdiction"],
                pack["version"],
            ]
        )
        for disclosure in pack.get("report_disclosures", []):
            writer.writerow(["Disclosure", disclosure])
        writer.writerow(["Daily Load Limits"])
        writer.writerow(["Rule", "Grouping", "Actual", "Limit", "Unit", "Severity"])
        for limit in pack.get("daily_load_limits", []):
            writer.writerow(
                [
                    limit["display_name"],
                    limit["report_grouping"],
                    limit["actual_quantity"],
                    limit["limit_quantity"],
                    limit["unit_label"] or limit["unit_type"],
                    limit["severity"],
                ]
            )
    if report.get("compliance_rule_results"):
        writer.writerow(["Rule Result Summary"])
        for result, count in sorted(report["compliance_rule_results"].items()):
            writer.writerow([result, count])


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
        f"<td>{escape(item['operator'])}</td>"
        f"<td>{escape(item['reason'])}</td>"
        f"<td>{format_cents(item['line_total_cents'])}</td>"
        "</tr>"
        for item in report["voided_transactions"]
    )
    operator_rows = "\n".join(
        "<tr>"
        f"<td>{escape(item['operator_label'])}</td>"
        f"<td>{item['transaction_count']}</td>"
        f"<td>{format_cents(item['total_cents'])}</td>"
        "</tr>"
        for item in report["operator_summaries"]
    )
    compliance_html = _render_compliance_html(report)
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
  <p>Total Transactions: {report['total_transactions']}<br>
  CRV Paid: {format_cents(report['total_crv_paid_cents'])}<br>
  Non-CRV Paid: {format_cents(report['total_non_crv_paid_cents'])}</p>
  <h2>Operator Summary</h2>
  <table>
    <thead><tr><th>Operator</th><th>Transactions</th><th>Total Paid</th></tr></thead>
    <tbody>{operator_rows}</tbody>
  </table>
  <h2>Voided/Corrected Transactions</h2>
  <p>Void Count: {report['void_count']}<br>
  Voided Amount: {format_cents(report['voided_total_cents'])}</p>
  <table>
    <thead>
      <tr><th>Transaction ID</th><th>Operator</th><th>Reason</th><th>Voided Line Total</th></tr>
    </thead>
    <tbody>{voided_rows}</tbody>
  </table>
  {compliance_html}
  <p>PDF export and certified processor reporting are future extension points.</p>
</body>
</html>
"""


def _render_compliance_html(report: dict[str, Any]) -> str:
    packs = report.get("compliance", {}).get("enabled_packs", [])
    if not packs:
        return ""
    sections = ["<h2>Compliance Pack Support</h2>"]
    for pack in packs:
        limit_rows = "\n".join(
            "<tr>"
            f"<td>{escape(limit['display_name'])}</td>"
            f"<td>{escape(limit['report_grouping'])}</td>"
            f"<td>{escape(limit['actual_quantity'])}</td>"
            f"<td>{escape(limit['limit_quantity'])}</td>"
            f"<td>{escape(limit['unit_label'] or limit['unit_type'])}</td>"
            f"<td>{escape(limit['severity'])}</td>"
            "</tr>"
            for limit in pack.get("daily_load_limits", [])
        )
        disclosures = "".join(
            f"<li>{escape(text)}</li>" for text in pack.get("report_disclosures", [])
        )
        recordkeeping = "".join(
            f"<li>{escape(text)}</li>"
            for text in pack.get("recordkeeping_requirements", [])
        )
        sections.append(
            f"""
  <h3>{escape(pack['display_name'])} {escape(pack['version'])}</h3>
  <p>Jurisdiction: {escape(pack['jurisdiction'])}<br>
  {escape(pack['disclaimer'])}</p>
  <ul>{disclosures}{recordkeeping}</ul>
  <table>
    <thead><tr><th>Rule</th><th>Grouping</th><th>Actual</th><th>Limit</th><th>Unit</th><th>Severity</th></tr></thead>
    <tbody>{limit_rows}</tbody>
  </table>
"""
        )
    if report.get("compliance_rule_results"):
        items = "".join(
            f"<li>{escape(result)}: {count}</li>"
            for result, count in sorted(report["compliance_rule_results"].items())
        )
        sections.append(f"<h3>Rule Result Summary</h3><ul>{items}</ul>")
    sections.append(
        "<p>Not compliance-certified. Final CRV rules must be verified before production use.</p>"
    )
    return "\n".join(sections)


def render_feet_closeout_html(report: dict[str, Any]) -> str:
    base = render_daily_report_html(report)
    additions = f"""
  <h2>FEET Closeout Checks</h2>
  <p>Business: {escape(report['business_name'])}<br>
  Period: {escape(report['period_start'])} - {escape(report['period_end'])}<br>
  Expected Cash: {_optional_cents(report['expected_cash_cents'])}<br>
  Actual Cash: {_optional_cents(report['actual_cash_cents'])}<br>
  Discrepancy: {_optional_cents(report['discrepancy_cents'])}</p>
  <p>Discrepancy Notes: {escape(report['discrepancy_notes'])}</p>
  <p>Operator Attestation: {escape(report['operator_attestation'])}</p>
  <p>Manager Approval: {escape(report['manager_approval'])}</p>
  <p>{escape(report['disclaimer'])}</p>
"""
    return base.replace("</body>", additions + "</body>")


def export_feet_closeout_pdf(report: dict[str, Any], output_path: str | Path) -> Path:
    return write_text_pdf(
        feet_closeout_report_to_text(report),
        output_path,
        title=f"FEET Closeout {report['date']}",
    )


def feet_closeout_report_to_text(report: dict[str, Any]) -> str:
    lines = [
        f"{report['report_type']} - {report['date']}",
        f"Business: {report['business_name']}",
        f"Period: {report['period_start']} - {report['period_end']}",
        "-" * 72,
        f"Total transactions: {report['total_transactions']}",
        f"Total paid: {format_cents(report['total_paid_cents'])}",
        f"Total CRV paid: {format_cents(report['total_crv_paid_cents'])}",
        f"Total non-CRV paid: {format_cents(report['total_non_crv_paid_cents'])}",
        f"Voided transactions: {report['void_count']}",
        f"Voided amount: {format_cents(report['voided_total_cents'])}",
        f"Expected cash: {_optional_cents(report['expected_cash_cents'])}",
        f"Actual cash: {_optional_cents(report['actual_cash_cents'])}",
        f"Discrepancy: {_optional_cents(report['discrepancy_cents'])}",
        f"Discrepancy notes: {report['discrepancy_notes']}",
        "",
        "Material Breakdown",
    ]
    for group in report["material_breakdown"]:
        lines.append(
            f"- {group['description']} ({group['report_grouping']}): "
            f"{group['quantity_total']} {group['unit_type']}, "
            f"{format_cents(group['total_cents'])}"
        )
    lines.extend(["", "Operator Totals"])
    for operator in report["operator_summaries"]:
        lines.append(
            f"- {operator['operator_label']}: {operator['transaction_count']} tx, "
            f"{format_cents(operator['total_cents'])}"
        )
    lines.extend(["", "Voided Transactions"])
    if not report["voided_transactions"]:
        lines.append("- none")
    for voided in report["voided_transactions"]:
        lines.append(
            f"- {voided['transaction_id']}: {format_cents(voided['line_total_cents'])}, "
            f"approved by {voided['approved_by']}, reason: {voided['reason']}"
        )
    packs = report.get("compliance", {}).get("enabled_packs", [])
    if packs:
        lines.extend(["", "Compliance Pack Support"])
        for pack in packs:
            lines.append(
                f"- {pack['display_name']} {pack['version']} ({pack['jurisdiction']})"
            )
            for disclosure in pack.get("report_disclosures", []):
                lines.append(f"  Disclosure: {disclosure}")
            for limit in pack.get("daily_load_limits", []):
                lines.append(
                    f"  {limit['display_name']}: actual {limit['actual_quantity']} "
                    f"/ limit {limit['limit_quantity']} "
                    f"{limit['unit_label'] or limit['unit_type']}"
                )
        if report.get("compliance_rule_results"):
            summary = ", ".join(
                f"{result}={count}"
                for result, count in sorted(report["compliance_rule_results"].items())
            )
            lines.append(f"  Rule results: {summary}")
        lines.append("  Not compliance-certified. Final CRV rules require review.")
    lines.extend(
        [
            "",
            f"Operator attestation: {report['operator_attestation']}",
            f"Manager approval: {report['manager_approval']}",
            "",
            "FEET principles:",
        ]
    )
    lines.extend(f"- {item}" for item in report["feet_principles"])
    lines.extend(["", report["disclaimer"]])
    return "\n".join(lines)


def _database_active_total(conn: sqlite3.Connection, day: str) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(total_cents), 0) AS total
        FROM transactions
        WHERE date(created_at) = ? AND status != 'voided'
        """,
        (day,),
    ).fetchone()
    return int(row["total"])


def _optional_cents(value: int | None) -> str:
    return "" if value is None else format_cents(int(value))
