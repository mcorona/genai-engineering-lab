# Activity 4: generation suite

Script: `experimentos/suite_generacion.py` (run on 2026-10-27). Frozen contexts: `contextos_generacion.json`. Output: `suite_generacion_salida.txt`; detail per question: `suite_generacion_detalle.csv`; answers and scores: `suite_generacion_cache.json`.

## Design

- **Questions:** all 75 per language of `datasets/eval_rag_{es,en}.jsonl`: 65 answerable, 10 unanswerable.
- **Fixed context**, independent of the retriever, frozen before generating, order shuffled with seed 11:
  - **Answerable:** one chunk per gold passage, plus 2 to 4 **hard distractors**: random among the 10 best-ranked chunks (activity 2, adopted pipeline) that contain no gold passage, so they are from the same corpus and similar to the question.
  - **Unanswerable:** 3 to 5 chunks drawn from the 10 most similar to the question.
- **Generator:** the week 10 assistant's: Haiku 5.5 `medium`, its system prompt, chunks as `[D1]..[Dn]`.
- **Judge:** Haiku 5.5 `low` (activity 3 decision).
- **Metrics:**
  - faithfulness and answer relevancy (RAGAS);
  - correctness against the reference (custom judge);
  - citation precision: cited chunks that contain the gold passage, over all cited chunks;
  - citation coverage: answers that cite a gold chunk;
  - abstention: a judge classifies each answer as "abstains" or "answers". This gives the correct abstention rate and the invented answer rate on unanswerable questions, and the false abstention rate on answerable ones.

## Results

| Lang | Type | n | faithfulness | answer relevancy | correctness (custom judge) | citation precision | citation coverage | false abstention |
|---|---|---|---|---|---|---|---|---|
| ES | base | 50 | 0.667 | 0.884 | 1.000 | 0.639 (83) | 1.000 | 0/50 |
| ES | non-text | 15 | 0.717 | 0.909 | 1.000 | 0.882 (17) | 1.000 | 0/15 |
| ES | all | 65 | **0.679** | 0.890 | **1.000** | 0.680 (100) | 1.000 | 0/65 |
| EN | base | 50 | 0.840 | 0.879 | 1.000 | 0.743 (70) | 1.000 | 0/50 |
| EN | non-text | 15 | 0.688 | 0.798 | 1.000 | 0.938 (16) | 1.000 | 0/15 |
| EN | all | 65 | **0.805** | 0.860 | **1.000** | 0.779 (86) | 1.000 | 0/65 |

| Unanswerable | n | Correct abstention | Invented answer |
|---|---|---|---|
| ES | 10 | **10/10** | 0/10 |
| EN | 10 | **10/10** | 0/10 |

| Chunks in context | n | faithfulness | correctness | citation precision |
|---|---|---|---|---|
| 3 | 34 | 0.703 | 1.000 | 0.791 |
| 4 | 53 | 0.721 | 1.000 | 0.761 |
| 5 | 40 | 0.788 | 1.000 | 0.689 |
| 6 | 3 | 0.930 | 1.000 | 0.455 |

Generation: $0.0305 for 150 answers ($0.00020 per query), p50 latency 2.1 s. Evaluation: $0.1369 (691 judge calls), about $0.0009 per answer. No missing judge scores.

## Reading

- **Every answer is correct and every unanswerable question was declined.** Correctness is 1.000 in both languages. The generator abstained in all 20 unanswerable questions, even with 3 to 5 similar chunks in front of it, and never abstained on an answerable one. Every answer cites the chunk that holds the passage.
- **Faithfulness is low because the generator adds meta-commentary, not because it invents data.** 66 of 150 answers add sentences such as "No SQL result was provided" or "the passage is cut at that point". The system prompt is the integrated assistant's, which tells the model to cite `[SQL]`, so with documents only it explains that there is no SQL. RAGAS counts each of those sentences as a claim the context does not support:
  - mean faithfulness is 0.634 for answers that mention SQL (n = 50) and 0.809 for those that do not (n = 80);
  - Spanish answers do it more often (45 vs 21), which explains most of the ES/EN gap (0.679 vs 0.805);
  - read one by one, the answers below 0.5 have their main fact right and cited (for example, `rec-37`: "12,000 pallet positions [D2]. No SQL result was included…").
- **Haiku false alarms, again:** `rec-01` and `rec-02` ES score faithfulness 0.00, although every sentence comes from the cited chunk (the 30-day return deadline; protective equipment not accepted once opened). This matches the Haiku false alarm seen in activity 3. Individual scores are noisy; averages and comparisons between configurations are what the metric is for.
- **Citation precision (0.68 ES, 0.78 EN) is a lower bound.** The answers cite extra chunks that are relevant but do not contain the exact gold passage: for example, a second chunk of the same policy, or the freight table that also says "2 days" (`rec-25`, the same evidence-outside-the-gold-set case as activity 2). Non-text questions, with a single exact figure, reach 0.88 to 0.94.
- **More distractors did not hurt** correctness or faithfulness (3 to 5 chunks). Citation precision drops as chunks are added, because there is more to cite.

## Decision

- **Generation suite metrics:** correctness (custom judge) and abstention as the primary pass/fail signals; faithfulness as a signal for unsupported content, read together with the meta-commentary caveat; citation precision as a lower bound.
- **Generator prompt for document-only RAG:** the integrated assistant's prompt causes the "no SQL" meta-commentary. Activity 6, which tests the suite's sensitivity to prompt changes, will measure a documents-only prompt; if faithfulness rises with correctness unchanged, that prompt is the one to use when there is no SQL tool.

## Limitations

- One run; generator and judge are not deterministic.
- Faithfulness with Haiku has false alarms (2 clear cases of 130 here, 1 of 40 controls in activity 3).
- The abstention test has 10 questions per language; all were outside the corpus by construction. A partly answerable question (half of the answer in the corpus) is not covered.
- Hard distractors come from the same retriever ranking, so they are the chunks the real pipeline would show; random distractors would make the task easier.
