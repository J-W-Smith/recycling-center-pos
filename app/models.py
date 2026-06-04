from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


UnitType = Literal["weight", "count", "manual"]
TransactionStatus = Literal["active", "voided", "corrected"]


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
class LineItemInput:
    material_type_id: int
    quantity: Decimal
    description: str = ""
    rate_cents_per_unit: int | None = None


@dataclass(frozen=True)
class TransactionInput:
    line_items: list[LineItemInput]
    operator_initials: str
    payout_method: str = "cash"
    notes: str = ""
