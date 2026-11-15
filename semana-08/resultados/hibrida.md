# Activity 6 (week 8): BM25, vector and hybrid search with RRF

Run of 2026-10-26. Script: `experimentos/hibrida_bm25.py` (the same as in commit `47da5c6`, which was only on the `hibrida-bm25` branch of PR #13, unmerged).
The `semana8` index in OpenSearch 2.19.1: 57 chunks (fixed 400/80) with bge-m3. The week 8 gold set (`datasets/recuperacion_{es,en}.jsonl`, 50 questions per language). No generative models.

- **BM25:** `match` on `content`, with OpenSearch's standard analyzer.
- **Vector:** k-NN with bge-m3.
- **Hybrid:** RRF fusion (k = 60) of the BM25 top 20 and the vector top 20.

## Results

| Language | Method | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| ES | BM25 | 0.930 | 0.970 | 0.824 |
| ES | Vector | **1.000** | **1.000** | 0.860 |
| ES | Hybrid RRF | 0.970 | 0.970 | **0.912** |
| EN | BM25 | 0.270 | 0.330 | 0.188 |
| EN | Vector | **1.000** | **1.000** | **0.834** |
| EN | Hybrid RRF | 0.770 | 0.900 | 0.582 |

MRR in this script: the average, per reference passage, of 1/position within the top 10. This definition differs from the one used for reranking (activity 7), which takes the first relevant chunk per question, so the MRR values of the two tables are not directly comparable.

## Reading

- **ES:** the hybrid improves the ranking (MRR from 0.860 to 0.912) but loses recall@5 (from 1.000 to 0.970): RRF pushes into the top 5 chunks that only BM25 ranked high.
- **EN:** BM25 barely works (recall@5 0.270), because the questions are in English and the corpus is in Spanish: they share no terms. RRF gives it the same weight as the vector search and pushes that noise to the top: the hybrid lowers recall@5 from 1.000 to 0.770.
- **Decision:** hybrid search is not adopted for this corpus. For ranking, reranking with Haiku (activity 7) improves more without losing recall.

## Limitations

- The gold set has no exact-term queries (codes, IDs, SKUs), which is where BM25 should help most. This result does not say whether hybrid search is worthwhile in general.
- RRF with equal weights. Per-language weights, or disabling BM25 for queries in another language, were not tested.
- A single run (BM25 and the index are deterministic).
