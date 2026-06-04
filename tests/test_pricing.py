from __future__ import annotations

from decimal import Decimal

from app.pricing import cents_for_quantity, decimal_from_user, format_cents


def test_count_based_crv_calculation() -> None:
    assert cents_for_quantity(Decimal("50"), 5) == 250


def test_weight_based_payout_calculation() -> None:
    assert cents_for_quantity(Decimal("12.5"), 80) == 1000


def test_decimal_cents_rounding_uses_decimal_not_float() -> None:
    assert decimal_from_user("0.333") == Decimal("0.333")
    assert cents_for_quantity(Decimal("0.333"), 100) == 33
    assert cents_for_quantity(Decimal("0.335"), 100) == 34
    assert format_cents(34) == "$0.34"

