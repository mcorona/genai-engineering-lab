# Week 11: RAG evaluation (recall@k, faithfulness, answer relevance with RAGAS; cost per query)

> Spanish names (folders, files, JSON keys, flags, stack names, status values) are explained in the [glossary](../docs/glossary.md). The documentation is in English. Spanish data and recorded results stay as they are: the README in each data or results folder describes them in English.

Status: closed (2026-10-27). Phase 3 criterion 10 verified.

Goal: evaluate retrieval and generation with separate suites, so a regression can be traced to the stage that caused it, and check that each metric detects known failures before relying on it.

## Setup

- RAGAS installed in the repo `.venv` with `uv pip install "ragas==0.4.3" "langchain-community==0.4.1" anthropic`. Versions recorded on 2026-10-27: ragas 0.4.3, langchain-community 0.4.1, langchain-core 1.7.0, instructor 1.17.0, anthropic 1.15.0, openai 3.3.0.
  - The current `ragas` release imports `langchain_community.chat_models.vertexai`, which the latest `langchain-community` removed. Pin `langchain-community==0.4.1`.
  - The judge is Claude through `llm_factory(..., provider="anthropic")`. RAGAS sends `temperature` and `top_p` by default; both are removed because current Claude models do not accept the pair.
  - Embeddings use bge-m3 in LM Studio through its OpenAI-compatible endpoint.
- Index: `semana10.chunks` from week 10, activity 7 (30 documents, 68 chunks, tenant `alfa`). Check it with `experimentos/verificar_entorno.py`.

## Setup check (2026-10-27)

`experimentos/verificar_ragas.py`, judge Haiku 5.5 `low`, embeddings bge-m3. Four cases with a known outcome, built from a verbatim passage of `semana-08/corpus/devoluciones.md`:

| Case | faithfulness | answer_relevancy | context_recall |
|---|---|---|---|
| Faithful answer | 1.00 | 0.94 | 1.00 |
| Changed figure (45 instead of 30 days) | **0.00** | 0.74 | 1.00 |
| True but off-topic answer | 1.00 | **0.58** | 1.00 |
| Wrong context, answer says "not in context" | 0.00 | 0.00 | **0.00** |

Every metric moved in the expected direction. Cost: 24 judge calls, 39,090 input and 2,454 output tokens, $0.0051.

Two readings to carry into activity 3:
- A correct abstention ("not in the context") scores faithfulness 0 and answer relevance 0: RAGAS finds no supported claim and treats the answer as noncommittal. Unanswerable questions need their own metric (abstention rate), not RAGAS.
- answer_relevancy also dropped for the changed figure (0.94 → 0.74), so it is not purely a topic measure.

`experimentos/verificar_entorno.py`: LM Studio serves `text-embedding-bge-m3` (1024 dimensions). `semana10.chunks` had been left by the week 10 security run (alfa 36 documents, 79 chunks; beta 10, 33; six injected documents). It was reindexed to the activity 7 index: 30 documents, 68 chunks, tenant `alfa` only.

## 1. Evaluation gold set (frozen)

`datasets/eval_rag_{es,en}.jsonl`, built by `datasets/construir_eval_rag.py`. 75 questions per language:

| Type | Per language | `gold` | `referencia` |
|---|---|---|---|
| Base (weeks 8/9) | 50 | Verbatim passages | Written by Haiku 5.5 `low` from the passage only, with the source document to interpret it (for example, a table header) |
| Non-text (week 10: 5 PDF, 5 OCR, 5 image) | 15 | Source document and exact answer | Same, with the source document and the exact answer |
| Unanswerable | 10 | empty | "The information is not in the documents." |

The 15 week 10 document questions come from the same 50 base questions (field `origen`), so they are not added twice. The unanswerable questions stay in the domain (vacation days, cargo insurer, accounting software, late-payment interest, CEO, remote work, year-end bonus, uniforms, factoring, carrier strike); the builder checks that their key terms do not appear in the week 8 corpus or the week 10 sources.

Automatic checks, all passing: every figure in a reference appears in the passage (or the document line that contains it), the source or the question; non-text references contain the exact answer; no answerable question has a reference that says the answer is missing.

