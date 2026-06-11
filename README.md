# Recycling Center POS

Planning-first scaffold and local MVP prototype for a California recycling center point-of-sale / payout tracking system.

The project is designed around local-first operation on an older Windows 11 Intel workstation. The preferred first UI is a lightweight Tkinter desktop app with a plain, classic Windows feel rather than a heavy web frontend.

## Static Demo

GitHub Pages demo: https://j-w-smith.github.io/recycling-center-pos/

The demo is static HTML/CSS/JavaScript only. It uses fake sample data and is not connected to a real database. The desktop Python/Tkinter/SQLite app remains the actual MVP.

## Current MVP Scope

- SQLite local storage.
- Configurable material/input types and effective-dated rates.
- Admin Settings window for adding/editing materials and rates without code changes.
- Manager PIN protection for Admin Settings.
- Read-only admin audit log for material, rate, and settings changes.
- Audit log CSV export.
- Local SQLite database backup and cautious restore controls.
- Operator records and active operator selection for transactions.
- Operator snapshots on transactions, receipts, reports, and audit entries.
- Lightweight role-based admin permissions using operator roles and the manager PIN gate.
- Optional individual operator PIN verification for stronger local identity tracking.
- CRV and non-CRV line items tracked separately.
- Count, weight, and manual payout line items.
- Transaction save flow with receipt snapshot text stored at transaction time.
- Customer copy and office copy receipt snapshots with FEET audit indicators.
- Receipt PDF export and Windows OS print-verb handoff for connected/default printers.
- Controlled manager/admin void workflow instead of deleting transactions.
- Transaction History window for reviewing receipt snapshots and voiding selected transactions.
- Transaction History receipt print/export actions that preserve void display marks.
- Daily report grouped by material/report group, with voided transactions separated.
- CSV export for daily reports.
- FEET-inspired end-of-day closeout report with CRV/non-CRV totals, material breakdowns, operator totals, void totals, discrepancy notes, attestations, CSV export, PDF export, audit logging, and immutable closeout snapshots.
- Focused pytest coverage for pricing, admin config, receipts, reports, transactions, and Decimal/cents handling.
- Focused tests for manager PIN hashing/validation and admin audit logging.
- Focused tests for audit CSV export and local database backup/restore behavior.
- Focused tests for operator identity, snapshots, reports, and audit attribution.
- Focused tests for optional operator PIN hashing, enforcement, audit entries, and migrations.
- Focused tests for controlled transaction void permissions, audit logging, reports, and receipt display.

## Quickstart

```powershell
git clone https://github.com/J-W-Smith/recycling-center-pos.git
cd recycling-center-pos
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
python -m app.main
```

If Python 3.11 is not installed, use the newest available Python 3 version and verify Tkinter is included.

## Editing Materials And Rates

Open the app and use `Admin Settings`.

The first time Admin Settings is opened, the app prompts for a manager PIN. The PIN is stored locally as a salted PBKDF2-SHA256 hash, not plain text. Later Admin Settings access requires that PIN. The PIN can be changed from the Settings tab after entering the current PIN.

On first app launch, if no active operator exists, the app prompts to create one. The first operator can optionally receive an individual PIN. Operators identify who performed transactions and admin changes. The manager PIN remains the main gate for Admin Settings.

Use the Operators tab in Admin Settings to add/edit operators, set initials, assign a lightweight role (`operator`, `manager`, or `admin`), set/reset/clear an optional operator PIN, and deactivate/reactivate operators. Operators are deactivated instead of deleted so historical transactions and audit records remain understandable.

Role behavior in the current MVP:

- `operator`: can create transactions and use main-screen reporting/receipt tools, but cannot open Admin Settings or perform admin actions.
- `manager`: can open Admin Settings after manager PIN confirmation and can manage materials, rates, operators, audit exports, backups, restores, and manager PIN changes.
- `admin`: currently has the same permissions as `manager`; it is reserved for cleaner future separation.

The app prevents deactivating or demoting the last active manager/admin operator. That protects the business from locking itself out of Admin Settings.

Operator selection is still not the same as a full login. If an operator has a PIN, the main screen can verify that PIN and show `Verified`. If no PIN exists, the screen shows `PIN not set`. In `Admin Settings` > `Settings`, managers/admins can enable:

- Require operator PIN verification for transactions.
- Require operator PIN verification for admin actions.

Both settings default to off for compatibility. Enabling them improves accountability, but it remains local-only identity verification. PINs are stored as salted PBKDF2-SHA256 hashes, never plain text, and PIN values are not written to the audit log.

Materials can be added, edited, deactivated, or reactivated. Deactivated materials are hidden from new transaction input but remain in historical transactions and reports.

Rates are effective-dated. Add a new rate with a start date when the shop price or CRV configuration changes. Use the replacement option to end-date the previous active rate automatically. Old rates are not hard-deleted because old transactions, receipts, and audit review may need to show the rate that was in force at the time.

The app warns when an active rate period overlaps another active period for the same material. New transactions require a current active rate; if none exists, the operator gets a validation error instead of a silent default.

Startup seed data creates missing defaults only. It should not reactivate or overwrite materials that were later changed in Admin Settings.

The Audit Log tab shows newest entries first and records operator, material, rate, and settings changes. It also records manager PIN creation/change events, audit CSV exports, backups, and restore attempts/completions/failures. Audit entries use the selected operator when available and keep before/after JSON snapshots where available.

