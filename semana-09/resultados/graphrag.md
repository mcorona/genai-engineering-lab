# Activity 7: GraphRAG (a scoped comparison)

Run of 2026-10-26. Script: `experimentos/graphrag.py`. Model: claude-haiku-5-5.

## Graph

Haiku extracted entities and relations from each of the 57 week 8 chunks (fixed 400/80). The graph was stored in Postgres:
`semana9.entidades` (chunk, entity, type) and `semana9.relaciones` (chunk, source, relation, target), with normalized names (lowercase, no accents).

- **Size:** 426 unique entities and 532 relations.
- **Validity:** 57 of 57 extractions with valid JSON (the script does not load the graph if any fails). Cache: `grafo_extraccion.jsonl`.
- **One-time extraction cost:** 25,936 input tokens and 90,017 output tokens, **$0.0476**. p50 latency of 6.9 s per chunk. The output is large because Haiku reasons before the JSON.
- **Generic entities:** none appears in more than 30% of the chunks (a threshold set before the run), so none was excluded from the expansion. The expansion weights each entity by 1/df.

## Questions

Only multi-hop questions, with two passages from two different documents, frozen before the experiment:

- **compound** (`datasets/multisalto_*.jsonl`, 10 per language): the question names both topics. This is the control.
- **bridge** (`datasets/multisalto_puente_*.jsonl`, 10 per language): **the most favorable case for GraphRAG**. The entity that links the documents does not appear in the question. For example, "how many days of transit are there from Mexico City to the distribution center with capacity for 12,000 pallet positions?": Monterrey has to be identified in one document and the transit time looked up in another.

Validation: the passages are literal, complete within a chunk, and from different documents (`datasets/construir_multisalto.py`).

## Methods

- **V:** vector search (bge-m3, OpenSearch `semana8`), top 10. The baseline.
- **V+R:** vector top 20 + reranking with Haiku, top 10. The comparison the plan calls for.
- **G:** 3 vector seeds + chunks connected by shared entities or by a relation (weight 1/df), filled in with the vector results.
- **G+Q:** Haiku extracts the entities of the question, in Spanish even when the question is in English; the chunks that mention them are fused with the vector results by RRF (k=60).

Metrics fixed before the run: recall@5 over the two passages, questions with both passages in the top 5, nDCG@10 and MRR, plus cost and latency per query.

## Results

| Set | Language | Method | recall@5 | Both passages in top 5 | nDCG@10 | MRR | Cost per query (USD) | p50 latency (ms) | Failures |
|---|---|---|---|---|---|---|---|---|---|
| compound | es | V | 0.950 | 9/10 | 0.923 | 0.950 | 0 | 29 | 0 |
| compound | es | V+R | **1.000** | **10/10** | **1.000** | **1.000** | 0.000504 | 2281 | 0 |
| compound | es | G | **1.000** | **10/10** | 0.946 | 0.950 | 0 | 29 | 0 |
| compound | es | G+Q | 0.950 | 9/10 | 0.899 | 0.900 | 0.000137 | 1714 | 0 |
| compound | en | V | 0.850 | 7/10 | 0.845 | 0.870 | 0 | 26 | 0 |
| compound | en | V+R | **1.000** | **10/10** | **0.969** | **0.950** | 0.000502 | 2316 | 0 |
| compound | en | G | 0.850 | 8/10 | 0.830 | 0.867 | 0 | 26 | 0 |
| compound | en | G+Q | 0.950 | 9/10 | 0.901 | **0.950** | 0.000144 | 1685 | 0 |
| bridge | es | V | 0.950 | 9/10 | 0.910 | **0.950** | 0 | 24 | 0 |
| bridge | es | V+R | **1.000** | **10/10** | **0.941** | **0.950** | 0.000507 | 2585 | 0 |
| bridge | es | G | 0.900 | 8/10 | 0.867 | **0.950** | 0 | 25 | 0 |
| bridge | es | G+Q | **1.000** | **10/10** | 0.867 | 0.833 | 0.000150 | 1909 | 0 |
| bridge | en | V | 0.750 | 5/10 | 0.778 | 0.875 | 0 | 25 | 0 |
| bridge | en | V+R | **1.000** | **10/10** | **0.961** | **0.950** | 0.000490 | 2332 | 0 |
| bridge | en | G | 0.800 | 6/10 | 0.766 | 0.875 | 0 | 25 | 0 |
| bridge | en | G+Q | 0.850 | 7/10 | 0.805 | 0.925 | 0.000162 | 1822 | 0 |

Detail per query: `graphrag_detalle.csv`.

## Reading

- **Vector + reranking is the best method in all four groups.** It retrieves both passages in the top 5 for 10 of 10 questions in every set and language, and it has the best nDCG@10. It costs about $0.0005 per query and adds about 2.3 s.
- **GraphRAG does not beat that baseline, not even in the most favorable case (bridge).** In bridge EN, G+Q retrieves 7 of 10 and V+R 10 of 10; in bridge ES both reach 10 of 10, but G+Q with a worse ranking (nDCG@10 0.867 vs. 0.941).
- **Why reranking wins on this corpus:** V+R only reorders the first 20 vector candidates, and it retrieved both passages for all 40 questions, so in every case both passages were already in the vector top 20. With 57 chunks, the top 20 is 35% of the corpus. The vector search's problem was ranking the second passage, not finding it, and a reranker solves that.
- **G (expansion, no query cost)** improves on vector search for some questions (`ms-01`, `pt-05`) but makes others worse (`pt-08` and `pt-10` in ES): the graph neighbors displace vector results that were correct. On balance it ties or loses, except in compound ES and bridge EN.
- **G+Q (entities from the question)** helps mainly in English (compound EN from 7 to 9 of 10; bridge EN from 5 to 7 of 10). It found graph entities for 40 of 40 questions, including English questions against a Spanish graph. It costs $0.00014 to $0.00016 per query, a third of reranking, but retrieves less.
- **Total cost of the graph:** $0.048 of one-time extraction, plus the per-query cost of G+Q. With a corpus of this size, that investment does not pay off.

## Conclusion

GraphRAG adds nothing over the vector + reranking baseline on this corpus, neither on compound questions nor in the most favorable case, with the bridge entity hidden. It is not adopted. It is documented without adjusting the metric: the metrics, the thresholds (30% for generic entities, 3 seeds, RRF k=60) and the question sets were fixed before the run.

The case in which GraphRAG could win is a much larger corpus, where the second passage falls outside the vector top 20 and the reranker cannot see it. That case was not tested here.

## Corrections during the activity

- **Token limit in the extraction:** with `max_tokens` 2000, 14 of 57 extractions were cut off at the limit, because Haiku reasons before the JSON. The script stopped without loading the graph, as designed. The limit was raised to 6000; the longest output was 2,931 tokens. The 43 valid extractions from the first run were reused from the cache (their JSON was complete).
- **Services:** Postgres (`copilot-db`) and OpenSearch stopped during the session (a clean shutdown, exit code 0) and were brought back up with no data loss.

## Limitations

- 10 questions per set and language: one question moves "both in the top 5" by 10%.
- A small corpus (57 chunks): the top 20 covers a third of the corpus, which favors reranking.
- A graph without entity resolution beyond normalization: variants such as `cedis monterrey` and `cedis monterrey.md` appear.
- A single local GraphRAG configuration (1 hop). Community summaries (global GraphRAG) were not tested.
- A non-deterministic LLM in extraction, reranking and question entities. One run.
