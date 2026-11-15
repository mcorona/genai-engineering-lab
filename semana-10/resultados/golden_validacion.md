# Activity 1: validating the integrated gold set

Date: 2026-10-26. Script: `datasets/construir_integrado.py`. Files: `datasets/integrado_{es,en}.jsonl` and `fuentes/`.

## Composition (per language)

| Type | Questions | Reference | Origin |
|---|---|---|---|
| SQL | 15 | Expected SQL, execution accuracy (`order_matters` from the original set) | `semana-07/datasets/nlq_hard_validado.jsonl` |
| Document | 15 | Literal passage | The base questions of `semana-09/datasets/avanzado_*.jsonl` |
| Non-text: PDF with tables | 5 | Exact answer in the source | `fuentes/tarifas_flete.md`, `fuentes/matriz_proveedores.md` |
| Non-text: OCR | 5 | Exact answer in the source | `fuentes/acta_inventario_norte.md`, `fuentes/remision_r4471.md` |
| Non-text: image | 5 | Exact answer in the source | `fuentes/grafica_nivel_servicio.json`, `fuentes/plano_cedis_occidente.json` |
| Mixed | 6 | Expected SQL + literal passage | New SQL + the week 8 corpus |

Total: 51 per language. The EN questions are translations of the ES ones, with the same reference.

## Validations

- **Literal passages:** those of the document and mixed questions appear verbatim in the week 8 corpus.
- **Non-text sources:** each answer is in its source and does **not** appear in the text corpus. If it did, the question could be answered without reading the PDF, the scan or the image. This rule rejected a first version of an image question (the answer "Occidente", which is already in the corpus); it was replaced by the chart's value (95.1%).
- **SQL (42 queries, 15 SQL and 6 mixed per language):** executed against the inventory-copilot database with its read role (`PG_DSN`). All of them run and return at least one row with no nulls.

The results of the mixed questions in the validation:

| Mixed | SQL result |
|---|---|
| `int-mix-01` critical SKUs | 30 |
| `int-mix-02` units sold in September 2026 | 75,001 |
| `int-mix-03` suppliers with more than 20 days of lead time | Shenzhen Components, Ningbo Hardware, Rhein Industrietechnik, … |
| `int-mix-04` stock in Monterrey | 49,382 |
| `int-mix-05` products in the Seguridad (safety) category | 25 |
| `int-mix-06` critical SKUs at risk today (the plan's example) | SKU-0164, SKU-0009, SKU-0189, … |

`int-mix-06` uses the risk definition in `skus_criticos.md`: days of coverage (total stock ÷ average daily sales over the last 30 days) lower than the supplier's lead time.

## Limitations

- The supplier names in the PDF matrix (for example, Shenzhen Industrial Parts) do not match those in the database (for example, Shenzhen Components). They are separate synthetic worlds; no question crosses the matrix with the database, but an assistant could confuse them if one did.
- The SQL results depend on the current synthetic data in the inventory-copilot database. If the data is regenerated, the expected answers can change, although the queries remain valid; the execution-based evaluation compares against the result of the reference SQL on the same database, not against these values.
