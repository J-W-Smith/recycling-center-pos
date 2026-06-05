# Data Model

## `material_types`

Configurable admin-defined material/input types.

- `key`
- `display_name`
- `category`
- `crv_eligible`
- `unit_type`: `weight`, `count`, or `manual`
- `default_rate_cents_per_unit`
- `report_grouping`
- `active`
- `sort_order`
- `notes`

## `rates`

Effective-dated rate records.

- `material_type_id`
- `rate_kind`
- `rate_cents_per_unit`
- `effective_from`
- `effective_to`
- `notes`
- `active`

## `transactions`

Audit-friendly transaction header.

- `id`
- `created_at`
- `operator_id`
- `operator_initials`
- `operator_display_name_snapshot`
- `operator_initials_snapshot`
- `payout_method`
- `notes`
- `status`: `active`, `voided`, or `corrected`
- `voided_at`
- `void_reason`
- `correction_of_transaction_id`
- `total_cents`
- `receipt_snapshot_text`

## `transaction_line_items`

Stored line-level payout values. These are not recalculated when rates change.

- `transaction_id`
- `material_type_id`
- `description`
- `quantity`
- `unit_type`
- `rate_cents_per_unit`
- `subtotal_cents`
- `crv_eligible`
- `report_grouping`

## `receipt_records`

Immutable receipt/internal copy snapshots.

- `transaction_id`
- `snapshot_text`
- `created_at`

## Optional Placeholders

- `daily_report_runs`
- `users`

## `operators`

Lightweight local identity records.

- `display_name`
- `initials`
- `role`: `operator`, `manager`, or `admin`
- `active`
- `notes`
- `created_at`
- `updated_at`

Operators do not have passwords in this MVP. The manager PIN still controls Admin Settings access. Transactions store operator snapshots so renaming or deactivating an operator later does not rewrite old receipts or reports.

## `app_settings`

Local app-level settings.

- `key`
- `value`
- `created_at`
- `updated_at`

The manager PIN is stored here as a salted PBKDF2-SHA256 hash. The plain PIN is not stored.

## `audit_log`

Append-only admin/config change history.

- `timestamp`
- `operator`
- `action_type`
- `entity_type`: `material_type`, `rate`, or `settings`
- `entity_id`
- `before_value`
- `after_value`
- `notes`

Logged actions include operator creation/edit/deactivation/reactivation, material creation/edit/deactivation/reactivation, rate creation, rate replacement/end-dating, manager PIN creation/change, audit log export, database backup creation, and database restore attempted/completed/failed events.

Backup files are SQLite database copies. They contain transactions, receipt snapshots, material/rate settings, audit log entries, and app settings.

## Data Safety Rules

- Do not delete transactions by default.
- Void/correct by adding status and reason metadata.
- Store currency as integer cents.
- Store weights and quantities as Decimal-compatible text.
- Store receipt snapshots at transaction time.
- Store operator display name and initials snapshots at transaction time.
- Keep inactive materials and old rates for historical reporting.
- Keep inactive operators for historical reporting.
- Use effective dates so price changes do not require code changes.
- Prevent overlapping active rate periods for the same material.
- Keep admin audit entries append-only in the UI.
- Do not store manager PINs in plain text.
- Validate expected tables before restore.
- Create a pre-restore backup before replacing local database contents.
