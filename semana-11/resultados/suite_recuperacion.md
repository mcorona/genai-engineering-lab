# Activity 2: retrieval suite

Script: `experimentos/suite_recuperacion.py` (run on 2026-10-27). Detail per query: `suite_recuperacion_detalle.csv`; rankings and RAGAS scores: `suite_recuperacion_cache.json`.

## Design

- **Questions:** the 65 answerable questions per language of `datasets/eval_rag_{es,en}.jsonl` (50 base, 15 non-text). Unanswerable questions do not apply to recall.
- **Index:** `semana10.chunks` (week 10, activity 7: 30 documents, 68 chunks, bge-m3). User of tenant `alfa` with all roles; the filter is inside the query, as in the assistant.
- **Configurations:**
  - `base`: vector + filter, in similarity order.
  - `adoptado`: the same plus Haiku 5.5 reranking of the top 20, as in the assistant.
- **Custom metrics:** exact relevance, the same definition as weeks 8 to 10. A chunk is relevant if it comes from the reference document and contains the gold passage; for non-text questions, the exact answer.
  - recall@1, 3, 5 and 10; MRR; nDCG@10; precision@5.
  - AP@5: the same formula as RAGAS context precision, but with exact relevance instead of the judge. It was added after the first run, to compare the two one to one.
- **RAGAS 0.4.3 metrics:** on the top 5, with the reference answer from activity 1, and Haiku 5.5 `low` as judge:
  - context precision: position-weighted precision of the chunks the judge finds useful for the reference;
  - context recall: share of the reference's claims that can be attributed to the top 5.
- **Configuration difference:** paired mean per query, with a 95% bootstrap interval (2,000 resamples, seed 11).

## Results

