# Activity 6: sensitivity of the suites to pipeline changes

Script: `experimentos/sensibilidad.py` (run on 2026-10-27). Output: `sensibilidad_salida.txt`; generation runs: `sensibilidad_gen_<variant>.json`; rankings and the rec300 index count: `sensibilidad_cache.json`; rec300 generation contexts: `contextos_generacion_rec300.json`.

## Design

- **Baseline (adopted pipeline):** retrieval suite = `adoptado` from activity 2; generation suite = fixed contexts and answers from activity 4 (Haiku 5.5 `medium`, the assistant's prompt).
- **Controlled changes, one at a time:**
  - `sin_rerank`: no reranking.
  - `sin_solo_contexto`: generator prompt without "use ONLY the context" and without "if the context is not enough, say so and do not invent".
  - `rec300`: recursive 300-character chunking instead of fixed 400/80, over the same 30 documents (new index `semana11.chunks_rec300`, 98 chunks instead of 68).
  - Extra variant, not a degradation: `solo_documentos`, the assistant's prompt without the `[SQL]` citation instruction (pending from activity 4).
- **Noise controls:** one more reranking with no change, and one more generation with no change. They show how much each suite moves on its own.
- **Isolation by construction:** the retrieval suite never calls the generator, and the generation suite uses fixed contexts. So reranking cannot move the generation suite, and the prompt cannot move the retrieval suite. This was checked by input fingerprints: the generation contexts are `1760e690916f` in every variant except rec300, and the retrieval rankings are `026fd458c7c6`.
- **Rule, fixed before running:** a metric moves if its paired difference against the baseline has a 95% bootstrap interval that excludes 0 **and** is larger than the noise control's difference. A suite moves if any of its main metrics moves:
  - retrieval: recall@3, recall@5, MRR, nDCG@10, AP@5;
  - generation: correctness, faithfulness, answer relevancy, citation precision; plus correct abstention on the 20 unanswerable questions, if the count changes by 2 or more and by more than in the repetition.

## Results

| Change | Retrieval suite | Generation suite | Expected |
|---|---|---|---|
| Noise: repeated reranking | no metric moves (MRR +0.021, CI includes 0) | - | - |
| Noise: repeated generation | - | no metric moves (faithfulness +0.031, CI includes 0) | - |
| **sin_rerank** | **moves:** recall@3 −0.065, MRR −0.072, nDCG@10 −0.056, AP@5 −0.083 (all CIs exclude 0); recall@5 unchanged | does not move (by construction; same contexts) | ✅ retrieval only |
| **sin_solo_contexto** | does not move (by construction; same ranking) | **moves:** faithfulness **+0.111** [+0.059, +0.163]; correctness unchanged; correct abstention 19/20 (baseline 20/20) | ✅ generation only, but in the opposite direction from the expected one (see reading) |
| **rec300** | **moves:** recall@3 and recall@5 −0.038 [−0.073, −0.012]; MRR, nDCG and AP@5 do not | **moves:** correctness −0.038 [−0.077, −0.008]; 1 false abstention | both, as expected for an indexing change |
| solo_documentos | does not move (by construction) | **moves:** faithfulness **+0.116** [+0.075, +0.159]; correctness unchanged; abstention 20/20; 1 false abstention | improvement candidate |

## Reading

- **Each suite moves only with the component it measures.** Removing reranking moves the order metrics of retrieval and cannot touch generation. Changing the prompt moves generation and cannot touch retrieval. Neither noise control moved any metric.
- **`sin_solo_contexto` moved generation, but faithfulness went up, not down.** Two things changed at once. The prompt without the "only context" rule also drops the `[SQL]` instruction, and the "no SQL result" remarks went from 68 answers to 0. That artifact dominates, as in activity 4. Comparing the two prompts without SQL directly isolates the "only context" instruction:

  | `sin_solo_contexto` − `solo_documentos` | Difference | 95% CI |
  |---|---|---|
  | faithfulness | −0.005 | [−0.043, +0.033] |
  | correctness | 0.000 | [0, 0] |
  | citation precision | −0.034 | [−0.064, −0.005] |
  | correct abstention | 19/20 vs 20/20 | - |

  Without the instruction, Haiku stays almost as grounded. The one visible degradation is `nr-07` ES (year-end bonus). The answer says the documents do not have it, then adds outside knowledge: "the Federal Labor Law sets a minimum…". The suite catches it through the abstention judge and citation precision, but the effect is small, and with 20 unanswerable questions it does not reach the rule's threshold (≥ 2). A weaker model, the plan's alternative, was not tested.
- **Chunking is an indexing change, so it reaches both suites.** The generation contexts are built from the index, so smaller chunks change what the generator reads:
  - Retrieval loses 5 gold passages per 130 queries (passages split by the 300-character chunks, as week 8 predicted: 48/50 intact).
  - Generation loses correctness in `int-imagen-12` ES/EN and `int-imagen-13` ES: the chunk keeps "98.6%" but loses the chart's title with the period, so the generator refuses to confirm "September 2026". `rec-27` ES and `rec-48` EN also fail, with answers left incomplete by the shorter chunks. This is the `rec-17` pattern from activity 5: chunk boundaries cost context that a failure count attributes to generation.
- **The documents-only prompt is a free improvement for document-only RAG.** Faithfulness rises +0.116 with correctness and abstention unchanged. The one false abstention (`rec-34` EN, "which SKUs are reviewed weekly?": the answer gives the rule and says the context lists no specific SKUs) is defensible.

## Decision

- **The suites are fit for regression testing.** Each detects a change in its own component above noise, and the split makes the other suite immune by construction. A change that moves both, like chunking, is an indexing change.
- **Keep fixed 400/80 chunking:** recursive 300 loses passages and context with no gain in ranking.
- **Generator prompt for document-only RAG: `solo_documentos`.** The assistant's prompt stays for the integrated assistant (week 10), where `[SQL]` is real.
- **Unanswerable set:** 10 questions per language detect an assistant that invents systematically, but not one that does it 1 time in 20. More unanswerable questions would be needed to measure small rates.

## Cost

| Item | Cost |
|---|---|
| Reranking (repetition and rec300) | $0.1181 |
| gen_repeticion | $0.1533 |
| sin_solo_contexto | $0.1526 |
| solo_documentos | $0.1403 |
| rec300 | $0.1472 |
| **Total** | **$0.711** (estimate $0.82) |

The first run stopped with `Event loop is closed` during the last variant; the rerun resumed from the cache (57 missing evaluations plus 1 missing score).

## Limitations

- One run per variant, with one repetition per suite as the noise estimate.
- The "only context" test is confounded with the `[SQL]` instruction; it is separated by the direct comparison, not by a dedicated variant.
- 20 unanswerable questions in total.
