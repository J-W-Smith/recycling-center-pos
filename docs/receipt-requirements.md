# Receipt Requirements

## Current Receipt Fields

- Business name placeholder.
- Date/time.
- Transaction ID.
- Operator initials/user.
- Payout method placeholder.
- Material line items.
- CRV vs non-CRV marker.
- Weight/count/manual quantity.
- Rate.
- Subtotal per line.
- Total paid.
- Transaction notes.
- Compliance notes/disclaimer area.

## Copy Strategy

The design should support printing two copies:

- Customer receipt.
- Internal record copy.

The MVP renders a single snapshot with the label `CUSTOMER RECEIPT / INTERNAL COPY`. Production should add print settings or duplicate output templates based on printer behavior.

## Thermal Printer Extension Point

Future work should add:

- Printer model detection or configuration.
- Receipt width settings.
- Cut command support where applicable.
- Cash drawer kick support where applicable.
- Retry/error handling and reprint audit trail.