| Config | Lang | recall@1 | recall@3 | recall@5 | recall@10 | MRR | nDCG@10 | precision@5 | context precision | context recall | Latency p50 (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base | ES | 0.769 | 0.962 | 1.000 | 1.000 | 0.877 | 0.905 | 0.240 | 0.896 | 1.000 | 0.01 |
| base | EN | 0.738 | 0.908 | 1.000 | 1.000 | 0.851 | 0.888 | 0.237 | 0.869 | 1.000 | 0.01 |
| adoptado | ES | 0.862 | 1.000 | 1.000 | 1.000 | 0.936 | 0.952 | 0.249 | 0.972 | 1.000 | 2.18 |
| adoptado | EN | 0.862 | 1.000 | 1.000 | 1.000 | 0.936 | 0.952 | 0.252 | 0.959 | 1.000 | 2.16 |

The split by question type is in the script output. Non-text questions score at or above base questions on every metric, except context precision in `adoptado` ES (0.970 vs 0.972).

The base latency is the amortized cost of a batched embedding plus the pgvector query; a single query embedding takes longer. Reranking adds about 2.2 s.

### Does the suite tell the two configurations apart?

Reranking minus base, paired by query, with the 95% interval:

| Metric | ES | EN |
|---|---|---|
| recall@1 | +0.092 [−0.023, +0.208] | +0.123 [+0.000, +0.238] |
| recall@3 | **+0.038 [+0.008, +0.085]** | **+0.092 [+0.031, +0.162]** |
| recall@5, recall@10, context recall | 0 (both at 1.000) | 0 |
| MRR | +0.058 [−0.009, +0.128] | **+0.085 [+0.008, +0.162]** |
| nDCG@10 | +0.047 [−0.001, +0.097] | **+0.065 [+0.009, +0.121]** |
| precision@5 | **+0.009 [+0.000, +0.018]** | **+0.015 [+0.003, +0.031]** |
| context precision (RAGAS) | **+0.078 [+0.025, +0.136]** | **+0.090 [+0.031, +0.152]** |

**Yes, for ranking metrics.** recall@3 and context precision separate the two configurations in both languages; MRR and nDCG@10 do in EN, and their ES intervals touch zero. Recall at 5 or more does **not** separate them: both configurations put every gold passage in the top 5 (ceiling effect, the same as week 8). In this corpus, reranking changes order, not coverage.

## Custom metrics vs RAGAS

| Pair (same queries, top 5) | base | adoptado |
|---|---|---|
| recall@5 vs context recall | 130/130 agree; both always 1.000, so no correlation can be computed | 129/129 agree |
| AP@5 vs context precision (same formula) | Pearson 0.841; 113/130 within 0.1; RAGAS higher in 12, lower in 5 | Pearson 0.574; 117/129 within 0.1; RAGAS higher in 9, lower in 3 |
| MRR vs context precision | Pearson 0.826 | 0.580 |
| precision@5 vs context precision | Pearson −0.021 | −0.126 |

**Where they agree:** context recall matches exact recall@5 on every query. Context precision follows AP@5 closely: means of 0.882 vs 0.854 (base) and 0.965 vs 0.936 (adoptado). The correlation drops after reranking because most queries reach 1.0 on both, leaving little variance.

**Where they disagree, and why:**
- **RAGAS context precision is a ranking metric, not the share of relevant chunks.** It averages precision only at the positions the judge marks useful. It correlates with MRR (0.83) and not with precision@5 (≈ 0). One relevant chunk at rank 1 gives 1.0, even if the other four are noise. Its name invites the wrong reading.
- **RAGAS scores higher (12 + 9 cases) when another chunk also contains the answer.** Two kinds:
  - **Evidence missing from the gold set:** `rec-25` asks for the transit time from Guadalajara to Monterrey. The freight-rate table from week 10 (`tarifas_flete`) also says "2 días", but the gold passage only points to the week 8 document. Here RAGAS is right and the exact metric undercounts.
  - **Passage split across chunks:** `rec-02`, `rec-22` and `rec-28`. A chunk from the same document contains part of the passage, enough to answer. The exact metric requires the whole passage.
- **RAGAS scores lower (5 + 3 cases) when it marks an extra chunk useful at a low rank.** For example, `rec-05` ES and `rec-17` EN have the relevant chunk at rank 1 (AP@5 = 1.00), but the judge also counted a chunk at rank 5 as useful, which lowers the average to 0.70. Context precision penalizes useful chunks that arrive late.
- **One judge failure out of 260** (`int-pdf-04` ES, adoptado, context precision). Haiku returned the verdict inside the reason text, so Instructor's schema check failed 4 times. The query is left without that score and does not enter the averages.

## Cost

| Item | Cost |
|---|---|
| Reranking (130 queries) | $0.0642 ($0.00049 per query) |
| RAGAS judge, Haiku 5.5 low (1,185 calls, 2.99 M input and 0.22 M output tokens) | $0.4071 |
| **Total** | **$0.4713** (estimate was $0.30; cap $0.50) |

The estimate fell short because context precision sends the full chunk and the reference in one call per chunk (about 2,500 input tokens per call). Judging retrieval with RAGAS costs about **$0.0016 per query and configuration**, more than three times the reranking. For CI (activity 8), the exact metrics are free and already separate the configurations; RAGAS context metrics are worth running on a subset.

## Decision

- **Retrieval suite:** exact metrics (recall@k, MRR, nDCG@10, AP@5) as the main measure: free, deterministic and they detect the reranking change. RAGAS context precision as a complement, because it catches valid evidence the gold set does not list.
- **Gold set finding:** `rec-25` has a second valid source (`tarifas_flete`). The frozen set is not changed; the case is recorded here.
- **Not useful on this corpus:** recall@5, recall@10 and context recall are all at 1.000 in both configurations, so they cannot detect a regression at k ≥ 5. A harder set or a larger corpus would be needed.

## Limitations

- One run; the RAGAS judge is not deterministic.
- Small corpus (30 documents, 68 chunks): the top 20 candidates cover almost a third of the index, which favors reranking and saturates recall.
- The RAGAS judge is Haiku 5.5 `low`; the generation-side meta-evaluation (activity 3) compares judges, but this activity does not.
