# GitHub Pages Static Demo

This folder powers the GitHub Pages static demo for Recycling Center POS.

The files here are not the real desktop application. They are a public-facing, sample-data-only walkthrough built with static HTML, CSS, and JavaScript so a partner or client can preview the intended workflow without installing anything.

The real MVP application is still the Python/Tkinter/SQLite desktop app in the repository root.

The demo includes a sample Compliance Packs section showing fake California CRV rule-pack behavior, warning examples, and receipt/report disclosure examples. It does not run real validation or persist settings.

## GitHub Pages Setup

1. Open the repository on GitHub.
2. Go to `Settings`.
3. Open `Pages`.
4. Set `Source` to `Deploy from a branch`.
5. Set `Branch` to `main`.
6. Set `Folder` to `/docs`.
7. Save the settings.

## Demo URL

https://j-w-smith.github.io/recycling-center-pos/

## Safety Notes

- Static demo only — not connected to a real database.
- Uses fake/sample data only.
- Does not store transactions, receipts, PINs, or settings.
- Compliance Pack examples are sample-only and do not certify any workflow.
- MVP prototype. Not compliance-certified. California CRV rules require final business/legal review before production use.
