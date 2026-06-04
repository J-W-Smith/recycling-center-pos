# Project Brief

## Purpose

Build a lightweight, local-first POS and payout tracking system for a California recycling center. The system should support both CRV redemption and non-CRV scrap purchase workflows.

## Operating Context

- Target workstation: older Intel PC running Windows 11.
- Preferred UI: simple desktop GUI with a retro Win95/Windows XP style.
- Storage: local SQLite.
- Network: optional only; core workflows must work offline.
- Users: counter operators and admins at a recycling center.

## Primary Workflows

1. Create a transaction.
2. Add material line items by weight, count, material type, or custom/manual input.
3. Calculate a customer-facing payout total.
4. Save an audit-friendly transaction record.
5. Print or store customer/internal receipt copies.
6. Generate daily reports and exports.
7. Void or correct transactions without destructive deletion.

## Planning Principles

- Keep prices and CRV rules configurable.
- Store receipt snapshots at the time of transaction.
- Preserve transaction history.
- Separate CRV and non-CRV scrap.
- Keep calculations explainable.
- Avoid heavy dependencies until the full requirements are confirmed.

