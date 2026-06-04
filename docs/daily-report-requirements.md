# Daily Report Requirements

## Required Breakdowns

- Material/type.
- CRV vs non-CRV.
- Quantity by weight/count/manual unit.
- Total paid.
- Transaction count.
- Grand totals.
- Voided/corrected transactions section.

## Current MVP Outputs

- In-memory report dictionary.
- CSV export.
- Printable HTML rendering.

## Deferred Outputs

- PDF export.
- Excel export.
- Certified processor report formats.
- Report run retention UI.
- Reconciliation workflow for cash drawer totals.

## Reporting Rules

- Active transactions are included in totals.
- Voided transactions are excluded from grand totals.
- Voided transactions appear in a separate section with reason and line total.
- Historical reports use stored line item values and receipt snapshots, not current rates.