| Run | What happened | Cost |
|---|---|---|
| v1 (passage only) | Two references said the answer was missing: `rec-07` read a table row without its header as a salary range, and `rec-23` EN did not see that the passage is the escalation threshold. The figure check also flagged 5 figures that came from the question | $0.0073 |
| v2 (passage + source document for context) | All checks pass; v1 answers are kept in the cache as evidence | $0.0117 |

Manual review of 20 references (10 per language, seed 11): **20/20 correct**; two add a detail from the same source line, verified ([`revision_referencias.md`](resultados/revision_referencias.md)).

## 2. Retrieval suite

[`experimentos/suite_recuperacion.py`](experimentos/suite_recuperacion.py) → [`resultados/suite_recuperacion.md`](resultados/suite_recuperacion.md). The suite covers the 65 answerable questions per language. It retrieves chunks but never calls the answer model.

| Config | Lang | recall@1 | recall@3 | recall@5 | MRR | nDCG@10 | context precision | context recall |
|---|---|---|---|---|---|---|---|---|
| base (vector + filter) | ES | 0.769 | 0.962 | 1.000 | 0.877 | 0.905 | 0.896 | 1.000 |
| base (vector + filter) | EN | 0.738 | 0.908 | 1.000 | 0.851 | 0.888 | 0.869 | 1.000 |
| adopted (+ Haiku reranking) | ES | 0.862 | 1.000 | 1.000 | 0.936 | 0.952 | 0.972 | 1.000 |
| adopted (+ Haiku reranking) | EN | 0.862 | 1.000 | 1.000 | 0.936 | 0.952 | 0.959 | 1.000 |

- **The suite tells the two configurations apart with ranking metrics.**
  - Reranking minus base, AP@5: **+0.070 [+0.008, +0.137] ES** and **+0.095 [+0.018, +0.171] EN**, with 95% bootstrap intervals.
  - recall@3: +0.038 ES and +0.092 EN. Context precision: +0.078 ES and +0.090 EN.
  - recall@5 and context recall do not separate the configurations: both reach 1.000 (ceiling effect).
- **Custom metrics vs. RAGAS:**
  - Context recall agrees with exact recall@5 on 259 of 259 queries.
  - RAGAS context precision is the AP@5 formula with a judge (Pearson 0.84 against AP@5 on the base configuration). It is a ranking metric, not the share of relevant chunks.
  - RAGAS scores higher when another chunk also holds the answer. That reveals evidence the gold set does not list (`rec-25`).

## 3. Meta-evaluation of the generation metrics

[`resultados/meta_evaluacion.md`](resultados/meta_evaluacion.md). Five rule-built answers per question, over 20 questions per language. Haiku 5.5 `low` and Sonnet 5.5 `low` were both tried as judges.

- **Faithfulness detects changed figures and invented claims.** Haiku: −0.837 and −0.587 against the control, below the control in 96% and 99% of pairs.
- **Answer relevancy detects off-topic and evasive answers** (−0.521 and −0.920). It does not notice a changed figure.
- **The custom correctness judge catches wrong figures but accepts 53% of invented additions with Haiku**, so it does not replace faithfulness.
- **Decision: Haiku 5.5 `low` as judge.** Both judges met all four expected detections and the control, and Haiku costs about 14 times less.

## 4. Generation suite

[`resultados/suite_generacion.md`](resultados/suite_generacion.md). Fixed contexts: the gold chunks plus 2 to 4 hard distractors, frozen in `contextos_generacion.json`. The suite does not depend on the retriever.

- **Correctness and abstention:**
  - Correctness is 1.000 in both languages.
  - Correct abstention is 20/20 on unanswerable questions, and there are 0 false abstentions on answerable ones.
  - Every answer cites the chunk that holds the passage.
- **Faithfulness (0.679 ES, 0.805 EN) is lowered by meta-commentary, not by invented data.**
  - The week 10 assistant prompt asks for `[SQL]` citations, so with documents only the model adds sentences such as "no SQL result was provided".
  - Answers with such sentences average 0.634; answers without them average 0.809.
- **Citation precision (0.68 ES, 0.78 EN) is a lower bound.** Answers also cite relevant chunks that do not contain the exact gold passage.

## 5. End to end and failure attribution

