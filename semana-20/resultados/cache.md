# Week 20, activity 3: prompt caching

**Status: offline part done ($0); the live run waits for Manuel's OK.** Design: [ADR 0014](../../semana-19/arquitectura/adr/0014-prompt-caching.md).

| What | File |
|---|---|
| Measurement (step 1) | [`cache_medicion.json`](cache_medicion.json), from [`cache/medir.py`](../cache/medir.py) |
| Prediction (step 3), committed before the run | [`cache_prediccion.json`](cache_prediccion.json), from [`cache/prediccion.py`](../cache/prediccion.py) and quotation v3 ([`costos/modelo.py`](../../semana-19/costos/modelo.py)) |
| Run (step 4) | `cache/` (raw), `cache_detalle.jsonl`, `cache_comparacion.json`: pending |

## 1. Measurement: the cacheable prefix per step

The source is the corrected run's saved spans (`corrida_corregida/crudo_eval.json`, 2026-11-23): 20 tasks and 2 warm-ups.

**How tokens are counted.** It is an estimate.
- The repository has no Haiku 4.5 tokenizer, and the spans hold tokens per task, not per call.
- Each task gets its own characters-per-token ratio, fitted so that its rebuilt calls sum to its real input tokens.
- The margin is the spread of those ratios: 2.70 to 3.57, median 2.94.
- The details are in the docstring of `cache/medir.py`.

| Item | Value |
|---|---|
| Fixed prefix: 6 tool definitions and the system prompt, as the agent sends them to Converse | 7,825 characters |
| The same, in tokens | 2,664 at the median ratio; 2,898 at the lowest ratio (the upper bound) |
| Haiku 4.5 minimum per cache point (cumulative) | 4,096 |
| A point on the system prompt or the tools caches anything | **no**: under the minimum, even at the upper bound (test `test_el_prefijo_fijo_no_alcanza_el_minimo_de_haiku_45_ni_en_la_cota_alta`) |
| The system prompt sent | week 13's `SISTEMA`, equal to the Prompt Management English version with its variable rendered (tested) |
| First call's input | 2,681 to 3,140 tokens |
| The call where the prefix reaches 4,096 | call 2 in 13 tasks; call 3 in 2; call 4 in 1; never in 4 (a01 and n01, in both languages, 2 or 3 calls) |
| Time per call | median 4.17 s, maximum 16.72 s (the cold warm-up) |
| Time between queries | median 0.92 s, maximum 6.76 s |

`sistema` and `historial+sistema` therefore cache nothing more than `historial` does on Haiku 4.5. A test prices both and gets the same tokens (`test_el_punto_del_sistema_no_cachea_nada_en_haiku_45`).

## 2. Design (ADR 0014, summary)

- **Where the points go: `CACHE_PROMPT=historial`.**
  - A point goes at the end of the history from the second call on, plus one where the previous call put its point. That uses 2 of the 4 points, and none on the first call.
  - Each call reads the previous call's prefix and writes only what it added.
- **TTL: 5 minutes.**
  - A query's calls are seconds apart.
  - No two queries share a cached prefix, so the 1-hour TTL (writes at 2×) would only cost more.
- **The security boundary.** The cached prefix holds the tools and the system prompt, which are the same for every user, and the query's own history. That history contains the query's model-generated `toolUseId`s, so no other query can match it. The first call (system, tools, question) is never cached. This is T3.7 in the threat model.
- **The budget.** It counts cache tokens by their dollar weight: a read is 0.1 of an input token, a write 1.25.
- **Cost.** The span and EMF cost add the cache tokens at their prices.
- **Default.** Off. The run deploys with `CACHE_PROMPT=historial`.
- **What the docs do not say** (read 2026-11-25), so the run measures it:
  - whether caching works through an application inference profile;
  - whether the Guardrail re-evaluates cached content.

## 3. Prediction (quotation v3), before the run

Each measured call is priced with `cache_por_paso` (ADR 0014's rule). Without the cache, the model reproduces the corrected run exactly: 0.927825 USD, median 0.034076.

| Scenario | Hit probability | Median per task (USD) | p95 | 20 tasks | Saving |
|---|---|---|---|---|---|
| Corrected run (real, no cache) | — | 0.034076 | 0.106158 | 0.927825 | — |
| Optimistic (quotation v3's central) | 1 | 0.021740 | 0.046182 | 0.510544 | 45.0% |
| Pessimistic (uniform over the 3 Regions of the `us.` profile) | 1/3 | 0.033436 | 0.098515 | 0.892078 | 3.9% |
| Worst (no call reads) | 0 | 0.039846 | 0.128702 | 1.082845 | −16.7% |

- **Break-even:** a hit probability of 0.27.
- **Tokens in the optimistic case:** 93,166 uncached, 452,412 read and 111,299 written, for the 20 tasks.
- **TTL of 1 hour, optimistic:** 0.602366 (35.1%).
- **Latency:** N. The docs give no figure.
- **With the warm-up (22 tasks):** 0.565418 (optimistic) to 1.174799 (worst). The run's cap is 1.50 USD.

## 4. Live run

Pending Manuel's OK to the estimate.

## 5. Predicted vs real

Pending.

## 6. Cost Explorer

Pending: one call, the day after the run.

## 7. Conclusion

Pending.
