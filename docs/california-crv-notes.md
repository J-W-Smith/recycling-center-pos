# California CRV Notes

These notes are for planning only. Final compliance must be reviewed against current CalRecycle rules, certified recycling center obligations, processor requirements, recordkeeping rules, and the recycling company's certification details.

Primary public references checked during scaffold creation:

- CalRecycle Beverage Container Recycling: https://calrecycle.ca.gov/bevcontainer/
- CalRecycle Wine and Distilled Spirits: https://calrecycle.ca.gov/bevcontainer/wine-spirits/
- CalRecycle consumer redemption basics: https://calrecycle.ca.gov/bevcontainer/consumers/

## Initial CRV Assumptions To Represent In Config

- Containers less than 24 ounces: `$0.05`.
- Containers 24 ounces or larger: `$0.10`.
- Eligible wine/liquor boxes, bladders, or pouches: `$0.25`.
- Customers may request per-container payment for up to 50 CRV containers of each material type per transaction.
- Current CalRecycle public guidance also distinguishes a 25-container per-transaction count limit for wine/distilled-spirit bag-in-box, multilayer pouch, and paperboard carton formats. Model this separately during compliance design.
- Daily load limits requested for this planning scaffold:
  - 100 lb aluminum.
  - 100 lb plastic.
  - 1,000 lb glass.
- Current CalRecycle public guidance also lists separate daily load limits for some wine/distilled-spirit box, pouch, and carton formats. Model these separately during compliance design.
- CRV and non-CRV scrap must be tracked separately.
- Recycling centers must keep detailed transaction records.

## Configurable Rule Strategy

The application should treat CRV compliance rules as data, not hardcoded code paths:

- Refund value by container class.
- Per-container count limits by material/container class.
- Daily load limits by material/container class.
- Effective dates.
- Required receipt fields.
- Required internal record fields.
- Exceptions and operator warnings.

The current MVP seeds CRV values as rates. It does not yet enforce count limits, daily load limits, customer identity requirements, certification rules, or processor reporting rules.

## Compliance Unknowns / TODOs

- Confirm current CalRecycle per-pound rates for aluminum, plastic, glass, and expanded wine/liquor container types.
- Confirm whether the business is certified and which reports it must retain or submit.
- Confirm any customer ID capture thresholds or fraud-prevention workflows.
- Confirm whether imported/out-of-state container screening must be represented in the workflow.
- Confirm exact transaction record retention requirements.
- Confirm operator certification or training record requirements.
- Confirm signage and receipt wording requirements.
- Confirm how voids/corrections should appear in retained records and reports.
- Confirm whether daily load limits must be enforced per customer, per transaction, per site, or by another operational definition.
- Confirm whether separate processor reports are required beyond internal daily reports.

## Recordkeeping Considerations

Each transaction should retain:

- Date/time.
- Transaction ID.
- Operator/user.
- Material line items.
- CRV vs non-CRV classification.
- Weight/count/manual quantity.
- Rate used.
- Subtotal per line.
- Total paid.
- Payout method.
- Receipt snapshot.
- Notes.
- Void/correction reason, timestamp, and related transaction ID when applicable.

## Receipt And Report Considerations

Receipts and internal copies should include compliance notes/disclaimers while the system is pre-production. Daily reports should separate CRV from non-CRV, summarize by material/type, include grand totals, and list voided/corrected transactions separately.