[`resultados/extremo_a_extremo.md`](resultados/extremo_a_extremo.md). Each wrong answer is attributed to **retrieval** if a gold passage did not reach the context, and to **generation** if every passage arrived and the answer still failed.

- **The adopted pipeline fails 1 of 150 questions**, and that failure is generation (`rec-22` ES). Correctness is 0.985 ES and 1.000 EN; correct abstention is 20/20.
- **The stress configuration** (no reranking, top 3) exercises the attribution. It produces 13 failures: 10 retrieval and 3 generation.
  - One of the generation failures, `rec-17`, is really a chunk boundary: the gold passage arrived, but its consequence sits in the next chunk.

## 6. Sensitivity of the suites

[`resultados/sensibilidad.md`](resultados/sensibilidad.md). One change at a time, each compared with a noise control (a repeated run without changes):

| Change | Retrieval suite | Generation suite |
|---|---|---|
| Remove reranking | moves (AP@5 −0.083, recall@3 −0.065) | does not move |
| Prompt without the "only context" rule | does not move | moves (faithfulness +0.111) |
| Recursive 300 chunking | moves (recall@5 −0.038) | moves (correctness −0.038) |
| `solo_documentos` prompt | does not move | faithfulness **+0.116**, correctness unchanged |

- Each suite moves only with the component it measures. A chunking change moves both suites, because it changes the index.
- **Adopted prompt for document-only RAG: `solo_documentos`.** Fixed 400/80 chunking stays.

## 7. Cost per query

[`resultados/costo_por_consulta.md`](resultados/costo_por_consulta.md). Per stage, averaged over the 150 questions:

| Stage | USD per query | p50 (s) | p95 (s) |
|---|---|---|---|
| Retrieval (bge-m3, pgvector, Haiku reranking of 20) | $0.00049 | 2.46 | 4.11 |
| Generation (Haiku `medium`, top 5) | $0.00021 | 1.58 | 2.78 |
| **Answer to the user** | **$0.00070** | **4.18** | **6.23** |
| Evaluation, answerable (4 metrics, 7.1 judge calls) | $0.00141 | 17.17 | 26.73 |
| Evaluation, unanswerable (abstention) | $0.00005 | 0.75 | 1.21 |

- **Evaluating an answer costs twice as much as producing it.**
- **Cost of evaluating each suite once:**
  - Both suites, with exact metrics in retrieval: **$0.279**.
  - With RAGAS context precision and recall also in retrieval: $0.483.

## 8. CI with thresholds

Workflow `eval-semana-11`, script [`ci/eval_ci.py`](ci/eval_ci.py), calibration in [`resultados/ci_calibracion.md`](resultados/ci_calibracion.md). It runs two separate jobs:

- **`semana11-recuperacion`:**
  - Rebuilds the index in the pgvector service and reranks with Haiku.
  - Thresholds per language: recall@3 and recall@5 at 0.95; MRR, nDCG@10 and AP@5 at 0.90.
  - Cost: $0.064.
- **`semana11-generacion`:**
  - Uses the fixed contexts, the `solo_documentos` prompt and the Haiku `low` judge, on all 150 questions. The cost is low enough that no subset is needed.
  - Thresholds per language: faithfulness 0.80 / 0.75 (ES / EN), answer relevancy 0.80 / 0.75, correctness 0.95, citation precision 0.65 / 0.70, no false abstention 0.95, correct abstention 0.90.
  - Cost: $0.16.

Thresholds follow the week 10 rule: the multiple of 0.05 just below (first CI value − max(0.03, 1/n)). CI uses `text-embedding-3-small`, so it is calibrated on its own first run.

Both jobs passed with thresholds on PR #57.

Both jobs run on every pull request and skip in seconds when `semana-11/**` is not touched. A required check therefore never blocks a PR from another week. Both checks are required by the `ProteccionRama` ruleset.

## Decisions

