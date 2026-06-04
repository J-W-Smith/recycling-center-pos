from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


CENT = Decimal("0.01")


def decimal_from_user(value: str | int | float | Decimal) -> Decimal:
    """Parse user-entered numeric input without carrying binary float artifacts."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value).strip())


def cents_for_quantity(quantity: Decimal, rate_cents_per_unit: int) -> int:
    """Return rounded cents for quantity x rate, using Decimal arithmetic."""
    cents = quantity * Decimal(rate_cents_per_unit)
    return int(cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100}.{cents % 100:02d}"

