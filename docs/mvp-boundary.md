# MVP Boundary

## Included Now

- Python 3.11+ app structure.
- SQLite schema for materials, rates, transactions, line items, receipt snapshots, daily report runs, and operator placeholders.
- Seed data for common CRV and non-CRV material/input types.
- Tkinter screen for adding line items and saving a transaction.
- Tkinter Admin Settings window for material and rate configuration.
- Manager PIN prompt before opening Admin Settings.
- Local salted-hash manager PIN storage and PIN change screen.
- Read-only Audit Log tab for admin/config changes.
- Material add/edit plus activate/deactivate behavior.
- Rate add/update metadata behavior with effective dates and overlap detection.
- Text receipt snapshot display.
- Daily report generation.
- Daily CSV export.
- Tests for pricing, admin configuration, receipt snapshots, transaction totals, daily reports, void handling, and cents/Decimal behavior.
- Tests for manager PIN hashing/validation/change, audit log entries, before/after snapshots, and existing-database migrations.

## Deferred

- Final California compliance logic.
- Certified scale integration.
- Thermal printer support.
- Cash drawer support.
- Employee login/permission model.
- Customer profile or ID capture.
- Business-specific payout approval rules.
- Role-protected admin access.
- Enterprise authentication or employee-specific identity management.
- Audit log export, signing, retention policy, or tamper-evidence.
- PDF exports.
- Installer packaging.
- Multi-workstation or multi-location syncing.
- Cloud backups.

## Non-Goals For This Scaffold

- Do not build a full ERP.
- Do not hardcode production rates into business logic.
- Do not assume the seed CRV settings are production-correct.
- Do not delete or rewrite transaction records as the normal correction path.
- Do not hard-delete materials or rates as the default admin action.
- Do not present local PIN protection as full security or compliance certification.
