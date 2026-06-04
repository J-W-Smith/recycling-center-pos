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
- `operator_initials`
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

Logged actions include material creation/edit/deactivation/reactivation, rate creation, rate replacement/end-dating, manager PIN creation, and manager PIN changes.

## Data Safety Rules

- Do not delete transactions by default.
- Void/correct by adding status and reason metadata.
- Store currency as integer cents.
- Store weights and quantities as Decimal-compatible text.
- Store receipt snapshots at transaction time.
- Keep inactive materials and old rates for historical reporting.
- Use effective dates so price changes do not require code changes.
- Prevent overlapping active rate periods for the same material.
- Keep admin audit entries append-only in the UI.
- Do not store manager PINs in plain text.
