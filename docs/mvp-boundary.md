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
- Audit Log CSV export using current Audit Log filters.
- Local SQLite database backup control.
- Cautious local SQLite restore with validation, warning, PIN confirmation, and pre-restore backup.
- First active operator setup prompt.
- Active operator selector on the transaction screen.
- Operator management tab in Admin Settings.
- Operator snapshots on transactions and receipts.
- Daily report operator summary.
- Centralized role/permission helpers for Admin Settings actions.
- Admin Settings access denied for plain operators.
- Last active manager/admin deactivation/demotion safeguards.
- Material add/edit plus activate/deactivate behavior.
- Rate add/update metadata behavior with effective dates and overlap detection.
- Text receipt snapshot display.
- Daily report generation.
- Daily CSV export.
- Tests for pricing, admin configuration, receipt snapshots, transaction totals, daily reports, void handling, and cents/Decimal behavior.
- Tests for manager PIN hashing/validation/change, audit log entries, before/after snapshots, and existing-database migrations.
- Tests for audit CSV export, database backup copies, restore rejection, pre-restore backup creation, and valid restore replacement.
- Tests for operator creation, migration, inactive filtering, transaction requirements, receipt snapshots, report summaries, admin audit attribution, and historical preservation.
- Tests for operator/manager/admin permissions, admin denial audit entries, backup/restore/audit-export permissions, and last manager/admin safeguards.

## Deferred

- Final California compliance logic.
- Certified scale integration.
- Thermal printer support.
- Cash drawer support.
- Employee login/permission model.
- Customer profile or ID capture.
- Business-specific payout approval rules.
- Operator passwords or full employee authentication.
- Fine-grained separation between manager and admin roles.
- Audit log signing, retention policy automation, or tamper-evidence.
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
- Do not silently restore a database without warning, PIN confirmation, and a pre-restore backup.
- Do not treat operator selection as secure authentication.
- Do not allow deactivating or demoting the last active manager/admin.
