# Summary: review of the legacy database (`legado`)

**Date:** 2 November 2026

## What we reviewed

We reviewed the legacy database that holds inventory, items, suppliers and sales. It has 9 data sets (tables and views) and about 36,000 sales records. We only read the data. We changed nothing.

## The risks that matter most

1. **Supplier contact data is personal and unprotected.** The supplier contact list stores names, emails, phone numbers and personal tax IDs of individual people, with no evidence of a legal basis or a retention limit. Any copy of this list spreads that data. *Action:* confirm the legal basis with the legal or privacy team, then limit who can see these fields.

2. **Stored notes try to instruct AI tools.** Two free-text notes in the database contain instructions aimed at an AI assistant, asking it to read data outside its scope. The audit did not act on them. As more AI tools connect to this database, this becomes a security risk. *Action:* have the database owner review and remove the two notes, and find out who wrote them.

3. **Some stock movements point to items or warehouses that do not exist.** Three inventory movements refer to two item codes and one warehouse that are not in the master lists. Stock totals for those items cannot be trusted. *Action:* the warehouse team confirms what these movements were and corrects them.

4. **Quantities are recorded in different units.** The same quantity field mixes pieces, cases and kilograms, with four spellings of the piece unit. Totals added together are wrong unless someone converts them. *Action:* choose one unit rule per item and standardize the records.

5. **The system accepts incomplete or invalid records.** About 2.5% of sales records (913 of 36,000) show zero units sold. Some stock movements have no item or warehouse, and one approved purchase order has no record of who approved it. *Action:* decide the business rules, then have the system enforce them.

## What is in good shape

- Item codes, warehouse codes and supplier codes are unique, with no missing keys in the main tables.
- Stock values are never negative, and costs and movement quantities are always positive.
- Movement types use only the two agreed values (receipts and issues).
- The sales and stock tables each match the item and warehouse masters, with no broken links.

## Recommended next steps

1. **This week:** review the two stored notes (risk 2) and limit access to supplier contact fields (risk 1).
2. **This month:** correct the orphan movements and the unit spellings (risks 3 and 4) with the warehouse team.
3. **Next quarter:** agree the business rules for zero-unit sales, missing fields and purchase approvals (risk 5), then add them to the database so the system enforces them.
4. **Ongoing:** keep personal data separate from operational data, and document the purpose of each personal field.

## Scope and limits

- The review covered only the `legado` schema, through a read-only account.
- Several small tables have very few records (for example, one purchase order). Results for them show what exists, not overall patterns.
- Some columns have names that do not show their purpose (for example, a numeric code and a date with no clear meaning). The business owner must confirm them before any change.
- The review did not check the content of free-text notes for personal information.
- No personal values are included in this summary or in the technical files.