Operator PIN set/change/clear events and operator PIN enforcement setting changes are audit logged without PIN values or hashes.

Use `Export CSV` in the Audit Log tab to save the currently filtered audit view. The default filename is `audit_log_YYYY-MM-DD_HHMMSS.csv`.

## Transaction Voids And Corrections

Transactions are not deleted or destructively edited after completion. If a completed transaction is wrong, a manager/admin should use `Transaction History`, select the transaction, and choose `Void Selected`.

Voiding requires:

- selected operator with `manager` or `admin` role
- manager PIN confirmation
- operator PIN verification when admin-action operator PIN enforcement is enabled
- a required reason/note

The original transaction and receipt snapshot remain stored. Viewing a voided receipt adds a `VOIDED TRANSACTION` marker for display/printing without rewriting the original receipt snapshot. Daily reports exclude voided transactions from normal paid totals and show void count, voided amount, and voided transaction details separately.

Full non-destructive correction transactions are still deferred. For the current MVP, managers should void the incorrect transaction with a clear reason and enter a new transaction. The Correction Workflow button is a placeholder to keep this limitation visible.

## Receipts And FEET Closeout

Each saved transaction stores an immutable receipt snapshot. The snapshot includes:

- business name placeholder
- customer copy and office copy labels
- transaction ID and date/time
- operator display name and initials snapshot
- operator PIN verification status when available
- material, unit type, quantity, rate, and subtotal lines
- total payout
- FEET audit indicators for verification, void marks, and notes/reasons

Use `Print Receipt` to hand the current receipt text to the Windows print queue when a default/connected receipt printer is available. Use `Save/Export Receipt` to export the current receipt as a PDF. Transaction History also supports printing/exporting selected receipt snapshots. Voided transaction display adds a void marker, void timestamp, reason, and approving operator snapshot without rewriting the original receipt snapshot.

Use `Run FEET End-of-Day Closeout` from the main screen with a manager/admin operator selected. The action requires the `run_feet_closeout` permission, manager PIN approval, and optional operator PIN verification when admin-action PIN enforcement is enabled. The report summarizes total transactions, total paid, CRV paid, non-CRV paid, material breakdowns, operator-wise totals, void count and voided amount, expected vs actual cash, discrepancy notes, operator attestation, and manager approval. The closeout is saved as an immutable JSON snapshot and exported to CSV and PDF under `data/exports`.

FEET in this MVP means: preserve an audit trail, capture who took actions, log void/correction reasons, and provide a final closeout snapshot for review. It is a local accountability framework only, not a compliance certification.

## Backup And Restore

Use `Admin Settings` > `Settings` to create a local SQLite backup. The default filename is `recycling_pos_backup_YYYY-MM-DD_HHMMSS.sqlite3`. Store backups somewhere outside the app working folder when practical, and periodically copy backups off the workstation to removable storage or another controlled location.

Restore is intentionally cautious. The manager chooses a backup file, sees a warning, enters the manager PIN again, and the app creates a pre-restore backup before replacing the current database contents. Restore validates that the selected file appears to be a recycling-center-pos SQLite database by checking expected tables. Restart the app after restore before normal operation.

## Local-First / Offline Design

- The app stores operational data in `data/recycling_pos.sqlite3`.
- Runtime databases, logs, exports, and caches are git-ignored.
- No cloud service is required for the MVP.
- Receipts are snapshotted so later rate changes do not alter old transaction records.
- Operator display name and initials are snapshotted on each transaction.
- Transactions store whether the selected operator was PIN-verified at save time.
- Voids store the approving operator snapshot, timestamp, and reason.
- FEET closeouts store final report JSON snapshots and audit entries.
- Old materials and rates are retained for audit/history instead of hard-deleted.
- Inactive operators are hidden from new transactions but retained for history.
- Admin settings are protected by local PIN access control.
- Backups are local SQLite copies and are not cloud-synced by the app.
- Currency is stored as integer cents.
- Quantities and weights are handled with `Decimal` and stored as text in SQLite.

## Compliance Warning

This repository is not a compliance-certified system. California CRV rules, certified recycling center recordkeeping, processor reporting, customer ID requirements, load limits, signage, payment rules, and business-specific certification obligations must be reviewed against current CalRecycle guidance and legal/accounting advice before production use.

The initial CRV assumptions are planning placeholders only.
The admin screen makes CRV values configurable, but it does not replace compliance review.

The manager PIN is the main local security gate for admin access. Operator role selection controls which actions are available. Optional individual operator PIN verification improves accountability but still does not replace OS account security, backups, disk encryption, production employee authentication, or production audit controls. Restoring an old backup can roll back operational records, so restore should be manager-only and documented in operating procedures.

## Intentionally Not Built Yet

- Employee password authentication or online accounts.
- Full employee login sessions beyond optional local operator PIN verification.
- Scale integration.
- Cash drawer integration.
- Direct printer integration beyond the Windows OS print verb.
- Barcode scanning.
- Customer identity capture.
- Full linked correction/adjustment transaction workflow.
- CalRecycle processor report submission.
- Multi-location sync.
- Production installer or auto-update flow.

## Development Notes

The MVP entry point is `app/main.py`. It initializes SQLite, seeds material/rate examples, and launches the Tkinter UI. Business logic is kept in small modules so requirements can evolve before committing to a larger application framework.
