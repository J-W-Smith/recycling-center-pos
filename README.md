# Recycling Center POS

Planning-first scaffold and local MVP prototype for a California recycling center point-of-sale / payout tracking system.

The project is designed around local-first operation on an older Windows 11 Intel workstation. The preferred first UI is a lightweight Tkinter desktop app with a plain, classic Windows feel rather than a heavy web frontend.

## Current MVP Scope

- SQLite local storage.
- Configurable material/input types and effective-dated rates.
- CRV and non-CRV line items tracked separately.
- Count, weight, and manual payout line items.
- Transaction save flow with receipt snapshot text stored at transaction time.
- Safe void support in the data layer instead of deleting transactions.
- Printable receipt text and HTML conversion helper.
- Daily report grouped by material/report group, with voided transactions separated.
- CSV export for daily reports.
- Focused pytest coverage for pricing, receipts, reports, transactions, and Decimal/cents handling.

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

## Local-First / Offline Design

- The app stores operational data in `data/recycling_pos.sqlite3`.
- Runtime databases, logs, exports, and caches are git-ignored.
- No cloud service is required for the MVP.
- Receipts are snapshotted so later rate changes do not alter old transaction records.
- Currency is stored as integer cents.
- Quantities and weights are handled with `Decimal` and stored as text in SQLite.

## Compliance Warning

This repository is not a compliance-certified system. California CRV rules, certified recycling center recordkeeping, processor reporting, customer ID requirements, load limits, signage, payment rules, and business-specific certification obligations must be reviewed against current CalRecycle guidance and legal/accounting advice before production use.

The initial CRV assumptions are planning placeholders only.

## Intentionally Not Built Yet

- Employee authentication and permissions.
- Scale integration.
- Cash drawer integration.
- Thermal receipt printer integration.
- Barcode scanning.
- Customer identity capture.
- Backup/restore workflow.
- PDF export.
- CalRecycle processor report submission.
- Multi-location sync.
- Production installer or auto-update flow.

## Development Notes

The MVP entry point is `app/main.py`. It initializes SQLite, seeds material/rate examples, and launches the Tkinter UI. Business logic is kept in small modules so requirements can evolve before committing to a larger application framework.

