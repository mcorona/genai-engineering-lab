# Manual review of references: English glosses

> Companion to [`revision_referencias.md`](revision_referencias.md). That file keeps the questions, gold passages and reference answers verbatim, as they appear in the frozen eval set (`datasets/eval_rag_es.jsonl`, `eval_rag_en.jsonl`), so many cells are in Spanish. This file gives an English gloss of each Spanish cell, by row number. The glosses are translations for the reader; the eval uses only the Spanish originals. Every figure in a gloss is the same as in its original cell (checked by `docs/tests/test_review_glosses.py`). Names of places, suppliers and people stay as they are; `CEDIS` is a distribution center (see the [glossary](../../docs/glossary.md)).

| # | Id | Question | Passage or exact answer | Reference |
|---|---|---|---|---|
| 1 | int-ocr-08 | Who was responsible for the physical inventory count at CEDIS Norte? | Laura Méndez | Laura Méndez, warehouse manager, was responsible for the physical inventory count at CEDIS Norte. |
| 2 | int-ocr-10 | How many pieces were shipped on delivery note R-4471? | 120 pieces | 120 pieces |
| 3 | rec-29 | What should I do if the copilot gives a wrong answer? | Report wrong answers to the data team, with the exact question and the date. | You should report it to the data team, stating the exact question and the date. |
| 4 | rec-33 | How long is surveillance video kept? | Surveillance videos are kept for **45 calendar days**. | Surveillance videos are kept for **45 calendar days**. |
| 5 | int-pdf-05 | Which supplier in the Security category has a C rating? | Seguridad Andina | Seguridad Andina is the supplier in the Security category with a C rating. |
| 6 | rec-38 | What is the target service level? | The target service level is **97%** of complete orders. | The target service level is **97%** of complete orders. |
| 7 | rec-13 | Against which stock is the reorder point evaluated? | it is evaluated against **total stock**, that is, the sum of the stock on hand at the three distribution centers. | The reorder point is evaluated against total stock, that is, the sum of the stock on hand at the three distribution centers. |
| 8 | rec-12 | How often is the Packaging category reviewed? | the Packaging category is reviewed **weekly** (on Mondays) | The Packaging category is reviewed weekly, on Mondays. |
| 9 | int-pdf-02 | What surcharge does express freight carry over the standard rate? | 35% | The express freight surcharge is 35% over the standard rate. |
| 10 | int-imagen-12 | What service level did CEDIS Norte have in September 2026? | 98.6% | CEDIS Norte had a service level of 98.6% in September 2026. |
| 12 | rec-24 | (in English) | Minimum quantity per transfer: **20 units** or one full pallet, whichever is smaller. | (in English) |
| 13 | rec-07 | (in English) | From $50,000 to $250,000 MXN \| Purchasing manager | (in English) |
| 14 | rec-29 | (in English) | Report wrong answers to the data team, with the exact question and the date. | (in English) |
| 15 | rec-20 | (in English) | Difference greater than 2%: a **partial rejection** of the difference is made and the supplier is notified. | (in English) |
| 16 | rec-10 | (in English) | reorder point = average daily demand × supplier lead time (days) × safety factor | (in English) |
| 17 | rec-06 | (in English) | **A:** critical SKUs and the 20% of SKUs with the highest inventory value. **Monthly** count. | (in English) |
| 18 | rec-35 | (in English) | The maximum height of a pallet is **1.20 meters**. | (in English) |
| 20 | rec-45 | (in English) | **Safety stock:** additional stock held to cover variations in demand or delivery. | (in English) |

Row 11 and row 19 are entirely in English, so they have no gloss.