| Decision | Why | Activity |
|---|---|---|
| Separate retrieval and generation suites, with end to end only as a third view | A regression can be traced to its stage; each suite is immune to the other component by construction | 2, 4, 6 |
| Exact metrics (recall@k, MRR, nDCG@10, AP@5) as the main retrieval signal; RAGAS context metrics as a complement | Free, deterministic, they detect reranking; RAGAS costs 3 to 4 times the reranking | 2, 7 |
| Judge: Haiku 5.5 `low` | Meets every meta-evaluation criterion at about 1/14 of Sonnet's cost | 3 |
| Generation suite: correctness and abstention as pass/fail; faithfulness for unsupported content; citation precision as a lower bound | Correctness alone misses invented additions; faithfulness alone penalizes correct abstentions | 3, 4 |
| `solo_documentos` prompt for document-only RAG | +0.116 faithfulness, correctness unchanged | 6 |
| Keep fixed 400/80 chunking | Recursive 300 loses passages and context | 6 |
| Full generation suite in CI, no subset | $0.22 per PR for both suites | 7, 8 |

## Failed cases

| Case | Stage | What happened |
|---|---|---|
| `rec-22` ES (adopted pipeline) | generation | Mixed the urgent-purchase rule ("regardless of amount") with the general approval table from another chunk |
| `rec-17` ES/EN (stress) | chunking | The gold passage arrived, but the consequence sits in the next chunk; attributed to generation by the rule |
| `int-imagen-12/13` (recursive 300) | chunking | The chunk keeps the figure but loses the chart title with the period; the generator declines to confirm it |
| `rec-01`, `rec-02` ES; `int-ocr-06` EN | judge | Haiku faithfulness 0.0 on answers that are fully supported (false alarms) |
| `rec-49` | judge | A changed threshold ($10,000 → $15,000) got faithfulness 1.0 from both judges |
| `nr-07` ES (prompt without "only context") | generation | Said the bonus is not in the documents, then added outside knowledge (Federal Labor Law); 1 of 20 is below what 10 unanswerable questions per language can detect |
| `rec-25` | gold set | The freight table also answers the question; exact metrics undercount, RAGAS context precision catches it |

## Corrections during the week

- **References v1** read a table row without its header (`rec-07`) and missed an escalation threshold (`rec-23` EN). v2 gives the source document as context.
- **Sonnet as judge:**
  - Sonnet 5.5 rejects forced `tool_choice`, so it uses Instructor JSON mode.
  - The RAGAS disk cache key ignores the model: Sonnet first received Haiku's cached scores. Each judge now has its own cache.
- **Mac network failures** (Python `connect` errno 12, then stalled calls):
  - In activities 3 and 7, the affected scores were dropped and measured again.
  - In activity 7 the first run is kept as evidence, because its p95 was inflated by stalls.

## Cost

| Item | Cost |
|---|---|
| Setup and gold set (references v1 and v2) | $0.024 |
| Retrieval suite (reranking + RAGAS) | $0.471 |
| Meta-evaluation (two judges, two runs) | $2.464 |
| Generation suite | $0.168 |
| End to end | $0.338 |
| Sensitivity | $0.711 |
| Cost per query (two runs) | ≈ $0.31 |
| CI: smoke test, calibration and threshold runs | ≈ $0.46 |
| **Total** | **≈ $4.95** |

## Limitations

- **Synthetic corpus, small and easy for retrieval.** The adopted pipeline puts every gold passage in the top 5, so recall@5 cannot detect a regression that stays inside the top 5. Ranking metrics carry the signal.
- **Unanswerable questions: 10 per language.** They detect an assistant that invents systematically, not one that invents 1 answer in 20. Partly answerable questions are not covered.
- **The judges are not deterministic.** Two CI runs of the same code moved:
  - citation precision ES from 0.728 to 0.684, leaving it 0.034 above its threshold;
  - faithfulness ES from 0.833 to 0.864;
  - MRR ES from 0.931 to 0.969.

  If a single metric fails with no change to its component, run the job once more before treating it as a regression.
- **Haiku faithfulness has false alarms.** Individual scores are noisy; means and paired comparisons are what the metric is for.
- **RAGAS penalizes correct abstentions** (faithfulness 0, relevancy 0). Unanswerable questions use an abstention judge instead.
- **Different embeddings in CI and locally.** CI uses `text-embedding-3-small`; local runs use bge-m3. CI thresholds are not comparable with local values.
- **Gold passages are literal.** A passage split across chunks, or evidence in another document, counts as a miss for the exact metrics.
