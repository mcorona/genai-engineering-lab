# Activity 7: the integrated assistant (NLQ + document RAG) with citations

Script: `experimentos/asistente.py`. Gold set: `datasets/integrado_{es,en}.jsonl` (51 questions per language: 15 SQL, 15 document, 15 non-text and 6 mixed), frozen in activity 1. The metrics were fixed before the run and did not change between runs.

## Design

| Piece | Choice | Origin |
|---|---|---|
| Routing | Haiku 5.5 low, classifies into sql, document or mixed | Activity 6 |
| NLQ tool | Haiku 5.5 low with the legacy DDL + the full dictionary, executed with the `copilot_ro` read-only role (`search_path = legado`, 5 s timeout) | Activity 2 |
| Document tool | pgvector `semana10.chunks` (30 documents, 68 chunks), the tenant and role filter inside the query, top 20 with bge-m3, reranking with Haiku and top 5 | Weeks 8 and 9 |
| Non-text content | PDF tables with pdfplumber, the scanned inventory record and delivery note with Haiku OCR, image descriptions with Haiku | Activities 3, 4 and 5 |
| Fallback | If the route is sql and the query fails, returns 0 rows or the NLQ abstains (`NO_SQL`), the documents are also queried | Activity 6 + this analysis |
| Answer | Haiku 5.5 medium, using only the context, citing `[SQL]` (the executed query and its rows) and `[D1]`..`[D5]` (a document passage or table) | |
| Judge | Sonnet 5.5 low against the reference (the rows of the reference SQL, literal passages or the expected answer) | |

Test user: tenant `alfa`, with roles that give access to every document the gold set needs (`datasets/permisos_semana10.json`).

Configurations compared on the same 102 questions:

- **integrado:** the complete assistant.
- **integrado_sin_abstencion:** the same, but with the activity 6 fallback as it was (no `NO_SQL`). It measures what the abstention contributes.
- **solo_sql:** always the NLQ tool.
- **solo_docs:** always the document tool.

## Metrics

- **Accuracy (judge):** Sonnet low decides whether the answer is correct against the reference.
- **Document citation precision:** cited `[D#]` passages that contain the reference passage, over cited passages. It is a lower bound: a cited passage that is relevant but is not the reference passage counts as having no evidence.
- **Correct SQL citation:** the answer cites `[SQL]` and the result of the executed query matches that of the reference SQL (the same comparison as in week 7). Only for sql and mixed questions.
- **Cost per question** (without the judge, which is reported separately) and **p50 latency**.

## Results (final run)

| Configuration | Type | Accuracy ES | Accuracy EN | Document citation precision ES / EN | Correct SQL citation ES / EN | Cost per question (USD) | p50 latency (s) |
|---|---|---|---|---|---|---|---|
| **integrado** | sql | 1.000 (15/15) | 1.000 (15/15) | - | 14/15 · 15/15 | 0.00057 | 4.6 |
| | document | 0.933 (14/15) | 1.000 (15/15) | 0.682 · 0.636 | - | 0.00077 | 5.0 |
| | non-text | 1.000 (15/15) | 1.000 (15/15) | 0.880 · 0.750 | - | 0.00090 | 5.8 |
| | mixed | 0.833 (5/6) | 0.833 (5/6) | 0.545 · 0.500 | 4/6 · 4/6 | 0.00148 | 8.2 |
| | **TOTAL** | **0.961 (49/51)** | **0.980 (50/51)** | 0.741 · 0.656 | 18/21 · 19/21 | 0.00083 | 5.3 |
| integrado_sin_abstencion | non-text | 0.800 (12/15) | 0.867 (13/15) | 0.895 · 0.792 | - | 0.00092 | 5.8 |
| | TOTAL | 0.902 (46/51) | 0.922 (47/51) | 0.691 · 0.684 | 18/21 · 19/21 | 0.00086 | 5.5 |
| solo_sql | sql | 1.000 (15/15) | 1.000 (15/15) | - | 14/15 · 15/15 | 0.00049 | 3.9 |
| | document, non-text, mixed | 0/36 | 0/36 | - | 0/6 · 0/6 | 0.00028 | 2.5 |
| | TOTAL | 0.294 (15/51) | 0.294 (15/51) | - | 14/21 · 15/21 | 0.00034 | 2.7 |
| solo_docs | sql | 0.000 (0/15) | 0.000 (0/15) | 0.000 · 0.000 | 0/15 · 0/15 | 0.00081 | 4.8 |
| | document | 1.000 (15/15) | 1.000 (15/15) | 0.577 · 0.652 | - | 0.00068 | 3.9 |
| | non-text | 1.000 (15/15) | 1.000 (15/15) | 0.769 · 0.909 | - | 0.00071 | 4.0 |
| | mixed | 0.167 (1/6) | 0.167 (1/6) | 0.429 · 0.412 | 0/6 · 0/6 | 0.00087 | 5.4 |
| | TOTAL | 0.608 (31/51) | 0.608 (31/51) | 0.366 · 0.416 | 0/21 · 0/21 | 0.00075 | 4.4 |

