# Activity 3: baseline (in-house pipeline) with the week 11 suites

Script: [`evaluacion/suites.py`](../evaluacion/suites.py) `--backend propio` (run on 2026-10-28). The same evaluator runs every option of the week. Each option is only a retrieval backend; the gold set, generator, judge and metrics are shared.

Files:
- Summary used by every later comparison: [`propio_resumen.json`](propio_resumen.json).
- Detail per question: `propio_detalle.csv`.
- Rankings, answers and scores: `propio_cache.json`.
- Output: `propio_salida.txt`.

## Setup

| Item | Value |
|---|---|
| Gold set | Week 11 `eval_rag_{es,en}.jsonl`, unchanged: 65 answerable and 10 unanswerable questions per language |
| User | Tenant `alfa` with every role |
| Retrieval | bge-m3 (LM Studio), pgvector `semana10.chunks` (68 chunks, fixed 400/80), tenant and role filter inside the query, top 20, Haiku 5.5 reranking |
| Generator | Haiku 5.5 `medium` on the top 5, `solo_documentos` prompt (week 11 decision) |
| Judge | Haiku 5.5 `low`: faithfulness and answer relevancy (RAGAS 0.4.3), custom correctness judge, abstention class |
| Retrieval metrics | Exact relevance (a chunk of the gold document that contains the literal passage), plus `doc_recall@5`. `doc_recall@5` asks only whether the gold document is in the top 5, so it does not depend on where each service cuts its chunks |
| Failure attribution | **Retrieval** if a gold passage is missing from the top 5; **generation** otherwise (week 11, activity 5) |

## Retrieval suite (65 answerable questions per language)

| Lang | recall@1 | recall@3 | recall@5 | recall@10 | MRR | nDCG@10 | AP@5 | doc_recall@5 |
|---|---|---|---|---|---|---|---|---|
| ES | 0.892 | 0.992 | 1.000 | 1.000 | 0.949 | 0.962 | 0.949 | 1.000 |
| EN | 0.885 | 1.000 | 1.000 | 1.000 | 0.954 | 0.965 | 0.950 | 1.000 |

## Generation suite on what was retrieved (top 5, common generator)

| Lang | Correctness | faithfulness | answer relevancy | Citation precision | Citation coverage | False abstention | Correct abstention |
|---|---|---|---|---|---|---|---|
| ES | **1.000** | 0.849 | 0.879 | 0.600 | 0.985 | 0/65 | **10/10** |
| EN | **1.000** | 0.830 | 0.866 | 0.625 | 1.000 | 0/65 | **10/10** |

**Failures: 0 of 150.** Every answerable question is correct, and every unanswerable question is declined.

## Cost and latency per query

| Stage | USD per query | p50 (s) | p95 (s) |
|---|---|---|---|
| Retrieval (embedding, search, reranking) | $0.00049 | 2.31 | 3.84 |
| Generation | $0.00021 | 1.69 | 3.39 |

Reranking ran 4 queries in parallel and generation 8, so latencies include API queuing. Activity 7 measures latency for every option with the same client and the same concurrency.

## Reading

- **This is the reference for the week.** Retrieval reaches recall@5 = 1.000 in both languages, so the bar for the managed services is high:
  - on coverage, they can at most tie;
  - the comparison carries information in recall@1 and @3, MRR, nDCG@10 and AP@5, in `doc_recall@5`, and in the end-to-end generation metrics.
- **Consistent with week 11, within run-to-run noise:**
  - **Retrieval:** recall@1 was 0.862 in week 11, activity 2, and is 0.885 to 0.892 here; MRR went from 0.936 to 0.949 to 0.954. Same reranking, different run; week 11 measured reranking noise at about ±0.02 in MRR.
  - **Generation:** faithfulness is 0.849 / 0.830 here against 0.813 / 0.814 end to end in week 11, activity 5. That run used the week 10 assistant prompt; this one uses `solo_documentos`, which week 11 measured at +0.116 on fixed contexts.
- **Citation precision (0.60 / 0.63) is a lower bound**, as in week 11. The real top 5 holds several chunks of the same document, and the generator also cites neighbors that are relevant but do not hold the literal passage.
  - `rec-17` ES is correct but cites only the neighboring chunk; that is the single answer without a gold citation.
- **Faithfulness below 0.5 in 2 of 130 answers** (`rec-02` EN 0.0, `int-pdf-04` EN 0.4). Both are correct according to the correctness judge; this is the Haiku false-alarm pattern seen in week 11.

## Cost

| Item | Cost |
|---|---|
| Reranking (150 queries) | $0.073 |
| Generation (150 answers) | $0.032 |
| Evaluation (judge) | $0.134 |
| Smoke test (8 questions) | ≈ $0.01 |
| **Total** | **≈ $0.25** (estimate $0.25) |

- Duration of the full run: 380 s.
- Judge scores missing: 0. Failed reranking: 0.
