# Recycling Center POS

Planning-first scaffold and local MVP prototype for a California recycling center point-of-sale / payout tracking system.

The project is designed around local-first operation on an older Windows 11 Intel workstation. The preferred first UI is a lightweight Tkinter desktop app with a plain, classic Windows feel rather than a heavy web frontend.

## Current MVP Scope

- SQLite local storage.
- Configurable material/input types and effective-dated rates.
- Admin Settings window for adding/editing materials and rates without code changes.
- Manager PIN protection for Admin Settings.
- Read-only admin audit log for material, rate, and settings changes.
- Audit log CSV export.
- Local SQLite database backup and cautious restore controls.
- CRV and non-CRV line items tracked separately.
- Count, weight, and manual payout line items.
- Transaction save flow with receipt snapshot text stored at transaction time.
- Safe void support in the data layer instead of deleting transactions.
- Printable receipt text and HTML conversion helper.
- Daily report grouped by material/report group, with voided transactions separated.
- CSV export for daily reports.
- Focused pytest coverage for pricing, admin config, receipts, reports, transactions, and Decimal/cents handling.
- Focused tests for manager PIN hashing/validation and admin audit logging.
- Focused tests for audit CSV export and local database backup/restore behavior.

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

Materials can be added, edited, deactivated, or reactivated. Deactivated materials are hidden from new transaction input but remain in historical transactions and reports.

Rates are effective-dated. Add a new rate with a start date when the shop price or CRV configuration changes. Use the replacement option to end-date the previous active rate automatically. Old rates are not hard-deleted because old transactions, receipts, and audit review may need to show the rate that was in force at the time.

The app warns when an active rate period overlaps another active period for the same material. New transactions require a current active rate; if none exists, the operator gets a validation error instead of a silent default.

Startup seed data creates missing defaults only. It should not reactivate or overwrite materials that were later changed in Admin Settings.

The Audit Log tab shows newest entries first and records material creation/edit/deactivation/reactivation, rate creation/replacement/end-date changes, manager PIN creation/change events, audit CSV exports, backups, and restore attempts/completions/failures. Audit entries keep before/after JSON snapshots where available.

Use `Export CSV` in the Audit Log tab to save the currently filtered audit view. The default filename is `audit_log_YYYY-MM-DD_HHMMSS.csv`.

## Backup And Restore

Use `Admin Settings` > `Settings` to create a local SQLite backup. The default filename is `recycling_pos_backup_YYYY-MM-DD_HHMMSS.sqlite3`. Store backups somewhere outside the app working folder when practical, and periodically copy backups off the workstation to removable storage or another controlled location.

Restore is intentionally cautious. The manager chooses a backup file, sees a warning, enters the manager PIN again, and the app creates a pre-restore backup before replacing the current database contents. Restore validates that the selected file appears to be a recycling-center-pos SQLite database by checking expected tables. Restart the app after restore before normal operation.

## Local-First / Offline Design

- The app stores operational data in `data/recycling_pos.sqlite3`.
- Runtime databases, logs, exports, and caches are git-ignored.
- No cloud service is required for the MVP.
- Receipts are snapshotted so later rate changes do not alter old transaction records.
- Old materials and rates are retained for audit/history instead of hard-deleted.
- Admin settings are protected by local PIN access control.
- Backups are local SQLite copies and are not cloud-synced by the app.
- Currency is stored as integer cents.
- Quantities and weights are handled with `Decimal` and stored as text in SQLite.

## Compliance Warning

This repository is not a compliance-certified system. California CRV rules, certified recycling center recordkeeping, processor reporting, customer ID requirements, load limits, signage, payment rules, and business-specific certification obligations must be reviewed against current CalRecycle guidance and legal/accounting advice before production use.

The initial CRV assumptions are planning placeholders only.
The admin screen makes CRV values configurable, but it does not replace compliance review.

The manager PIN is local workstation access control for the MVP. It is not enterprise-grade identity management, does not identify individual employees, and does not replace OS account security, backups, disk encryption, or production audit controls. Restoring an old backup can roll back operational records, so restore should be manager-only and documented in operating procedures.

## Intentionally Not Built Yet

- Employee authentication and permissions.
- Individual admin/operator identity tracking.
- Scale integration.
- Cash drawer integration.
- Thermal receipt printer integration.
- Barcode scanning.
- Customer identity capture.
- PDF export.
- CalRecycle processor report submission.
- Multi-location sync.
- Production installer or auto-update flow.

## Development Notes

The MVP entry point is `app/main.py`. It initializes SQLite, seeds material/rate examples, and launches the Tkinter UI. Business logic is kept in small modules so requirements can evolve before committing to a larger application framework.
