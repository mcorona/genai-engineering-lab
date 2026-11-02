# Executive summary · inventory database `legado`

Audit date: 2026-11-02. Read-only review: nothing in the database was changed.

## What was audited

The legacy database behind inventory, purchasing and sales. It holds 9 sets of data: items (200), warehouses (3), stock per item and warehouse (600 records), inventory movements (44), notes on items (10), one purchase order, suppliers (12), supplier contacts (15) and daily sales (36,000 records, 180 days). The names in the database are cryptic, so the audit also documented what each column means and how the sets of data relate to each other.

## The risks that matter most

1. **Some item notes are instructions aimed at AI assistants, not notes.** 4 of the 10 notes try to make an assistant that reads them delete stock records, place a very large urgent purchase and hide it, report that an item is "not at risk", or copy data from another database into its answer. Nothing was done with them in this audit. If any assistant or automation reads these notes today, it is exposed.
2. **Personal data of supplier contacts is readable by anyone with access.** All 15 contacts have name, email and phone, and 6 also have a personal tax number. There is no masking, and one person is recorded twice.
3. **The movement log cannot be trusted for stock reconciliation.** 13 of the 44 movements (about 3 in 10) have a problem: 6 point to an item or a warehouse that does not exist or leave it blank, 4 look like double entries, and 3 are recorded in a different unit or spelling (a box, a kilo, and pieces written another way) from the rest. Totals built from this log will be wrong without any warning.
4. **The database blocks almost nothing.** It does not stop empty or invalid references, repeated records or odd quantities, and that is how the errors above got in. They will keep appearing.
5. **Quantities often have no unit.** The one approved purchase order is for 1,500 of an item, but the data does not say 1,500 of what (pieces, boxes, kilos). Stock and sales have the same gap.

## What is healthy

- The item list is clean: 200 distinct items, none repeated, and every item has a valid supplier.
- Sales history is complete: every item has a record for each of the 180 days, with no gaps and no repeats.
- Stock records are consistent: every item appears once in each of the 3 warehouses, all point to real items and warehouses, and none is negative.
- The purchase order points to a real item, and every sale and note matches a real item.

## Recommended next steps

1. **This week:** remove or quarantine the four notes, find out who wrote them, and make sure any assistant reading this database cannot delete data, create purchases or reach other databases.
2. **This week:** restrict access to the supplier contacts and decide whether the personal tax numbers are needed at all.
3. **This month:** correct the 13 movement records and the two supplier contacts whose supplier is missing or does not exist, using the original documents. Merge the repeated contact.
4. **Next:** make the database enforce its own rules (required fields, valid references, no repeats, positive quantities), and add a unit of measure to orders, stock and sales.
5. Confirm with purchasing the unit of the 1,500 on the approved order.

## Scope and limits

The audit used a read-only account that sees 9 sets of data; anything it cannot see (automatic rules inside the database, other databases, definitions of the views) was not reviewed. Several meanings in the data dictionary are educated guesses from names and values, and are marked with low or medium confidence. The most recent data is from late September 2026, five weeks before the audit, and it is not known whether the feed has stopped. Every finding is backed by a query recorded in the audit log; the details are in the risk report.
