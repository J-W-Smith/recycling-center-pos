# Architecture

## Chosen MVP Stack

- Python 3.11+.
- Tkinter desktop UI.
- SQLite local database.
- Plain text and HTML receipt/report rendering.
- CSV export.
- pytest for tests.
- Ruff available as a simple lint tool.

## Module Layout

- `app/main.py`: app entry point.
- `app/gui.py`: Tkinter MVP interface.
- `app/db.py`: SQLite connection, schema, transaction persistence, safe voids.
- `app/models.py`: lightweight dataclasses and type aliases.
- `app/pricing.py`: Decimal/cents calculation helpers.
- `app/receipt.py`: receipt snapshot rendering.
- `app/reports.py`: daily report grouping, CSV export, printable HTML.
- `app/seed_data.py`: sample material and rate configuration.

## Data Flow

1. Operator chooses a configured material/input type.
2. Operator enters quantity and optional notes.
3. App looks up the current effective rate.
4. App calculates line subtotals using Decimal arithmetic.
5. App stores transaction and line items.
6. App stores a receipt snapshot text at the same time.
7. Reports read stored line item values, not recalculated current prices.

## Local Deployment Direction

The likely production shape is a packaged Windows desktop app with a local SQLite file and explicit backup/restore controls. A local FastAPI interface remains possible later, but the first implementation favors Tkinter to keep memory, install, and runtime complexity low.

