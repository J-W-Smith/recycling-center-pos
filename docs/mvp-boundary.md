# MVP Boundary

## Included Now

- Python 3.11+ app structure.
- SQLite schema for materials, rates, transactions, line items, receipt snapshots, daily report runs, FEET closeout snapshots, compliance packs/rules, transaction rule results, and operator placeholders.
- Seed data for common CRV and non-CRV material/input types.
- Tkinter screen for adding line items and saving a transaction.
- Tkinter Admin Settings window for material and rate configuration.
- Tkinter Admin Settings Compliance Packs tab for viewing/toggling packs, rules, and pack-linked material selection.
- Manager PIN prompt before opening Admin Settings.
- Local salted-hash manager PIN storage and PIN change screen.
- Read-only Audit Log tab for admin/config changes.
- Audit Log CSV export using current Audit Log filters.
- Local SQLite database backup control.
- Cautious local SQLite restore with validation, warning, PIN confirmation, and pre-restore backup.
- First active operator setup prompt.
- Active operator selector on the transaction screen.
- Optional operator PIN setup on first-operator creation.
- Main-screen operator PIN verification status and verify button.
- Operator management tab in Admin Settings.
- Operator PIN set/reset/clear controls in Admin Settings.
- Admin settings for optional operator PIN enforcement on transactions and admin actions.
- Operator snapshots on transactions and receipts.
- Operator PIN verification snapshot on transactions.
- Transaction History window for reviewing stored transactions and receipt snapshots.
- Transaction History receipt print/export actions.
- Controlled manager/admin transaction void workflow with manager PIN approval.
- Voided receipt display marker without rewriting the original receipt snapshot.
- Customer and office receipt copy snapshots with operator verification and FEET audit indicators.
- Receipt PDF export.
- Windows OS print-verb receipt handoff when a connected/default printer is available.
- Daily report operator summary.
- Daily report void count, voided amount, and separate voided transaction section.
- Daily report compliance-pack section with enabled packs, configured daily load limits, actual quantities, disclosures, and rule result counts.
- FEET-inspired end-of-day closeout report with business/date/period header.
- FEET closeout CRV/non-CRV totals, material breakdown, operator totals, void totals, discrepancy notes, attestation, approval lines, CSV export, PDF export, audit entry, and saved JSON snapshot.
- FEET closeout snapshots include enabled compliance-pack support sections when packs are active.
- California CRV Compliance Pack seed data with configurable refund-value, daily-load, count-payment, recordkeeping, receipt disclosure, and report disclosure rules.
- Transaction validation layer that returns passed/warning/blocked compliance rule results.
- Warning override audit entries for manager/admin compliance warning overrides.
- Material pack links that can hide linked materials from new transactions without rewriting history.
- Centralized role/permission helpers for Admin Settings actions.
- Admin Settings access denied for plain operators.
- Last active manager/admin deactivation/demotion safeguards.
- Material add/edit plus activate/deactivate behavior.
- Rate add/update metadata behavior with effective dates and overlap detection.
- Text receipt snapshot display.
- Daily report generation.
- Daily CSV export.
- FEET closeout CSV/PDF export.
- Tests for pricing, admin configuration, receipt snapshots, transaction totals, daily reports, void handling, and cents/Decimal behavior.
- Tests for manager PIN hashing/validation/change, audit log entries, before/after snapshots, and existing-database migrations.
- Tests for audit CSV export, database backup copies, restore rejection, pre-restore backup creation, and valid restore replacement.
- Tests for operator creation, migration, inactive filtering, transaction requirements, receipt snapshots, report summaries, admin audit attribution, and historical preservation.
- Tests for operator/manager/admin permissions, admin denial audit entries, backup/restore/audit-export permissions, and last manager/admin safeguards.
- Tests for optional operator PIN hashing, validation, reset/clear audit logs, enforcement settings, transaction enforcement, and migrations.
- Tests for controlled transaction void permissions, reason requirements, audit entries, report totals, receipt display, and migrations.
- Tests for compliance-pack tables, California CRV seed idempotency, pack/rule toggles, material-link selection, daily-load and count-payment warnings, block behavior, warning override audit logging, receipt/report disclosures, disabled-pack behavior, and public demo safety.

## Deferred

- Final California compliance certification/legal review.
- Official filing/export formats for CalRecycle or processors.
- Customer-specific daily limit enforcement beyond the configured site-day warning support.
- Full custom compliance-pack authoring UI.
- Advanced rule editor for arbitrary JSON configs.
- Certified scale integration.
- Dedicated printer-driver integration beyond OS-level print handoff.
- Cash drawer support.
- Full employee login/session model.
- Customer profile or ID capture.
- Business-specific payout approval rules.
- Full linked correction/adjustment transaction workflow.
- Operator passwords or full employee authentication beyond optional local PIN verification.
- Fine-grained separation between manager and admin roles.
- Audit log signing, retention policy automation, or tamper-evidence.
- Installer packaging.
- Multi-workstation or multi-location syncing.
- Cloud backups.

## Non-Goals For This Scaffold

- Do not build a full ERP.
- Do not hardcode production rates into business logic.
- Do not assume the seed CRV settings are production-correct.
- Do not present Compliance Packs as legal advice, certification, or official reporting.
- Do not delete or rewrite transaction records as the normal correction path.
- Do not void transactions without manager/admin role, manager PIN approval, and a reason.
- Do not run FEET closeout without manager/admin role and manager PIN approval.
- Do not hard-delete materials or rates as the default admin action.
- Do not present local PIN protection as full security or compliance certification.
- Do not present FEET closeout output as compliance-certified processor reporting.
- Do not silently restore a database without warning, PIN confirmation, and a pre-restore backup.
- Do not treat operator selection as secure authentication.
- Do not treat optional operator PIN verification as enterprise authentication.
- Do not allow deactivating or demoting the last active manager/admin.
- Do not hard-delete built-in compliance packs or rules as the normal admin path.
