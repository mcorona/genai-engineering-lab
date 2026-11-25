# Week 9: advanced RAG (query rewriting, HyDE, contextual retrieval, GraphRAG, metadata filters, ACLs, multi-tenant)

> Spanish names (folders, files, JSON keys, flags, stack names, status values) are explained in the [glossary](../docs/glossary.md). The documentation is in English.

Goal: measure advanced RAG techniques against the week 8 baseline with the same frozen gold set, and make permissions and tenant isolation a hard, tested requirement.
Every generative step uses claude-haiku-5-5. Prices come from the official Anthropic pricing page (`semana-07/prices.json`, checked 2026-10-26). All figures link to a results file in `resultados/`.

**Baseline:** vector search with bge-m3 and fixed 400/80 chunking (week 8, OpenSearch index `semana8`).

## Gold sets (frozen before any experiment)

| Set | Per language | Purpose | File |
|---|---|---|---|
| Base | 50 | Standalone questions from week 8 | `datasets/avanzado_{es,en}.jsonl` |
| Follow-up | 15 | Need the previous question to make sense | same |
| Permission | 10 (5 allowed, 5 forbidden) | Role-based access | same + `datasets/permisos.json` |
| Multi-tenant | 10 | Near-identical documents in two tenants, different figures | `datasets/multitenant_{es,en}.jsonl`, `corpus_beta/` |
| Multi-hop, compound | 10 | Two documents, both topics named (control) | `datasets/multisalto_{es,en}.jsonl` |
| Multi-hop, bridge | 10 | Two documents, bridging entity hidden: best case for GraphRAG | `datasets/multisalto_puente_{es,en}.jsonl` |

All gold passages are validated as verbatim text and whole inside a chunk.

## Results

Full comparison: [`resultados/comparacion_final.md`](resultados/comparacion_final.md).

| # | Technique | Main result | Decision | Details |
|---|---|---|---|---|
| 2 | Query rewriting | Base unchanged (recall@5 1.000); follow-up ES 0.933 → 0.800, EN 0.867 → 0.933, within run-to-run noise | Not adopted | [`reescritura.md`](resultados/reescritura.md) |
| 3 | HyDE | Lowers recall on base EN (1.000 → 0.880) and nDCG@10 everywhere | Not adopted | [`hyde.md`](resultados/hyde.md) |
| 4 | Contextual retrieval | Base recall 1.000 → 0.970 (ES and EN); $0.007 one-off indexing, no query latency | Not adopted | [`contextual.md`](resultados/contextual.md) |
| 5 | Role filters (ACLs) | Leakage 0 in pgvector, Qdrant and OpenSearch; without filter ~66% of returned chunks were unauthorized | Adopted | [`permisos.md`](resultados/permisos.md) |
| 6 | Multi-tenant isolation | Cross-tenant leakage 0 in the three engines; own figure in top 5 in 20/20 near-identical cases; without filter, the other tenant's figure ranks first in 10/20 | Adopted | [`multitenant.md`](resultados/multitenant.md) |
| 7 | GraphRAG (426 entities, 532 relations in Postgres) | Vector + reranking gets both passages in the top 5 in 10/10 for all four groups; best GraphRAG variant reaches 7/10 on bridge EN | Not adopted | [`graphrag.md`](resultados/graphrag.md) |

**Pipeline decision:** vector search with tenant and role filters inside the query, plus Haiku reranking when ranking matters or the question spans two documents.

## CI

`.github/workflows/recuperacion-semana-09.yml` runs on every PR that touches `semana-09/**`, with a pgvector service and `text-embedding-3-small`. It fails if recall@5 drops below 0.90 in either language, or on **any** leakage by role or across tenants. Leakage has no threshold. First run: recall@5 ES 0.990, EN 0.950; all leakage checks 0 ([`ci_semana09.md`](resultados/ci_semana09.md)).

## Corrections during the week

These are recorded in each results file, because they changed how a result should be read:

- **Output token limits:** Haiku returns reasoning (`thinking`) blocks before the text, billed as output. Limits that were too low produced empty or cut outputs in HyDE (5 of 130 fell back to the original question) and GraphRAG extraction (14 of 57 invalid JSON). Both runs were discarded, limits raised, and the experiments rerun. Contextual retrieval and GraphRAG stop without indexing if any output is invalid.
- **Query rewriting** was run twice with the same code: follow-up EN went from 1.000 to 0.933. Differences of one or two questions are treated as noise.
- **Multi-tenant contrast:** the first version summed unfiltered other-tenant chunks across both users, which is always 10 per question by construction. It was split per tenant.
- **CI:** the first run failed on an HTTP 500 from the embeddings API. Retries with backoff were added for transient errors only.

## Failed cases

Questions where a technique lost a gold passage from the top 5 that the vector baseline had found. Taken from the per-query detail files; partial losses on two-passage questions are not listed one by one, which is why some averages do not move in whole questions.

| Technique | Lost (ES) | Lost (EN) | What happened | Detail |
|---|---|---|---|---|
| Query rewriting (follow-up) | `seg-02`, `seg-14` | `seg-14` | Rewrites were faithful (e.g. "what do I do if the copilot gives a wrong answer?"); the rephrasing moved the vector ranking. EN also gained `seg-02` and `seg-10`. | `resultados/reescritura_detalle.csv` |
| HyDE (base) | `rec-23`, `rec-44` | `rec-26`, `rec-38`, `rec-44`, `rec-46`, `rec-50` | Searching with the generated passage instead of the question lost these gold passages; the cause was not analyzed question by question. The generated passages are in the detail file. | `resultados/hyde_detalle.csv` |
| Contextual retrieval | `rec-34`, `seg-14` | `rec-34`, `seg-13`, `seg-14` | Same questions fail in both languages, so the index caused it: long contexts (267 chars vs 348 per chunk) that repeat the company name dilute each chunk. `seg-10` gained in both. | `resultados/contextual_detalle.csv` |
| GraphRAG, expansion (G) | bridge `pt-08`, `pt-10` | compound `ms-07` | Graph neighbors pushed correct vector results out of the top 5. | `resultados/graphrag_detalle.csv` |
| GraphRAG, query entities (G+Q) | none below baseline | bridge `pt-01`, `pt-03`, `pt-05` (one passage of two) | Best GraphRAG variant still misses one hop on three bridge questions; vector + reranking finds both. | `resultados/graphrag_detalle.csv` |
| Role filters, multi-tenant, CI | none | none | Leakage 0 in every run. | `resultados/permisos.md`, `resultados/multitenant.md`, `resultados/ci_semana09.md` |

## Limits

- Small corpus (24 documents, 57 chunks). The baseline already has recall@5 1.000 on base questions, and the vector top 20 covers 35% of the corpus, which favors reranking over GraphRAG.
- One run per technique (two for query rewriting); Haiku is not deterministic.
- Generative techniques were tested only with Haiku 5.5.
- Synthetic roles and tenants; document-level permissions; one role per user in most tests.
- CI checks pgvector only. Qdrant and OpenSearch were verified locally.
- Latencies come from separate runs on the same Mac, not a shared benchmark.
