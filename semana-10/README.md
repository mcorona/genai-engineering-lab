# Week 10: structured data and documents (text-to-SQL on a legacy schema, PDF tables, OCR, images, integrated assistant)

> Spanish names (folders, files, JSON keys, flags, stack names, status values) are explained in the [glossary](../docs/glossary.md). The documentation is in English. Spanish data and recorded results stay as they are: the [data guide](../docs/data/README.md) and the README in each data or results folder describe them in English.

Goal: integrate NLQ-Inventory (week 7) and document RAG (weeks 8 and 9) into one assistant, and measure each new piece (legacy schema, PDFs, OCR, images, routing) against a baseline before adding it.
Prices come from the official Anthropic pricing page (`semana-07/prices.json`, checked 2026-10-26): Haiku 5.5 $0.10 / $0.50 and Sonnet 5.5 $2 / $10 per million tokens. Every figure links to a results file in `resultados/`.

## Gold sets (frozen before any experiment)

| Set | Per language | Reference | File |
|---|---|---|---|
| Integrated: SQL | 15 | Expected SQL, execution accuracy (from the week 7 hard set) | `datasets/integrado_{es,en}.jsonl` |
| Integrated: document | 15 | Verbatim passage (week 9 base questions) | same |
| Integrated: non-text | 15 (5 PDF, 5 OCR, 5 image) | Exact answer that exists only in the PDF, scan or image, never in the text corpus | same + `fuentes/` |
| Integrated: mixed | 6 | Expected SQL + verbatim passage | same |
| Legacy text-to-SQL | 43 | Week 7 hard set, compared by execution against the original tables | `semana-07/datasets/nlq_hard_validado.jsonl` |
| Security | 12 write attempts, 4 NLQ leak attempts, 8 injection questions; 18 direct statements | Zero writes, zero leakage, injected instruction not followed | `datasets/seguridad.json` |

Validation of the integrated set: [`golden_validacion.md`](resultados/golden_validacion.md).

## Results

| # | Piece | Main result | Decision | Details |
|---|---|---|---|---|
| 2 | Text-to-SQL on a legacy schema (cryptic views + data dictionary) | Haiku 5.5: no dictionary ES 0.884 / EN 0.953; full dictionary **0.977 / 1.000** at $0.00033 per question; retrieved dictionary 0.767 / 0.721. Sonnet 5.5 is no better and costs about 13x more | Haiku + legacy DDL + full dictionary | [`sql_legado.md`](resultados/sql_legado.md) |
| 3 | PDF tables | Rows intact: pypdf 0/13, pdfplumber 13/13, Haiku 13/13; recall@5 does not separate them | pdfplumber (free, local) | [`pdf_tablas.md`](resultados/pdf_tablas.md) |
| 4 | OCR of scans | Mean CER: Tesseract 0.009, Haiku 0.001, Sonnet 0.000; same recall for all | Tesseract by default; Haiku when figures matter ($0.0007/page) | [`ocr.md`](resultados/ocr.md) |
| 5 | Images (chart, floor plan) | Associated facts: Tesseract 0/7, Haiku description 7/7; recall@5 5/5 with the description | Haiku describes and extracts at indexing time | [`imagenes.md`](resultados/imagenes.md) |
| 6 | Question routing | Haiku 5.5 low: ES 0.882, EN 0.863 (majority floor 0.588); SQL 30/30, mixed 12/12; 9 harmful document → SQL errors | Router with fallback to documents | [`ruteo.md`](resultados/ruteo.md) |
| 7 | Integrated assistant | Judge accuracy **ES 0.961, EN 0.980** vs SQL only 0.294 and documents only 0.608; mixed 5/6 vs at most 1/6 for either tool alone; $0.00083 per question, p50 5.3 s | Integrated, with SQL abstention on the SQL route | [`asistente.md`](resultados/asistente.md) |
| 8 | Assistant security | Hardened NLQ: **0 writes**; leakage **0** by role (56), across tenants (40) and through SQL (32); injected instructions followed **0/48** | Hardened NLQ (`copilot_nlq` + rolled-back `READ ONLY` transaction) | [`seguridad.md`](resultados/seguridad.md) |
| 9 | CI | Workflow `eval-semana-10` on every PR touching `semana-10/**`; thresholds calibrated on the first run | Thresholds 0.85 / 0.90 / 0.90 | [`ci_calibracion.md`](resultados/ci_calibracion.md) |

