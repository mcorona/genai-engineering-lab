# Activity 4: contextual retrieval with claude-haiku-5-5

Run of 2026-10-26. Script: `experimentos/contextual.py`.
For each of the 57 week 8 chunks (fixed 400/80), Haiku receives the full document and the chunk, and writes a short context.
The embedding (bge-m3) is computed over `context + chunk` and indexed in OpenSearch as `semana9_ctx`.
The `content` field keeps the original chunk, so the comparison against the reference passage is identical to the baseline's (`semana8`).
The queries are the same for both indexes. The permission cases are evaluated in activity 5.

Validity: 57 of 57 contexts contain text (the script does not index if any comes back empty). Every response was a single `text` block.
Contexts: `contextos.jsonl`. Detail per query: `contextual_detalle.csv`.

## Results

| Type | Language | Index | recall@5 | nDCG@10 | MRR |
|---|---|---|---|---|---|
| base | es | semana8 (baseline) | 1.000 | 0.904 | 0.874 |
| base | es | semana9_ctx | 0.970 | 0.873 | 0.834 |
| follow-up | es | semana8 (baseline) | 0.933 | 0.809 | 0.747 |
| follow-up | es | semana9_ctx | 0.933 | 0.805 | 0.763 |
| base | en | semana8 (baseline) | 1.000 | 0.885 | 0.845 |
| base | en | semana9_ctx | 0.970 | 0.875 | 0.841 |
| follow-up | en | semana8 (baseline) | 0.867 | 0.802 | 0.739 |
| follow-up | en | semana9_ctx | 0.800 | 0.798 | 0.756 |

## Cost and size

- **Indexing (one time):** 42,119 input tokens and 6,111 output tokens, $0.00727 at the price in `semana-07/prices.json` (author's source, 2026-10-21). p50 latency of 1.2 s per chunk.
- **Query:** no added cost or latency, because search does not call Haiku.
- **Index size:** 1,471,171 B (`semana8`) vs. 1,490,310 B (`semana9_ctx`), 1.3 % larger.

## Cases whose recall@5 hit changes

| Question | ES | EN |
|---|---|---|
| `rec-34` (perishable SKUs reviewed every week) | lost | lost |
| `seg-10` (who approves the urgent purchase of that SKU) | gained | gained |
| `seg-13` (and can it change prices?) | no change | lost |
| `seg-14` (and what do I do if it gives me a wrong answer?) | lost | lost |

The changes agree in both languages, so they come from the index, not from query noise: with the same query embeddings and a deterministic index, the difference is the added context.

## Reading

- **It does not improve recall.** It drops on base questions (ES and EN, from 1.000 to 0.970) and on EN follow-ups (from 0.867 to 0.800). It does not change on ES follow-ups.
- **The ranking improves slightly, and only on follow-ups.** MRR rises by 0.016 in ES and 0.017 in EN; nDCG@10 drops slightly in all four cells.
- **Hypothesis (not verified):** the contexts are long relative to the chunk (267 characters on average vs. 348), and 51 of 57 repeat the company name. That shared text makes the chunk embeddings more similar to each other and dilutes what is specific to each chunk. Besides, the baseline is already at the ceiling (recall@5 of 1.000 on base questions), so there is little room to gain.

## Conclusion

Contextual retrieval does not improve retrieval on this corpus and is not adopted. Its indexing cost is low ($0.007 one time) and it adds no query latency, so the problem is not the cost: it adds nothing with 24 short documents whose chunks already carry their topic.

A variant with shorter contexts and without the company name could test the dilution hypothesis. It remains an option, not a pending item of this activity.

## Limitations

- One run. The index and the queries are deterministic, but Haiku's contexts may vary if they are regenerated.
- Vector search only. BM25 over the contextualized text (contextual BM25), the other half of the original technique, was not tested.
- A small, homogeneous corpus: the expected benefit of the technique is larger in big corpora, with chunks that lose their context.
