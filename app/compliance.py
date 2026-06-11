from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from app.models import LineItemInput, TransactionInput


CA_CRV_PACK_KEY = "ca_crv"


class ComplianceValidationError(ValueError):
    def __init__(self, results: Iterable["ComplianceCheckResult"]) -> None:
        self.results = list(results)
        message = "\n".join(result.message for result in self.results)
        super().__init__(message or "Compliance validation failed.")


@dataclass(frozen=True)
class ComplianceCheckResult:
    pack_key: str
    rule_key: str
    severity: str
    result: str
    message: str
    details: dict[str, Any]


def validate_transaction(
    conn: sqlite3.Connection,
    payload: TransactionInput,
    created_at: datetime | None = None,
) -> list[ComplianceCheckResult]:
    created_at = created_at or datetime.now()
    as_of = created_at.date().isoformat()
    results: list[ComplianceCheckResult] = []
    pack_rows = _enabled_pack_rows(conn)
    if not pack_rows:
        return results
    draft_items = _draft_items(conn, payload.line_items)
    for pack in pack_rows:
        rules = _enabled_rule_rows(conn, int(pack["id"]), as_of)
        for rule in rules:
            rule_type = rule["rule_type"]
            if rule_type == "daily_load_limit":
                result = _evaluate_daily_load_limit(
                    conn, pack, rule, draft_items, created_at.date()
                )
            elif rule_type == "count_payment_limit":
                result = _evaluate_count_payment_limit(pack, rule, draft_items)
            elif rule_type == "audit_requirement":
                result = _evaluate_audit_requirement(pack, rule, payload, draft_items)
            elif rule_type == "warning":
                result = _evaluate_info_warning(pack, rule, draft_items)
            else:
                result = None
            if result is not None:
                results.append(result)
    return results


def blocking_results(results: Iterable[ComplianceCheckResult]) -> list[ComplianceCheckResult]:
    return [result for result in results if result.result == "blocked"]


def warning_results(results: Iterable[ComplianceCheckResult]) -> list[ComplianceCheckResult]:
    return [result for result in results if result.result == "warning"]


def format_results_for_display(results: Iterable[ComplianceCheckResult]) -> str:
    return "\n".join(f"- {result.message}" for result in results)


def save_transaction_rule_results(
    conn: sqlite3.Connection,
    transaction_id: str,
    results: Iterable[ComplianceCheckResult],
) -> None:
    for result in results:
        conn.execute(
            """
            INSERT INTO transaction_rule_results (
                transaction_id, pack_key, rule_key, severity, result, message, details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transaction_id,
                result.pack_key,
                result.rule_key,
                result.severity,
                result.result,
                result.message,
                json.dumps(result.details, sort_keys=True),
            ),
        )


def receipt_disclosures_for_line_items(
    conn: sqlite3.Connection, line_items: Iterable[dict[str, object]]
) -> list[str]:
    if not any(bool(item.get("crv_eligible")) for item in line_items):
        return []
    disclosures: list[str] = []
    for pack in _enabled_pack_rows(conn):
        for rule in _enabled_rule_rows(conn, int(pack["id"]), date.today().isoformat()):
            if rule["rule_type"] != "receipt_disclosure":
                continue
            text = str(_config(rule).get("text", "")).strip()
            if text and text not in disclosures:
                disclosures.append(text)
    return disclosures


def daily_report_compliance_summary(
    conn: sqlite3.Connection, report_date: str
) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    for pack in _enabled_pack_rows(conn):
        rules = _enabled_rule_rows(conn, int(pack["id"]), report_date)
        daily_limits = []
        disclosures = []
        recordkeeping = []
        for rule in rules:
            config = _config(rule)
            if rule["rule_type"] == "daily_load_limit":
                report_grouping = str(config.get("report_grouping", ""))
                unit_type = str(config.get("unit_type", "weight"))
                actual = _existing_daily_quantity(
                    conn,
                    report_date,
                    report_grouping=report_grouping,
                    unit_type=unit_type,
                )
                daily_limits.append(
                    {
                        "rule_key": rule["rule_key"],
                        "display_name": rule["display_name"],
                        "report_grouping": report_grouping,
                        "unit_type": unit_type,
                        "limit_quantity": str(config.get("limit_quantity", "")),
                        "actual_quantity": str(actual),
                        "unit_label": str(config.get("unit_label", "")),
                        "severity": rule["severity"],
                    }
                )
            elif rule["rule_type"] == "report_requirement":
                text = str(config.get("text", "")).strip()
                if text:
                    disclosures.append(text)
            elif rule["rule_type"] == "audit_requirement":
                recordkeeping.append(rule["display_name"])
        summaries.append(
            {
                "pack_key": pack["pack_key"],
                "display_name": pack["display_name"],
                "version": pack["version"],
                "jurisdiction": pack["jurisdiction"],
                "daily_load_limits": daily_limits,
                "report_disclosures": disclosures,
                "recordkeeping_requirements": recordkeeping,
                "disclaimer": (
                    "Compliance packs provide configurable support and are not "
                    "compliance certification."
                ),
            }
        )
    return {"enabled_packs": summaries}


def transaction_rule_result_summary(
    conn: sqlite3.Connection, report_date: str
) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT trr.result, COUNT(*) AS count
        FROM transaction_rule_results trr
        JOIN transactions t ON t.id = trr.transaction_id
        WHERE date(t.created_at) = ?
        GROUP BY trr.result
        """,
        (report_date,),
    ).fetchall()
    return {row["result"]: int(row["count"]) for row in rows}


