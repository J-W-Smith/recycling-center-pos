from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal


UnitType = Literal["weight", "count", "manual"]
TransactionStatus = Literal["active", "voided", "corrected"]
OperatorRole = Literal["operator", "manager", "admin"]


@dataclass(frozen=True)
class MaterialType:
    id: int
    key: str
    display_name: str
    category: str
    crv_eligible: bool
    unit_type: UnitType
    report_grouping: str
    active: bool = True
    sort_order: int = 0
    notes: str = ""


@dataclass(frozen=True)
class Rate:
    id: int
    material_type_id: int
    rate_kind: str
    rate_cents_per_unit: int
    effective_from: str
    effective_to: str | None = None
    notes: str = ""
    active: bool = True


@dataclass(frozen=True)
class Operator:
    id: int
    display_name: str
    initials: str
    role: OperatorRole
    active: bool = True
    pin_set: bool = False
    pin_updated_at: str | None = None
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class LineItemInput:
    material_type_id: int
    quantity: Decimal
    description: str = ""
    rate_cents_per_unit: int | None = None


@dataclass(frozen=True)
class TransactionInput:
    line_items: list[LineItemInput]
    operator_id: int | None = None
    operator_initials: str = ""
    operator_verified: bool = False
    payout_method: str = "cash"
    notes: str = ""
    compliance_warning_override_reason: str = ""
    compliance_override_operator_id: int | None = None


@dataclass(frozen=True)
class CompliancePack:
    id: int
    pack_key: str
    display_name: str
    jurisdiction: str
    version: str
    description: str
    source_notes: str
    enabled: bool
    built_in: bool
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class ComplianceRule:
    id: int
    pack_id: int
    rule_key: str
    display_name: str
    rule_type: str
    severity: str
    config: dict[str, Any]
    enabled: bool
    effective_start_date: str
    effective_end_date: str | None = None
    created_at: str = ""
    updated_at: str = ""
