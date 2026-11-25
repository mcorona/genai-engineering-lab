# Activity 5: end-to-end RAG and failure attribution

Script: `experimentos/extremo_a_extremo.py` (run on 2026-10-27). Output: `e2e_salida.txt`; detail: `e2e_detalle.csv`; contexts: `e2e_contextos.json`; answers and scores: `e2e_cache_<config>.json`.

## Design

- **Full RAG:** retrieval from activity 2 + generation from activity 4 on what was retrieved, with the same metrics (Haiku 5.5 `low` judge). All 75 questions per language.
- **`adoptado_top5`:** the assistant's pipeline (vector + filter + Haiku reranking, top 5). Answerable questions reuse the activity 2 rankings; the 20 unanswerable ones were ranked here with the same code.
- **`estres_base_top3`:** no reranking and only 3 chunks. It is not a candidate configuration. The adopted pipeline puts every gold passage in its context, so on its own it gives nothing to attribute to retrieval. This configuration leaves the passage out in 11 questions, to check that the attribution separates the two kinds of failure.
- **Failure:** an answerable question with correctness 0 (custom judge), or an unanswerable question the generator answers instead of declining.
- **Attribution, fixed before running:** **retrieval** if any gold passage did not reach the context; **generation** if all passages arrived and the answer failed. Unanswerable questions that get an answer count as generation.

## Results

| Config | Lang | Context recall | Correctness | faithfulness | answer relevancy | Citation precision | Citation coverage | False abstention |
|---|---|---|---|---|---|---|---|---|
| adoptado_top5 | ES | 1.000 | **0.985** | 0.813 | 0.878 | 0.637 | 1.000 | 0/65 |
| adoptado_top5 | EN | 1.000 | **1.000** | 0.814 | 0.871 | 0.650 | 1.000 | 0/65 |
| estres_base_top3 | ES | 0.962 | 0.908 | 0.790 | 0.842 | 0.657 | 0.969 | 1/65 |
| estres_base_top3 | EN | 0.908 | 0.892 | 0.796 | 0.830 | 0.657 | 0.923 | 4/65 |

Unanswerable questions: correct abstention **10/10** in every configuration and language; 0 invented answers.

### Failure attribution (language × type)

| Config | Lang | Base (50) | Non-text (15) | Unanswerable (10) | Total failures | Retrieval | Generation |
|---|---|---|---|---|---|---|---|
| adoptado_top5 | ES | 1 | 0 | 0 | **1** | 0 | 1 |
| adoptado_top5 | EN | 0 | 0 | 0 | **0** | 0 | 0 |
| estres_base_top3 | ES | 6 | 0 | 0 | **6** | 4 | 2 |
| estres_base_top3 | EN | 6 | 1 | 0 | **7** | 6 | 1 |

### Failures, one by one

| Config | Question | Attribution | What happened |
|---|---|---|---|
| adoptado_top5 | `rec-22` ES | generation | Correct rule (purchasing manager approves an urgent purchase regardless of amount), but it also brings in the general approval table from another chunk ("over $250,000: director of operations"), which contradicts "regardless of amount". The judge marks it wrong: the generator mixed two rules. |
| estres_base_top3 | `rec-22` ES | generation | Same mix of rules as above. |
| estres_base_top3 | `rec-17` ES/EN | generation | The gold passage arrived, but the chunk ends mid-sentence ("Se busca reemplazo y no se…"). The generator said the sentence was cut off and did not complete it, so the second half of the reference is missing. **The cause is the chunk boundary, not the model**; with the adopted top 5, the same question passes. |
| estres_base_top3 | `rec-29` ES/EN, `rec-06` EN, `int-pdf-05` EN | retrieval | Passage not in context (recall 0). The generator said the context does not answer; it did not invent. |
| estres_base_top3 | `rec-22` EN | retrieval | Passage not in context (recall 0). The generator answered from the general approval table (by amount), which does not cover the urgent-purchase exception. |
| estres_base_top3 | `rec-47`, `rec-48`, `rec-49` (ES and EN) | retrieval | Two-passage questions with only one passage in context (recall 0.5). The answer covers the part that arrived and says the rest is not there. |

Not a failure, though the passage did not arrive: `rec-28` EN under stress answered correctly from another chunk (the copilot is read-only), alternative evidence like `rec-25` in activity 2.

## Reading

- **The adopted RAG fails 1 of 150 questions, and that failure is generation.** Retrieval brought every gold passage. The only error is the generator mixing the urgent-purchase exception with the general approval table.
- **The attribution separates the two causes when both exist.** Under stress, 10 of 13 failures are retrieval and 3 are generation. In 9 of the 10 retrieval failures the generator says the context does not answer, or covers only the part that arrived, instead of inventing. The exception is `rec-22` EN, which answered from a related but wrong rule.
- **A third cause hides under "generation": chunk boundaries.** `rec-17` has the gold passage in context, but its consequence sits in the next chunk. A failure attributed to generation with the passage present should be checked for truncation before blaming the model.
- **End-to-end vs isolated suites:** correctness with the real top 5 (0.985 / 1.000) is close to the generation suite with fixed contexts (1.000 / 1.000), and consistent with retrieval recall@5 = 1.000. Faithfulness is higher end to end (0.813 / 0.814) than in the generation suite (0.679 / 0.805), with the same rate of "no SQL" remarks (38 and 24 of 75). One likely reason: the real top 5 often holds neighboring chunks of the same document, which support the extra details the generator adds, while the suite's distractors exclude the gold passage. This was not tested directly.

## Cost

| Item | Cost |
|---|---|
| adoptado_top5: generation $0.0331 + evaluation $0.1356 | $0.1687 |
| estres_base_top3: generation $0.0286 + evaluation $0.1317 | $0.1603 |
| Reranking of unanswerable questions | $0.0094 |
| **Total** | **$0.338** |

Generation p50 latency: 2.4 s (top 5) and 1.9 s (top 3). Three judge scores are missing in the stress run (Haiku returned the claim list as text twice for faithfulness, once for relevancy); they do not affect correctness or attribution.

## Limitations

- One run; generator and judges are not deterministic.
- The stress configuration is artificial (3 chunks without reranking) and exists only to exercise the attribution.
- Attribution is binary; truncation by chunking (`rec-17`) is identified by reading the case, not by the rule.
