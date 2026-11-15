# Activity 8: final comparison for week 9

A summary of every technique measured in week 9 against the same baseline, with the same frozen gold set (`datasets/avanzado_{es,en}.jsonl`).
There are no new runs: every figure comes from the results file indicated. Every generative technique uses claude-haiku-5-5; prices from Anthropic's official page (`semana-07/prices.json`, consulted on 2026-10-26).

**Baseline:** vector search with bge-m3 and fixed 400/80 chunking (the `semana8` index in OpenSearch).

## 1. Base questions (50 per language, self-contained)

| Technique | Language | recall@5 | nDCG@10 | Cost per query (USD) | Added p50 latency | One-time indexing cost | Decision | Source |
|---|---|---|---|---|---|---|---|---|
| Vector (baseline) | ES | 1.000 | 0.904 | 0 | 0 | 0 | Baseline | week 8 |
| Vector (baseline) | EN | 1.000 | 0.885 | 0 | 0 | 0 | Baseline | week 8 |
| Reranking with Haiku | ES | 1.000 | **0.982** | ~0.0005 | ~2.4 s | 0 | Better ranking | week 8, activity 7 |
| Reranking with Haiku | EN | 1.000 | **0.974** | ~0.0005 | ~2.4 s | 0 | Better ranking | week 8, activity 7 |
| Query rewriting | ES | 1.000 | 0.898 | 0.000085 | 1.3 s | 0 | Not adopted | `reescritura.md` (2nd run) |
| Query rewriting | EN | 1.000 | 0.885 | 0.000098 | 1.5 s | 0 | Not adopted | `reescritura.md` (2nd run) |
| HyDE | ES | 0.960 | 0.886 | 0.000098 | 1.4 s | 0 | Not adopted | `hyde.md` |
| HyDE | EN | 0.880 | 0.816 | 0.000137 | 1.9 s | 0 | Not adopted | `hyde.md` |
| Contextual retrieval | ES | 0.970 | 0.873 | 0 | 0 | 0.0073 | Not adopted | `contextual.md` |
| Contextual retrieval | EN | 0.970 | 0.875 | 0 | 0 | 0.0073 | Not adopted | `contextual.md` |

## 2. Follow-up questions (15 per language, dependent on a previous question)

| Technique | Language | recall@5 | nDCG@10 | Cost per query (USD) | Added p50 latency | Source |
|---|---|---|---|---|---|---|
| Vector (baseline) | ES | 0.933 | 0.809 | 0 | 0 | `reescritura.md` |
| Vector (baseline) | EN | 0.867 | 0.802 | 0 | 0 | `reescritura.md` |
| Query rewriting | ES | 0.800 | 0.711 | 0.000040 | 0.9 s | `reescritura.md` (2nd run) |
| Query rewriting | EN | 0.933 | 0.793 | 0.000081 | 1.2 s | `reescritura.md` (2nd run) |
| HyDE (with the previous question) | ES | 0.933 | 0.750 | 0.000097 | 1.4 s | `hyde.md` |
| HyDE (with the previous question) | EN | 0.933 | 0.774 | 0.000159 | 2.2 s | `hyde.md` |
| Contextual retrieval | ES | 0.933 | 0.805 | 0 | 0 | `contextual.md` |
| Contextual retrieval | EN | 0.800 | 0.798 | 0 | 0 | `contextual.md` |

With 15 questions, one question moves recall by 0.067. Query rewriting went from 1.000 to 0.933 in EN between two runs of the same code: differences of one or two questions are noise.

## 3. Multi-hop questions (10 per set and language, two documents per question)

"Both" counts the questions with both passages in the top 5. The bridge set is the most favorable case for GraphRAG (the entity that links the documents does not appear in the question).

| Technique | Compound ES | Compound EN | Bridge ES | Bridge EN | Cost per query (USD) | p50 latency | One-time cost |
|---|---|---|---|---|---|---|---|
| Vector (baseline) | 9/10 | 7/10 | 9/10 | 5/10 | 0 | ~25 ms | 0 |
| Vector + reranking | **10/10** | **10/10** | **10/10** | **10/10** | ~0.0005 | ~2.3 s | 0 |
| GraphRAG by expansion (G) | **10/10** | 8/10 | 8/10 | 6/10 | 0 | ~25 ms | 0.048 |
| GraphRAG with entities from the question (G+Q) | 9/10 | 9/10 | **10/10** | 7/10 | 0.00014–0.00016 | ~1.8 s | 0.048 |

Source: `graphrag.md`.

## 4. Security: permissions and multi-tenancy (a non-negotiable criterion)

| Test | pgvector | Qdrant | OpenSearch | No filter (contrast) | Source |
|---|---|---|---|---|---|
| Permission leak by role (300 queries per database and language) | **0** | **0** | **0** | ~66 % unauthorized chunks | `permisos.md` |
| Forbidden passages returned (5 cases per language) | **0/5** | **0/5** | **0/5** | 5/5 | `permisos.md` |
| Leak across tenants (100 queries per database and language) | **0** | **0** | **0** | 36–38 % (alfa) and 62–64 % (beta) from the other tenant | `multitenant.md` |
| The other tenant's figure in near-identical texts (20 cases) | **0/20** | **0/20** | **0/20** | ranked first in 10/20 | `multitenant.md` |

The filter has no API cost. recall@5 with the filter (0.991) matches exactly what the permissions allow the user to see.

## Gains in recall vs. cost and latency

- **Recall:** no week 9 technique improves the baseline's recall@5 on the base questions, which is already at 1.000. On multi-hop questions, the only technique that takes every group to 10/10 is the week 8 reranking. GraphRAG with entities (G+Q) improves on vector search in English but does not reach reranking.
- **Ranking (nDCG@10):** reranking is the only technique that clearly improves it (ES 0.904 → 0.982; EN 0.885 → 0.974). Query rewriting, HyDE and contextual retrieval leave it unchanged or lower it.
- **Cost:** contextual retrieval and GraphRAG by expansion have no per-query cost (only one-time indexing costs of $0.007 and $0.048). Query rewriting and HyDE cost between $0.00004 and $0.00016 per query without improving anything. Reranking is the most expensive per query (~$0.0005), and the only one that pays for its cost with a better ranking.
- **Latency:** reranking adds ~2.3–2.4 s; HyDE, 1.4–2.2 s; query rewriting, 0.9–1.5 s; G+Q, ~1.8 s. Contextual retrieval, GraphRAG by expansion and the permission filters add no model-call latency.

## Decision for the pipeline

Vector search (bge-m3, fixed 400/80) with the tenant and role filter inside the query, and reranking with Haiku when ranking matters or the question spans two documents. Query rewriting, HyDE, contextual retrieval and GraphRAG are not adopted for this corpus.

## Limits of this comparison

- A small corpus (24 documents, 57 chunks): the baseline is already at the recall ceiling on the base questions, and the vector top 20 covers 35 % of the corpus, which favors reranking.
- One run per technique (two for query rewriting). Haiku is not deterministic.
- The latencies come from different runs, on the same Mac, and were not measured on a common benchmark.
- Every generative technique was tested only with Haiku 5.5.
