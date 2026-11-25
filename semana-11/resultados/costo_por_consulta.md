# Activity 7: cost and latency per query

Script: `experimentos/costo_por_consulta.py` (run on 2026-10-27). Output: `costo_por_consulta_salida.txt`; per-query cache: `costo_por_consulta_cache.json`.

The pipeline is the one decided in activities 2 to 6:
- **Retrieval:** bge-m3 (local), pgvector with the tenant and role filter (top 20) and Haiku 5.5 reranking.
- **Generation:** Haiku 5.5 `medium` on the top 5, with the `solo_documentos` prompt.
- **Evaluation:** the generation suite, with Haiku 5.5 `low` as judge.

It ran on the 150 questions of the gold set (65 answerable and 10 unanswerable per language). Tokens are the ones the API reports on each call. Prices come from `semana-07/prices.json`: Haiku 5.5 costs $0.10 per million input tokens and $0.50 per million output tokens.

## Cost and latency per stage (means per query)

| Stage | Input tokens | Output tokens | USD per query | p50 (s) | p95 (s) | Note |
|---|---|---|---|---|---|---|
| Retrieval: embedding (bge-m3) | 0 | 0 | $0.00000 | 0.05 | 0.05 | local, no API cost |
| Retrieval: pgvector search | 0 | 0 | $0.00000 | 0.00 | 0.00 | top 20 with filter |
| Retrieval: reranking (Haiku) | 3,350 | 316 | $0.00049 | 2.41 | 4.05 | 20 candidates |
| **Retrieval total** | 3,350 | 316 | **$0.00049** | **2.46** | **4.11** | |
| **Generation** (Haiku `medium`) | 1,023 | 210 | **$0.00021** | **1.58** | **2.78** | top 5, `solo_documentos` prompt |
| **Answer to the user** (retrieval + generation) | 4,373 | 526 | **$0.00070** | **4.18** | **6.23** | what production pays |
| **Evaluation**, answerable (4 metrics) | 9,056 | 1,007 | **$0.00141** | **17.17** | **26.73** | 7.1 judge calls |
| **Evaluation**, unanswerable (abstention) | 363 | 19 | **$0.00005** | **0.75** | **1.21** | 1 call |

### Evaluation latency per metric (answerable)

| Metric | p50 (s) | p95 (s) |
|---|---|---|
| faithfulness (RAGAS) | 5.61 | 8.88 |
| answer relevancy (RAGAS) | 8.70 | 16.45 |
| correctness (custom judge) | 0.97 | 3.47 |
| abstention class | 0.81 | 2.03 |

## Cost of evaluating each full suite once (one CI run)

| Suite | What it includes | Cost |
|---|---|---|
| Retrieval, exact metrics | 130 answerable queries: embedding, search and reranking | $0.064 |
| Retrieval with RAGAS (context precision and recall) | the above plus the judge ($0.00157 per query, activity 2) | $0.268 |
| Generation | 150 answers on fixed contexts, plus their evaluation | $0.215 |
| **Both suites, exact metrics in retrieval** | | **$0.279** |
| Both suites, RAGAS also in retrieval | | $0.483 |

## Reading

- **Production cost:**
  - An answer costs $0.0007, about 1,400 queries per dollar.
  - Reranking is 70% of the cost and 58% of the median latency.
  - Embedding and search cost nothing and take under 0.1 s.
- **Evaluating costs more than answering:**
  - Evaluating an answerable query costs twice as much as answering it ($0.00141 vs $0.00070).
  - It takes about 7 judge calls. RAGAS splits the answer into claims and verifies each one, and answer relevancy generates questions.
  - The two RAGAS metrics account for most of the evaluation latency.
- **CI:**
  - Both suites cost $0.28 per run. Adding RAGAS to retrieval almost doubles that ($0.48).
  - Reranking is already detected by exact metrics (recall@3 and AP@5, activity 2). So activity 8 can use exact metrics in retrieval and the full 150 questions in generation, with no subset.
  - If cost ever matters, the cut with the most effect is in the generation evaluation, not in retrieval.
- **How latencies were measured:**
  - Retrieval ran sequentially, so its latency is that of a single query.
  - Generation ran 4 queries in parallel, and evaluation 8 queries in parallel, with metrics in series within each query. Their latencies include API queuing at that concurrency.

## Runs

- **Run 1** (`costo_por_consulta_salida_corrida1.txt`): the local network failed.
  - 33 metrics failed on 18 queries (connection errors, timeouts and exhausted Instructor retries).
  - Stalls of up to 15 minutes inflated the evaluation p95 to 579 s.
  - 20 evaluations were dropped: the 18 with errors and 2 that took more than 60 s on a metric.
- **Final run:**
  - Only those 20 evaluations were measured again.
  - Retrieval, generation and the 130 clean evaluations came from the cache.
  - Judge errors: 0.
  - The tables combine the 150 measured queries from run 1 and the final run.
- **Actual spend for the activity:** ≈ $0.31 ($0.28 for run 1 and ≈ $0.03 for the re-evaluation).
