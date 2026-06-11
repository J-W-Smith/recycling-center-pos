from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal

import pytest

from app.compliance import (
    ComplianceValidationError,
    blocking_results,
    validate_transaction,
    warning_results,
)
from app.db import (
    create_transaction,
    fetch_transaction,
    get_compliance_pack_by_key,
    get_material_by_key,
    list_compliance_packs,
    list_compliance_rules,
    list_material_pack_links,
    list_materials,
    set_compliance_pack_enabled,
    set_compliance_rule_enabled,
    set_material_pack_link_enabled,
)
from app.models import LineItemInput, TransactionInput
from app.reports import generate_daily_report, render_daily_report_html
from app.seed_data import seed_materials


def test_compliance_pack_migration_tables_exist(conn: sqlite3.Connection) -> None:
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    assert "compliance_packs" in tables
    assert "compliance_rules" in tables
    assert "material_pack_links" in tables
    assert "transaction_rule_results" in tables


def test_california_crv_pack_seed_is_idempotent(conn: sqlite3.Connection) -> None:
    before_packs = conn.execute("SELECT COUNT(*) AS count FROM compliance_packs").fetchone()[
        "count"
    ]
    before_rules = conn.execute("SELECT COUNT(*) AS count FROM compliance_rules").fetchone()[
        "count"
    ]
    before_links = conn.execute(
        "SELECT COUNT(*) AS count FROM material_pack_links"
    ).fetchone()["count"]

    seed_materials(conn, effective_from="2026-01-01")

    pack = get_compliance_pack_by_key(conn, "ca_crv")
    assert pack.display_name == "California CRV Compliance Pack"
    assert pack.enabled
    assert pack.built_in
    assert conn.execute("SELECT COUNT(*) AS count FROM compliance_packs").fetchone()[
        "count"
    ] == before_packs
    assert conn.execute("SELECT COUNT(*) AS count FROM compliance_rules").fetchone()[
        "count"
    ] == before_rules
    assert conn.execute("SELECT COUNT(*) AS count FROM material_pack_links").fetchone()[
        "count"
    ] == before_links


def test_enable_disable_pack_and_rule_are_audited(conn: sqlite3.Connection) -> None:
    pack = get_compliance_pack_by_key(conn, "ca_crv")
    rule = next(rule for rule in list_compliance_rules(conn, pack.id) if rule.enabled)

    set_compliance_pack_enabled(conn, pack.id, False, operator="Test Operator (TO)")
    set_compliance_rule_enabled(conn, rule.id, False, operator="Test Operator (TO)")

    disabled_pack = get_compliance_pack_by_key(conn, "ca_crv")
    disabled_rule = next(item for item in list_compliance_rules(conn, pack.id) if item.id == rule.id)
    actions = [
        row["action_type"]
        for row in conn.execute(
            "SELECT action_type FROM audit_log WHERE entity_type LIKE 'compliance_%'"
        ).fetchall()
    ]

    assert not disabled_pack.enabled
    assert not disabled_rule.enabled
    assert "compliance_pack_disabled" in actions
    assert "compliance_rule_disabled" in actions


def test_material_link_can_hide_material_from_new_transactions(
    conn: sqlite3.Connection,
) -> None:
    material = get_material_by_key(conn, "aluminum_crv_weight")
    pack = get_compliance_pack_by_key(conn, "ca_crv")
    link = next(
        row
        for row in list_material_pack_links(conn, pack.id)
        if row["material_type_id"] == material.id
    )

    set_material_pack_link_enabled(conn, int(link["id"]), False)
    active_ids = {item.id for item in list_materials(conn, active_only=True)}
    all_ids = {item.id for item in list_materials(conn, active_only=False)}

    assert material.id not in active_ids
    assert material.id in all_ids


def test_daily_load_limit_warning_when_configured_limit_exceeded(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    material = get_material_by_key(conn, "aluminum_crv_weight")
    create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("99"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 9, 0, 0),
    )

    results = validate_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("2"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 10, 0, 0),
    )

    warnings = warning_results(results)
    assert any(result.rule_key == "daily_load_limit_aluminum" for result in warnings)


def test_count_payment_limit_warning(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    material = get_material_by_key(conn, "aluminum_crv_count_small")

    results = validate_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("51"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 10, 0, 0),
    )

    warnings = warning_results(results)
    assert any(result.rule_key == "count_payment_limit_standard_crv" for result in warnings)


def test_blocking_rule_prevents_transaction_save(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    material = get_material_by_key(conn, "aluminum_crv_count_small")
    pack = get_compliance_pack_by_key(conn, "ca_crv")
    rule = next(
        item
        for item in list_compliance_rules(conn, pack.id)
        if item.rule_key == "count_payment_limit_standard_crv"
    )
    conn.execute(
        "UPDATE compliance_rules SET severity = 'block' WHERE id = ?",
        (rule.id,),
    )

    with pytest.raises(ComplianceValidationError) as exc:
        create_transaction(
            conn,
            TransactionInput(
                line_items=[LineItemInput(material.id, Decimal("51"))],
                operator_id=operator_id,
            ),
            created_at=datetime(2026, 6, 4, 10, 0, 0),
        )

    assert blocking_results(exc.value.results)[0].rule_key == rule.rule_key


def test_warning_override_is_audit_logged(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    material = get_material_by_key(conn, "aluminum_crv_count_small")

    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("51"))],
            operator_id=operator_id,
            compliance_override_operator_id=operator_id,
            compliance_warning_override_reason="manager reviewed count request",
        ),
        created_at=datetime(2026, 6, 4, 10, 0, 0),
    )
    audit = conn.execute(
        """
        SELECT * FROM audit_log
        WHERE action_type = 'compliance_warning_overridden'
          AND entity_id = ?
        """,
        (tx_id,),
    ).fetchone()

    assert audit is not None
    assert "manager reviewed count request" in audit["notes"]


def test_receipt_and_daily_report_include_enabled_pack_disclosures(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    material = get_material_by_key(conn, "plastic_crv_count_small")

    tx_id = create_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("12"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 10, 0, 0),
    )
    receipt = fetch_transaction(conn, tx_id)["receipt_snapshot_text"]
    report = generate_daily_report(conn, "2026-06-04")
    html = render_daily_report_html(report)

    assert "California CRV Compliance Pack enabled" in receipt
    assert report["compliance"]["enabled_packs"][0]["pack_key"] == "ca_crv"
    assert "Compliance Pack Support" in html
    assert "California CRV Compliance Pack" in html


def test_disabled_pack_does_not_affect_validation(
    conn: sqlite3.Connection, operator_id: int
) -> None:
    pack = get_compliance_pack_by_key(conn, "ca_crv")
    material = get_material_by_key(conn, "aluminum_crv_count_small")
    set_compliance_pack_enabled(conn, pack.id, False)

    results = validate_transaction(
        conn,
        TransactionInput(
            line_items=[LineItemInput(material.id, Decimal("500"))],
            operator_id=operator_id,
        ),
        created_at=datetime(2026, 6, 4, 10, 0, 0),
    )

    assert results == []


def test_built_in_pack_and_rules_are_not_hard_deleted(conn: sqlite3.Connection) -> None:
    pack = get_compliance_pack_by_key(conn, "ca_crv")
    rules = list_compliance_rules(conn, pack.id)

    set_compliance_pack_enabled(conn, pack.id, False)
    set_compliance_rule_enabled(conn, rules[0].id, False)

    assert get_compliance_pack_by_key(conn, "ca_crv").built_in
    assert len(list_compliance_packs(conn)) >= 1
    assert len(list_compliance_rules(conn, pack.id)) == len(rules)