## The assistant

```
question → router (Haiku 5.5 low) ──sql──────→ NLQ (Haiku low, legacy DDL + dictionary, copilot_nlq, READ ONLY rolled back)
                                   │              └─ error, 0 rows or NO_SQL → also documents
                                   ├─document──→ RAG (pgvector, tenant and role filter inside the query, top 20 → Haiku rerank → top 5)
                                   └─mixed─────→ both
answer (Haiku 5.5 medium), only from context, citing [SQL] (executed query and rows) and [D1]..[D5] (passage or table)
```

Indexed content: week 8 text corpus, PDF tables extracted by pdfplumber, scans transcribed by Haiku, and image descriptions by Haiku (30 documents, 68 chunks).

| Question type (ES / EN) | Integrated | SQL only | Documents only |
|---|---|---|---|
| SQL | 1.000 / 1.000 | 1.000 / 1.000 | 0 / 0 |
| Document | 0.933 / 1.000 | 0 / 0 | 1.000 / 1.000 |
| Non-text (PDF, OCR, image) | 1.000 / 1.000 | 0 / 0 | 1.000 / 1.000 |
| Mixed | 0.833 / 0.833 | 0 / 0 | 0.167 / 0.167 |
| **Total** | **0.961 / 0.980** | 0.294 / 0.294 | 0.608 / 0.608 |

SQL citation correct (cited `[SQL]` and the result matches the reference): 18/21 ES, 19/21 EN. Document citation precision is a lower bound (0.741 / 0.656), because a cited passage that is relevant but is not the reference passage counts as unsupported.

## Security

| Requirement | Result | How it was measured |
|---|---|---|
| Zero SQL writes | **0** with the hardened NLQ, in every phase | Database fingerprint (md5 of every table, relations, privileges, sequences, large objects, role attributes) before and after each phase; 18 direct statements per layer, a chain on one session, 104 natural-language attempts through the assistant |
| Leakage 0 by role and across tenants, also through the assistant | **0** in 128 cases | Unauthorized chunks in the assistant's context (passages or SQL rows) and unauthorized data in the answer |
| Injected instructions in a PDF or an image are not followed | **0/48** followed; correct data 48/48 | 2 PDFs and 2 images with an instruction (table row, 8 pt footnote, visible box, near-invisible text); Sonnet 5.5 low as judge |

**What the security tests found:** the week 7 / activity 7 NLQ connection was never read-only. psycopg ignores `read_only` in autocommit, so `SELECT lo_create(0)` passed the single-SELECT filter and **wrote large objects**. In addition, `copilot_ro` could read the document table without the role filter. The assistant never triggered either (Haiku abstained), but the tool allowed it. The hardened NLQ (role `copilot_nlq` limited to the legacy views, each query inside a `READ ONLY` transaction that always rolls back) closes both, and is what `experimentos/asistente.py` has used since PR #44.

Haiku also acted as a first barrier when indexing images: it detected the injected text and left it out of the description. The answer model was then tested with a literal transcription that does carry the instruction, and still did not follow it.

## CI

`.github/workflows/eval-semana-10.yml` runs on every PR that touches `semana-10/**`. It uses a pgvector service with the week 7 CI database (seed 42) and `text-embedding-3-small`, because bge-m3 runs in LM Studio, not in Actions. It costs about $0.11 per run and takes about 9 minutes.

| Check | First run (ES / EN) | Threshold |
|---|---|---|
| Routing accuracy | 0.882 / 0.882 | 0.85 |
| Execution accuracy on the legacy schema (hardened NLQ) | 0.930 / 0.953 | 0.90 |
| recall@5 of re-extracted documents (pdfplumber, Haiku OCR, Haiku image description) | 1.000 / 1.000 | 0.90 |
| Security: privileges, zero writes, leakage 0, injected instructions not followed | all pass | none: must pass |

Calibration rule, fixed before the first run: the threshold is the multiple of 0.05 just below (first-run value − max(0.03, 1/n)). The check is not required by the `ProteccionRama` ruleset. If it were, every PR that does not touch `semana-10/**` would wait forever for a check that never runs.

## Corrections during the week

These are recorded in each results file, because they changed how a result should be read:

