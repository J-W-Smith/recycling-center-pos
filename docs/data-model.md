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
- `operator_verified`
- `payout_method`
- `notes`
- `status`: `active`, `voided`, or `corrected`
- `voided_at`
- `voided_by_operator_id`
- `voided_by_operator_name_snapshot`
- `voided_by_operator_initials_snapshot`
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

Receipt snapshots contain customer and office copies, operator snapshot text, operator verification status when available, material/rate/subtotal lines, total payout, and FEET audit indicators. Voided receipt display is layered on at read/print time so the original snapshot is not mutated.

## `compliance_packs`

Configurable rule-pack headers.

- `pack_key`: stable unique key such as `ca_crv`
- `display_name`
- `jurisdiction`
- `version`
- `description`
- `source_notes`
- `enabled`
- `built_in`
- `created_at`
- `updated_at`

The built-in California CRV Compliance Pack is seeded here. Built-in packs should be disabled rather than hard-deleted.

## `compliance_rules`

Rules belonging to a compliance pack.

- `pack_id`
- `rule_key`: unique within the pack
- `display_name`
- `rule_type`: `material_enablement`, `payout_value`, `daily_load_limit`, `count_payment_limit`, `receipt_disclosure`, `report_requirement`, `warning`, `blocking_validation`, or `audit_requirement`
- `severity`: `info`, `warning`, or `block`
- `config_json`
- `enabled`
- `effective_start_date`
- `effective_end_date`
- `created_at`
- `updated_at`

Rule configuration stays in JSON so future packs can add state-specific or material-specific settings without schema changes.

## `material_pack_links`

Links materials to compliance packs and captures which pack-linked materials this center uses.

- `pack_id`
- `material_type_id`
- `required`
- `enabled_by_default`
- `enabled`
- `notes`
- `created_at`
- `updated_at`

If an enabled pack has a disabled material link, that material is hidden from new transaction input. Existing transaction history still uses stored line-item snapshots.

## `transaction_rule_results`

Saved compliance validation results for completed transactions.

- `transaction_id`
- `pack_key`
- `rule_key`
- `severity`
- `result`: `passed`, `warning`, `blocked`, or `skipped`
- `message`
- `details_json`
- `created_at`

Warnings that are overridden are also logged in `audit_log` with the override reason and manager/admin operator snapshot.

## `feet_closeout_reports`

Immutable FEET-inspired end-of-day closeout snapshots.

- `report_date`
- `generated_at`
- `business_name`
- `period_start`
- `period_end`
- `generated_by_operator_id`
- `generated_by_operator_name_snapshot`
- `generated_by_operator_initials_snapshot`
- `operator_verified`
- `expected_cash_cents`
- `actual_cash_cents`
- `discrepancy_cents`
- `discrepancy_notes`
- `operator_attestation`
- `manager_approval`
- `report_snapshot_json`

The JSON snapshot stores the rendered closeout totals for audit review. It is not recalculated after the closeout is saved.

## Optional Placeholders

- `daily_report_runs`
- `users`

## `operators`

Lightweight local identity records.

- `display_name`
- `initials`
- `role`: `operator`, `manager`, or `admin`
- `active`
- `pin_hash`
- `pin_updated_at`
- `notes`
- `created_at`
- `updated_at`

Operators do not have full login accounts in this MVP. They may have an optional individual PIN for local verification. The PIN is stored as a salted PBKDF2-SHA256 hash in `pin_hash`; plain PIN values are not stored or shown. `pin_updated_at` records the last PIN set/change time when practical.

The manager PIN still controls Admin Settings access. Transactions store operator snapshots so renaming or deactivating an operator later does not rewrite old receipts or reports. `operator_verified` records whether the selected operator had successfully verified their individual PIN at transaction save time.

The `operator` role can use normal transaction workflows. The `manager` and `admin` roles can access Admin Settings after manager PIN confirmation and can approve transaction voids. Manager and admin are currently equivalent; admin is reserved for future separation. At least one active manager/admin must remain.

## `app_settings`

Local app-level settings.

- `key`
- `value`
- `created_at`
- `updated_at`

The manager PIN is stored here as a salted PBKDF2-SHA256 hash. The plain PIN is not stored.

Operator PIN enforcement settings are also stored here:

- `require_operator_pin_for_transactions`
- `require_operator_pin_for_admin_actions`

Both default to false for compatibility unless a manager/admin enables them.

## `audit_log`

Append-only admin/config change history.

- `timestamp`
- `operator`
- `action_type`
- `entity_type`: `material_type`, `rate`, `operator`, `settings`, `transaction`, `feet_closeout_report`, `compliance_pack`, `compliance_rule`, or `material_pack_link`
- `entity_id`
- `before_value`
- `after_value`
- `notes`

Logged actions include operator creation/edit/deactivation/reactivation, operator PIN set/change/clear, operator PIN verification attempts when recorded by the UI, operator PIN enforcement setting changes, transaction void attempted/completed/failed events, compliance pack/rule/material-link toggles, compliance warning overrides, material creation/edit/deactivation/reactivation, rate creation, rate replacement/end-dating, manager PIN creation/change, audit log export, database backup creation, and database restore attempted/completed/failed events.

FEET closeout completion is logged with the report date, total paid, void count, and selected operator label. The full report snapshot lives in `feet_closeout_reports`.

Operator audit snapshots intentionally expose only `pin_set` and `pin_updated_at`, not `pin_hash`.

Backup files are SQLite database copies. They contain transactions, receipt snapshots, material/rate settings, audit log entries, and app settings.

## Data Safety Rules

- Do not delete transactions by default.
- Void/correct by adding status and reason metadata.
- Require manager/admin approval, manager PIN confirmation, and a reason before voiding.
- Keep original receipt snapshots unchanged when transactions are voided.
- Keep original closeout snapshots unchanged after report generation.
- Verify FEET closeout line totals against stored transaction totals for the report date.
- Store currency as integer cents.
- Store weights and quantities as Decimal-compatible text.
- Store receipt snapshots at transaction time.
- Store operator display name and initials snapshots at transaction time.
- Store operator PIN verification status at transaction time when available.
- Store void approver display name and initials snapshots at void time.
- Store closeout operator display name and initials snapshots at closeout time.
- Keep inactive materials and old rates for historical reporting.
- Keep inactive operators for historical reporting.
- Prevent deactivating or demoting the last active manager/admin.
- Use centralized permission helpers for admin actions.
- Use effective dates so price changes do not require code changes.
- Prevent overlapping active rate periods for the same material.
- Keep admin audit entries append-only in the UI.
- Do not store manager PINs in plain text.
- Do not store operator PINs in plain text.
- Do not write PIN values or PIN hashes to audit entries.
- Validate expected tables before restore.
- Create a pre-restore backup before replacing local database contents.
- Treat compliance packs as configurable support, not certification.
- Store compliance rule results separately from transactions.
- Preserve receipt/report disclosure text used at the time of transaction or closeout.
- Disable built-in compliance packs/rules instead of hard-deleting them.
