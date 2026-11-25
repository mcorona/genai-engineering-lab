# Activity 6: question routing

Run of 2026-10-26. Script: `experimentos/ruteo.py`. Model: **claude-haiku-5-5, effort `low`**.

## Design

- **Questions:** the integrated gold set, 51 per language (`datasets/integrado_{es,en}.jsonl`).
- **Correct label**, derived from the type frozen in activity 1: `sql` (15 per language), `documental` (15 text documents and 15 non-text ones from a PDF, a scan or an image) and `mixta` (6).
- **Classifiers:**
  - **Majority:** always `documental`. It is the floor: 30/51 = 0.588.
  - **Haiku 5.5 (`low`):** it receives the description of the two tools (what is in the database and what is in the documents) and returns JSON with the route.

## Results

| Classifier | Language | Accuracy | SQL | Document (text) | Document (non-text) | Mixed |
|---|---|---|---|---|---|---|
| Majority (always document) | ES | 0.588 (30/51) | 0/15 | 15/15 | 15/15 | 0/6 |
| Majority (always document) | EN | 0.588 (30/51) | 0/15 | 15/15 | 15/15 | 0/6 |
| Haiku 5.5 (low) | ES | **0.882** (45/51) | **15/15** | 14/15 | 10/15 | **6/6** |
| Haiku 5.5 (low) | EN | **0.863** (44/51) | **15/15** | 14/15 | 9/15 | **6/6** |

### Haiku's confusion matrix (both languages)

| Expected \ Predicted | sql | document | mixed | invalid format |
|---|---|---|---|---|
| sql | **30** | 0 | 0 | 0 |
| document | 9 | **47** | 4 | 0 |
| mixed | 0 | 0 | **12** | 0 |

**Cost and latency:** $0.00891 for 102 questions ($0.000087 per question). p50 latency of 0.96 s; 65 output tokens on average; no output truncated or with an invalid format.

Detail: `ruteo_detalle_claude-haiku-5-5_low.csv`. The model's responses: `ruteo_claude-haiku-5-5_low.json`.

## Errors

| Question | Type | Language | Predicted | Effect |
|---|---|---|---|---|
| `int-doc-27` "¿Qué puede consultar el copiloto sobre existencias?" ("What can the copilot look up about stock?") | document | ES, EN | sql | harmful |
| `int-pdf-04` the agreed lead time of Shenzhen Industrial Parts | PDF | ES, EN | sql | harmful (see note) |
| `int-pdf-05` the Seguridad (safety) supplier with a C rating | PDF | ES, EN | mixed | benign |
| `int-imagen-11` the lowest service level | image | ES, EN | sql | harmful |
| `int-imagen-12` the service level of the Norte distribution center | image | ES / EN | mixed / sql | benign / harmful |
| `int-imagen-13` the service level of the Centro distribution center | image | ES / EN | sql / mixed | harmful / benign |
| `int-ocr-07` the valued difference in the Norte distribution center's inventory record | scan | EN | sql | harmful |

- **Document → mixed (4 cases): benign.** The mixed route also queries the documents, so the answer stays within reach; it only costs one extra query.
- **Document → SQL (9 cases): harmful.** The assistant would search the database for something that exists only in a document.
- **Note on `int-pdf-04`:** the database does have lead times per supplier, but not for that supplier, which exists only in the PDF matrix. It is the inconsistency of the synthetic world noted in activity 1 (the supplier names in the PDF do not match those in the database). From the wording, routing it to SQL is reasonable.

## Reading

- **SQL and mixed questions are routed perfectly** (30/30 and 12/12). No mixed question is lost to a single source, which is the most expensive error.
- **The errors concentrate on non-text questions** (19/30 correct). Their wording sounds like database data (service levels, lead times, inventory differences), even though the figure exists only in a chart, a table or a record. The classifier does not know which figures exist in the database and which exist only in documents.
- **Harmful errors:** 9 of 102 (8.8%). Total errors: 13 of 102.
- **Negligible cost and latency** compared with a full answer: less than a tenth of a cent and less than a second per question.

## Decision for the assistant (activity 7)

Use the Haiku `low` classifier **with a fallback**: if the SQL route returns an error or zero rows, also query the documents. That turns the document → SQL errors into an extra query instead of a lost answer. The mechanism was not tested here; it is measured in activity 7.

## Limitations

- 51 questions per language, with only 6 mixed ones.
- The description of the document tool mentions the kinds of documents that exist (PDF tables, scanned records, charts and floor plans). It is what a real assistant would know about its sources, but it makes routing the non-text questions easier.
- The inconsistency of supplier names between the database and the PDF matrix affects one question.
- One run, with a single model and effort level.
