# MVP Boundary

## Included Now

- Python 3.11+ app structure.
- SQLite schema for materials, rates, transactions, line items, receipt snapshots, daily report runs, and operator placeholders.
- Seed data for common CRV and non-CRV material/input types.
- Tkinter screen for adding line items and saving a transaction.
- Text receipt snapshot display.
- Daily report generation.
- Daily CSV export.
- Tests for pricing, receipt snapshots, transaction totals, daily reports, void handling, and cents/Decimal behavior.

## Deferred

- Final California compliance logic.
- Certified scale integration.
- Thermal printer support.
- Cash drawer support.
- Employee login/permission model.
- Customer profile or ID capture.
- Business-specific payout approval rules.
- PDF exports.
- Installer packaging.
- Multi-workstation or multi-location syncing.
- Cloud backups.

## Non-Goals For This Scaffold

- Do not build a full ERP.
- Do not hardcode production rates into business logic.
- Do not assume the seed CRV settings are production-correct.
- Do not delete or rewrite transaction records as the normal correction path.

