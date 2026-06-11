# Compliance Packs

Compliance Packs are configurable rule packs for recycling center workflows. They let one local-first POS support different material lists, warning checks, blocking validations, receipt disclosures, and report sections without hardcoding every rule into transaction code.

Compliance Packs provide compliance support and audit-friendly controls only. They are not legal advice, compliance certification, official filing exports, or a substitute for current regulatory and business-specific review.

## Why Rule Packs

Recycling center requirements vary by jurisdiction, certification status, material stream, equipment, and business policy. A rule-pack model keeps these decisions data-driven:

- enable or disable a pack for the center
- enable or disable a specific rule
- link materials to a pack and hide unneeded materials from new transactions
- store effective dates and JSON config for rules
- keep receipt/report disclosures configurable
- save validation results with completed transactions

This makes future packs possible for other states, scrap-only centers, e-waste, special handling, or customer-specific business rules.

## California CRV Compliance Pack

The first built-in pack is `California CRV Compliance Pack` with pack key `ca_crv`.

Seeded defaults include:

- CRV count refund values: 5 cents, 10 cents, and 25 cents for configured container classes.
- Daily CRV load-limit warning rules: aluminum, plastic, glass, bag-in-box, multilayer pouches, and paperboard cartons.
- Count-payment request warning rules.
- CRV transaction recordkeeping support.
- Receipt disclosure text.
- Daily report disclosure text.

The pack is enabled by default in seed data. Managers/admins can disable the pack, disable individual rules, or deselect linked materials from Admin Settings. Built-in packs/rules should not be hard-deleted through normal operations.

## Warnings vs Blocks

Rules use three severities:

- `info`: informational support, disclosure, or report content.
- `warning`: show the warning before save; manager/admin override can allow the transaction with a reason.
- `block`: prevent saving until the issue is fixed.

The MVP defaults daily load and count-payment checks to warning to avoid false legal certainty. The recordkeeping rule is blocking when the app lacks the operator snapshot required for a CRV transaction.

## Receipt And Report Disclosures

Enabled receipt disclosure rules are rendered into the transaction receipt snapshot at save time. This means later rule text changes do not rewrite old receipts.

Enabled report requirement rules appear in daily reports and FEET closeout snapshots. The report section shows enabled pack name/version, daily load limit actuals, rule result counts, disclosures, and a not-compliance-certified disclaimer.

## Material Selection

`material_pack_links` describe which materials are associated with a pack. Deselecting a linked material hides it from new transaction input when the pack is enabled. Historical transactions keep their stored line-item snapshots.

This is the MVP version of "this center uses these materials / rules." A richer custom material-pack editor is deferred.

## Open Deployment Questions

- Which compliance packs apply to the recycling center?
- Which material categories does the center actually accept?
- Should daily load limits be warning-only, blocking, or manager override?
- Are limits tracked per customer, per transaction, per site/day, or another business definition?
- What exact receipt disclosures are required?
- What reports are retained internally versus submitted externally?
- Who is allowed to override warnings?
- How should rule changes be approved and documented?

Final deployment requires current regulatory review, business certification review, and operating procedure sign-off.
