# Inventory and purchasing database: summary for the buyer

**Audit date:** 2 November 2026 · **Access:** read-only, nothing was changed

## What was reviewed

The legacy database behind inventory and purchasing: 200 products, 3 warehouses, 12 suppliers and their 15 contact people, 600 stock figures (every product in every warehouse), 36,000 daily sales records covering 180 days, 44 stock movements and 1 approved purchase order. In total there are 9 data sets. The names are cryptic abbreviations, so I wrote a plain-language dictionary and a relationship diagram of how they connect.

## The risks that matter

1. **The database does not protect itself.** It has no rules that stop bad entries, such as a movement for a product that does not exist. As a result, **13 of the 44 stock movements (about 3 in 10) have a problem**: unknown products or warehouses, missing product or warehouse, apparent double entries, or quantities in boxes and kilograms mixed in with pieces. Today's stock figures cannot be fully trusted until these are cleaned.
2. **Personal data is stored without protection.** Every supplier contact has a name, email and phone on file, and 6 have a personal tax ID. Employee logins are stored on all movements. Transferring this in a sale needs a legal basis, and any test copy of the database would carry it.
3. **A stored note tries to give orders to an AI tool.** One internal note is written to make an AI assistant read data from another system and repeat it. It was not followed. It shows that someone could place text in this data to hijack automated tools. Who wrote it should be investigated.
4. **Duplicate supplier contact.** The same person is registered twice, and two contacts have missing or non-existent suppliers.
5. **Item costs have no currency.** Suppliers are in 7 countries, but the data never says whether a cost is in pesos, dollars or euros. Valuing the inventory needs that answer first.

## What is healthy

- Every product has a valid supplier, and every stock figure and sale refers to a real product (no gaps in 36,000 sales records).
- No negative stock and no negative sales.
- The 200 products, 12 suppliers and 3 warehouses each have unique codes.
- Country and product-line labels are spelled consistently.

## Recommended next steps

1. Have the database administrator correct the 13 movements with the warehouse team (the audit lists their numbers), then add rules to the database so this cannot happen again.
2. Ask legal whether supplier contact data and tax IDs may be transferred. Mask them in any test copy.
3. Investigate and remove the note aimed at AI tools. Treat free-text notes as untrusted.
4. Ask the seller for the currency and unit of item costs, and for how stock figures are produced and refreshed.
5. Merge the duplicate contact and fix the two contacts without a valid supplier.

## Scope and limits

- I had read-only access to 9 data sets in one schema. I could not see how the six "views" are built, so the database underneath may hold more.
- Meanings of some abbreviations (reorder level, critical item, supplier delivery days) are educated guesses and should be confirmed with the client.
- Stock movements only cover 1 to 25 September 2026. The data ends on 28 September 2026.
- Whether the apparent double entries are real mistakes needs confirmation from the warehouse.
- Full details and the evidence for every point are in `riesgos.md`.