Cost and latency combine ES and EN; the per-language values are in the script's full output and in `asistente_detalle.csv` (one row per question and configuration). Document fallback triggered: integrado 11 of 102 questions; integrado_sin_abstencion 3 of 102.

## Reading

- **The integrated assistant beats each tool on its own:** 0.961 ES and 0.980 EN, vs. 0.294 for solo_sql and 0.608 for solo_docs. Each tool alone solves its own question type and fails on the others. On mixed questions, no single tool gets more than 1/6, while the integrated assistant reaches 5/6.
- **The integrated assistant loses no accuracy on each tool's own type:** on sql it ties with solo_sql (1.000, SQL citation 14/15 and 15/15), and on document and non-text questions it ties with solo_docs (except `int-doc-27` ES).
- **Cost:** $0.00083 per question, 2.4 times solo_sql and 1.1 times solo_docs. It comes from 1 routing call plus 1 or 2 tools plus the answer. p50 latency rises to 5.3 s (vs. 2.7 and 4.4 s); mixed questions are the slowest (8.2 s), because they run both tools in series.
- **The NLQ abstention helps on non-text questions:** they go from 0.800/0.867 to 1.000/1.000. Without it, the service-level questions (a figure that exists only in a chart) are routed to sql, and Haiku approximates the figure from other columns: it invented service levels of 98 %, 99.5 % and 100 % with a `[SQL]` citation (16 % in the pilot), all false, and the fallback did not trigger because there were rows. The NLQ abstained on 9 of the integrated assistant's 102 questions (image, OCR and `int-doc-27`), none of them of type sql.
- **The activity 6 fallback ("error or 0 rows") is not enough:** a query that answers something else returns rows. This confirms the risk of the 9 harmful document-to-sql routing errors in activity 6.

## How the final run was reached

| Run | Change | integrado ES / EN | Cost |
|---|---|---|---|
| Pilot (`--limite 1`, 12 questions × 3 configurations) | Initial design | 0.833 / 0.833; `int-imagen-11` fails (routed to sql, an invented query with rows, no fallback) | $0.081 |
| Run 1 (102 × 4) | The `NO_SQL` abstention in the NLQ and the `integrado_sin_abstencion` configuration | 0.863 / 0.922; mixed 0/6 ES and 2/6 EN | $0.696 |
| Final run | The abstention applies only on the sql route (where there is a fallback) and in solo_sql | 0.961 / 0.980 | $0.048 (only the 16 mixed-route answers, with the judge) |

In run 1, the NLQ abstained on 15 of the 16 mixed-route questions, because the question includes the document part ("who approves…?") and the tool rejected all of it. This was a mistake in the scope of the change, not in the gold set or the metrics. The evidence of that run is in `asistente_cache_corrida1.json` and `asistente_detalle_corrida1.csv`; the pilot's is in `asistente_cache_prueba.json`.

**Total cost of the activity: $0.82** (assistant $0.33 and judge $0.49), with the official prices of Haiku 5.5 ($0.10/$0.50) and Sonnet 5.5 ($2/$10) per MTok, checked on 2026-10-26. The judge costs more than the assistant.

## Cases that fail in the integrated assistant

| Question | What happened | Kind of failure |
|---|---|---|
| `int-mix-06` ES/EN ("which critical SKUs are at risk today and who approves their urgent purchase?") | The NLQ read "at risk" as stock below the reorder point (12 SKUs). The reference defines it by coverage against the supplier's lead time. The part about who approves is correct (the purchasing manager). | A design limit: the tools run in parallel, and the definition in the document does not reach the SQL query. It needs two steps (document → SQL). |
| `int-doc-27` ES ("what can the copilot look up about stock?") | Routed to sql; the NLQ abstains and the fallback brings in the correct document. The answer only says "stock in read-only mode" and omits sales, suppliers and reorder points. | An incomplete answer. In EN, the same question is answered correctly. |
| `int-mix-03` ES/EN (SQL citation) | The judge accepts it, but the query returns suppliers with their critical SKUs (12 rows, 6 columns) and the reference returns only supplier names (5 rows). | A strict metric: the SQL citation requires the same result. |
| `int-sql-014` ES (SQL citation) | Correct for the judge; the query returns the warehouse id and the quantity instead of the name. | A strict metric (same cause). |

**Document citation precision** (0.66 to 0.88 in the integrated assistant) is a lower bound. It counts as having no evidence every cited passage that does not contain the reference passage, even when it is relevant; for example, the reorder policy cited next to the list of critical SKUs. In solo_docs it drops to 0.37/0.42, because on sql questions it cites documents that do not answer them (0 of 85 with evidence).

## Decision

- Default assistant: **integrated, with abstention on the sql route**. It beats each tool in total accuracy, matches each one on its own type and costs $0.00083 per question.
- Pending for a two-step design (out of scope this week): having the mixed route query the documents first and pass the definition to the NLQ (`int-mix-06`).
- The assistant's security (zero writes, 0 leaks and resistance to injected instructions) is measured in activity 8.