- **Activity 2 ran out of API credit mid-run.** About 43 calls were billed without saved results (~$0.16, estimated). The script now saves after each question and resumes.
- **The first image question was rejected by the gold set builder:** its answer ("Occidente") already appeared in the text corpus. It was replaced by the chart value (95.1%).
- **Two drawing ambiguities were fixed before running activity 5:** the quarantine label overlapped aisle 13, and the critical SKU zone spanned docks 2 and 3.
- **The first assistant run applied SQL abstention to the mixed route too:** the NLQ rejected the whole question because it also had a document part, and mixed questions dropped to 0/6 ES and 2/6 EN. Abstention now applies only on the SQL route, where a fallback exists. Both runs are kept as evidence.
- **The first security run attributed one large object to the hardened chain:** each chain phase also ran the base connection. Each layer and each tool version is now its own phase. The direct statements also used the schema `copilot`, but the base tables live in `public`.
- **Effort level of the NLQ:** activity 2 measured Haiku at `medium`; the assistant and CI use `low`. CI measures `low` at 0.930–0.977, within two questions of `medium`.

## Failed cases

| Piece | Case | What happened | Detail |
|---|---|---|---|
| Legacy SQL, no dictionary | 7 of 86 | Haiku understood the structure but wrote `'ALEMANIA'` where the database stores ISO codes (`'DE'`), and searched the city in the warehouse name column | `resultados/sql_legado_detalle_claude-haiku-5-5_medium.csv` |
| Legacy SQL, retrieved dictionary | 0 of 22 correct when a needed table was not retrieved | Similarity retrieval kept the tables the question names (sales, stock) and dropped the item master `artmst` needed for the JOIN | same |
| PDF | `int-pdf-05` | "Seguridad" attracts other chunks; fails even with the original text, so it is ranking, not extraction | `resultados/pdf_tablas.md` |
| OCR | `rec-06` | ABC classes passage out of the top 5 for every extractor, including the original text | `resultados/ocr.md` |
| Images, Tesseract | 0/7 associated facts | Reads labels but not which value goes with which bar or zone; did not read "98.6%" | `resultados/imagenes.md` |
| Routing | `int-doc-27`, `int-pdf-04`, `int-imagen-11/12/13`, `int-ocr-07` | Document questions whose wording sounds like a database figure were routed to SQL | `resultados/ruteo.md` |
| Assistant | `int-mix-06` ES/EN | The definition of "at risk" (coverage vs supplier lead time) is in a document, but the tools run in parallel, so the SQL never sees it; it used "below reorder point" instead. Needs two steps (document → SQL) | `resultados/asistente.md` |
| Assistant | `int-doc-27` ES | Routed to SQL, NLQ abstained, fallback found the right document, answer incomplete | same |
| Assistant, SQL citation metric | `int-mix-03`, `int-sql-014` ES | Judge correct, but the query returned extra columns, so the strict result comparison fails | same |
| Security, base NLQ | `lo_create(0)`, read of `semana10.chunks` | Allowed by the activity 7 connection (see Security); closed by the hardened NLQ | `resultados/seguridad.md` |

## Cost

| Activity | Cost (USD) |
|---|---|
| 2 Legacy text-to-SQL (Sonnet and Haiku, 4 variants, pilot, cut run) | ~1.49 |
| 3 PDF, 4 OCR, 5 images | 0.073 |
| 6 Routing | 0.009 |
| 7 Assistant (pilot, run 1, final) | 0.82 |
| 8 Security (run 1, final) | 0.26 |
| 9 CI (calibration and thresholds) | 0.23 |
| **Total** | **~2.88** |

## Limitations

- Everything is synthetic: database (seed 42), documents, scans, images, roles and tenants. Real legacy schemas have hundreds of tables and abbreviations without a pattern; real scans and photos are noisier.
- Small sets: 43 SQL questions, 15 per type and 6 mixed per language, 4 injected documents. One question moves accuracy by 0.02 to 0.17.
- One run per configuration for most experiments; Haiku is not deterministic (CI legacy accuracy moved from 0.953 to 0.977 EN between two runs of the same code).
- The assistant runs its tools in parallel, so it cannot use a definition found in a document to write the SQL (`int-mix-06`).
- CI uses `text-embedding-3-small`; local experiments use bge-m3.
- Haiku not following injected instructions in 48 cases does not guarantee it never will. Protection against writes rests on the database (role and rolled-back transaction), and protection against leakage on the filter inside the query, not on the model.