def _enabled_pack_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM compliance_packs WHERE enabled = 1 ORDER BY built_in DESC, display_name"
        )
    )


def _enabled_rule_rows(
    conn: sqlite3.Connection, pack_id: int, as_of: str
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT *
            FROM compliance_rules
            WHERE pack_id = ?
              AND enabled = 1
              AND effective_start_date <= ?
              AND (effective_end_date IS NULL OR effective_end_date >= ?)
            ORDER BY rule_type, display_name
            """,
            (pack_id, as_of, as_of),
        )
    )


def _draft_items(
    conn: sqlite3.Connection, items: Iterable[LineItemInput]
) -> list[dict[str, Any]]:
    draft_items = []
    for item in items:
        row = conn.execute(
            "SELECT * FROM material_types WHERE id = ?", (item.material_type_id,)
        ).fetchone()
        if row is None:
            continue
        draft_items.append(
            {
                "material_type_id": int(row["id"]),
                "material_key": row["key"],
                "display_name": row["display_name"],
                "report_grouping": row["report_grouping"],
                "unit_type": row["unit_type"],
                "crv_eligible": bool(row["crv_eligible"]),
                "quantity": Decimal(item.quantity),
            }
        )
    return draft_items


def _evaluate_daily_load_limit(
    conn: sqlite3.Connection,
    pack: sqlite3.Row,
    rule: sqlite3.Row,
    draft_items: list[dict[str, Any]],
    report_day: date,
) -> ComplianceCheckResult | None:
    config = _config(rule)
    report_grouping = str(config.get("report_grouping", ""))
    unit_type = str(config.get("unit_type", "weight"))
    if not report_grouping:
        return None
    draft_total = sum(
        item["quantity"]
        for item in draft_items
        if item["crv_eligible"]
        and item["unit_type"] == unit_type
        and item["report_grouping"] == report_grouping
    )
    if draft_total == 0:
        return None
    existing_total = _existing_daily_quantity(
        conn,
        report_day.isoformat(),
        report_grouping=report_grouping,
        unit_type=unit_type,
    )
    limit = Decimal(str(config.get("limit_quantity", "0")))
    combined = existing_total + draft_total
    if combined > limit:
        result = _result_for_severity(rule["severity"])
        unit_label = str(config.get("unit_label", unit_type))
        return ComplianceCheckResult(
            pack_key=pack["pack_key"],
            rule_key=rule["rule_key"],
            severity=rule["severity"],
            result=result,
            message=(
                f"{rule['display_name']} exceeded: existing {existing_total} "
                f"+ current {draft_total} = {combined} {unit_label}; "
                f"configured limit is {limit} {unit_label}."
            ),
            details={
                "existing_quantity": str(existing_total),
                "draft_quantity": str(draft_total),
                "combined_quantity": str(combined),
                "limit_quantity": str(limit),
                "report_grouping": report_grouping,
                "unit_type": unit_type,
            },
        )
    return ComplianceCheckResult(
        pack_key=pack["pack_key"],
        rule_key=rule["rule_key"],
        severity=rule["severity"],
        result="passed",
        message=f"{rule['display_name']} checked.",
        details={
            "combined_quantity": str(combined),
            "limit_quantity": str(limit),
            "report_grouping": report_grouping,
            "unit_type": unit_type,
        },
    )


def _evaluate_count_payment_limit(
    pack: sqlite3.Row,
    rule: sqlite3.Row,
    draft_items: list[dict[str, Any]],
) -> ComplianceCheckResult | None:
    config = _config(rule)
    material_keys = set(config.get("material_keys", []))
    limit = Decimal(str(config.get("limit_quantity", "0")))
    matches = [
        item
        for item in draft_items
        if item["crv_eligible"]
        and item["unit_type"] == "count"
        and (not material_keys or item["material_key"] in material_keys)
    ]
    if not matches:
        return None
    messages = []
    overages = []
    for item in matches:
        if item["quantity"] > limit:
            messages.append(
                f"{item['display_name']} count {item['quantity']} exceeds configured limit {limit}."
            )
            overages.append(
                {
                    "material_key": item["material_key"],
                    "display_name": item["display_name"],
                    "quantity": str(item["quantity"]),
                    "limit_quantity": str(limit),
                }
            )
    if overages:
        return ComplianceCheckResult(
            pack_key=pack["pack_key"],
            rule_key=rule["rule_key"],
            severity=rule["severity"],
            result=_result_for_severity(rule["severity"]),
            message=f"{rule['display_name']}: " + " ".join(messages),
            details={"overages": overages, "message_note": config.get("message_note", "")},
        )
    return ComplianceCheckResult(
        pack_key=pack["pack_key"],
        rule_key=rule["rule_key"],
        severity=rule["severity"],
        result="passed",
        message=f"{rule['display_name']} checked.",
        details={"limit_quantity": str(limit)},
    )


def _evaluate_audit_requirement(
    pack: sqlite3.Row,
    rule: sqlite3.Row,
    payload: TransactionInput,
    draft_items: list[dict[str, Any]],
) -> ComplianceCheckResult | None:
    if not any(item["crv_eligible"] for item in draft_items):
        return None
    missing = []
    if payload.operator_id is None:
        missing.append("operator snapshot")
    if missing:
        return ComplianceCheckResult(
            pack_key=pack["pack_key"],
            rule_key=rule["rule_key"],
            severity="block",
            result="blocked",
            message=f"{rule['display_name']}: missing {', '.join(missing)}.",
            details={"missing": missing},
        )
    return ComplianceCheckResult(
        pack_key=pack["pack_key"],
        rule_key=rule["rule_key"],
        severity=rule["severity"],
        result="passed",
        message=f"{rule['display_name']} checked.",
        details={"requires_receipt_snapshot": True},
    )


def _evaluate_info_warning(
    pack: sqlite3.Row,
    rule: sqlite3.Row,
    draft_items: list[dict[str, Any]],
) -> ComplianceCheckResult | None:
    if not any(item["crv_eligible"] for item in draft_items):
        return None
    config = _config(rule)
    message = str(config.get("message", "")).strip()
    if not message:
        return None
    return ComplianceCheckResult(
        pack_key=pack["pack_key"],
        rule_key=rule["rule_key"],
        severity=rule["severity"],
        result="passed" if rule["severity"] == "info" else "warning",
        message=message,
        details={},
    )


def _existing_daily_quantity(
    conn: sqlite3.Connection,
    report_date: str,
    *,
    report_grouping: str,
    unit_type: str,
) -> Decimal:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(CAST(li.quantity AS NUMERIC)), 0) AS quantity_total
        FROM transactions t
        JOIN transaction_line_items li ON li.transaction_id = t.id
        WHERE date(t.created_at) = ?
          AND t.status != 'voided'
          AND li.crv_eligible = 1
          AND li.report_grouping = ?
          AND li.unit_type = ?
        """,
        (report_date, report_grouping, unit_type),
    ).fetchone()
    return Decimal(str(row["quantity_total"] or "0"))


def _config(rule: sqlite3.Row) -> dict[str, Any]:
    return json.loads(rule["config_json"] or "{}")


def _result_for_severity(severity: str) -> str:
    return "blocked" if severity == "block" else "warning"
