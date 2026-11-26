# Week 20, activity 3: prompt caching

**Status: run done on 2026-11-26 (0.547294 USD of model for the 22 tasks, cap 1.50); the Cost Explorer call is the
next day's.** Design: [ADR 0014](../../semana-19/arquitectura/adr/0014-prompt-caching.md).

| What | File |
|---|---|
| Measurement (step 1) | [`cache_medicion.json`](cache_medicion.json), from [`cache/medir.py`](../cache/medir.py) |
| Prediction (step 3), committed before the run | [`cache_prediccion.json`](cache_prediccion.json), from [`cache/prediccion.py`](../cache/prediccion.py) and quotation v3 ([`costos/modelo.py`](../../semana-19/costos/modelo.py)) |
| Run (step 4), 2026-11-26 | [`cache/crudo_eval.json`](cache/crudo_eval.json) (raw), [`cache_detalle.jsonl`](cache_detalle.jsonl) (per task and per model call), [`cache_comparacion.json`](cache_comparacion.json), from [`cache/corrida.py`](../cache/corrida.py) |

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

## 4. Live run (2026-11-26)

**How it ran.**
- From scratch: `desplegar.sh --si` (control, bootstrap, base, datos, ia, the loader and the ingestion), then
  `--solo-control --si` (`BootstrapCreado=true`).
- Then computo with `CACHE_PROMPT=historial` and `PRESUPUESTO_TAREA=techo_semana20` (`cdk diff` first: 64 resources
  to create, none changed). Deploy times are in `semana-19/resultados/tiempos_despliegue.jsonl`.
- Before the first task, the script checked the agent's environment (`CACHE_TTL` absent, so 5 minutes) and that the
  deployed zip carries the repository's 6 cache files (#358). The package had been rebuilt with `paquete_agente.py`.
- 2 warm-up tasks and the 20 CI golden tasks, through the public API with real Cognito tokens, as in the corrected run.

**Cost and tokens** (`cache/crudo_eval.json` `resumen.costo`, 22 tasks):

| | Corrected run (2026-11-23) | Cache run (2026-11-26) |
|---|---|---|
| Model USD, 22 tasks | 1.008147 | **0.547294** (cap 1.50) |
| Uncached input tokens | 708,087 | 103,487 |
| Cache read tokens | 0 | 373,753 |
| Cache write tokens | 0 | 125,006 |
| Output tokens | 41,682 | 40,084 |

`tokens_por_tarea` (6,526.0 here, 34,080.4 before) counts uncached input and output only, so it is not comparable
across the two runs; the four token rows above are.

**The 20 main tasks** (`cache_comparacion.json`):

| | Corrected run | Cache run | Change |
|---|---|---|---|
| Total USD | 0.927825 | **0.505822** | −45.5% |
| Median per task | 0.034076 | **0.022060** | −35.3% |
| p95 per task | 0.106158 | **0.050441** | −52.5% |
| Success | 16/20 | 17/20 | +1 |
| Tasks cut by the budget | 1 | 1 (r05-en, 12 calls) | — |
| Trajectory ok | 8/20, mean 0.912 | 11/20, mean 0.924 | — |

**Hits per call.** A call can read when the call before it wrote. All 55 such calls read: a hit rate of **1.0**,
against a predicted break-even of 0.27.

| Call | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|
| Could read / read | 11 / 11 | 13 / 13 | 14 / 14 | 7 / 7 | 2 / 2 | 2 / 2 | 2 / 2 | 2 / 2 | 1 / 1 | 1 / 1 |

- Call 1 never carries a point, and call 2 only writes, so hits start at call 3. No first call has cache tokens (the
  boundary of ADR 0014: the prefix two users could share is never cached).
- Four tasks have no call that could read: a01-es, a01-en, n01-es (2 calls each) and v01-en (4 calls). Their prefix
  stayed under the minimum or was written only on the last call. Step 1 measured the same short tasks.
- **What the docs did not say, now measured:** caching works through the application inference profile
  `semana19-agente` and with the Guardrail on. Converse returns no Region, so `region` stays null; with every possible
  call a hit, no call was served away from the server that wrote.

**Latency** (`cache_detalle.jsonl`, the chat spans' durations):

| | Corrected run | Cache run |
|---|---|---|
| Per model call, median (104 calls) | not recorded per call | 2.93 s (max 10.69 s) |
| First call, median of the tasks | not recorded per call | 2.49 s |
| Later calls, median of the tasks' medians | not recorded per call | 2.91 s |
| Task latency over calls, median (same method, `cache/medir.py`) | 4.11 s | 4.08 s |
| Task latency, warm: p50 / p95 | 21.57 s / 45.02 s | 19.41 s / 48.70 s |
| Task latency, cold | 2 tasks, p50 50.16 s | not classified: both warm-up tasks came out `desconocido` |

- The corrected run recorded no per-call durations (the chat spans came with #356), so the like-for-like comparison is
  the task latency over its calls: 4.11 s against 4.08 s. That includes tool time and the API's polling, so it does not
  isolate the model call, and it shows no latency gain from the cache at this prefix size (3,000 to 12,000 tokens).
- The first call (never cached) and the later calls (cached) have about the same median, 2.49 s against 2.91 s.
- Cold against warm with the cache is not measured: the run's warm-up tasks were not classified. It stays N.

**Week 10's rule** (`cache/crudo_eval.json` `resumen.comparacion`), against week 17's local baseline:

| | Base | Cache run | Threshold | Regression |
|---|---|---|---|---|
| es | 1.0 | 0.9 | 0.9 | no |
| en | 1.0 | 0.8 | 0.9 | yes |
| Total | 1.0 | 0.85 | 0.95 | yes |

- It is still a regression, as in the corrected run, which Manuel accepted as week 20's baseline without passing.
- Failures: c02-es, r05-en (cut by the budget) and c06-en. c02-en and r05-es now pass; c06-en passed before.
  With 10 tasks per language that is inside the noise (95% interval of the total: 0.64 to 0.948), so no change of
  quality is attributed to the cache. The cache does not change the prompt or what the model sees (tested), only
  where the prefix is read from.
- The warm-up's s02-es has `spans_modelo_validos: false`: it ran next to s01-es, and the two tasks' chat spans mixed.
  Its per-call columns are null (#358); the cost and the main tasks are not affected.

**Teardown:** `destruir.sh --si --todo`, then the inventory with the read-only role (result in §6 with Cost Explorer).

## 5. Predicted vs real

Quotation v3's central scenario (optimistic, p = 1), committed before the run (#357):

| | Predicted | Real | Error |
|---|---|---|---|
| Total, 20 tasks | 0.510544 | 0.505822 | **−0.9%** |
| Median per task | 0.021740 | 0.022060 | +1.5% |
| p95 per task | 0.046182 | 0.050441 | +9.2% |
| Hit rate | 1 (scenario) | 1.0 (55 / 55) | — |
| Latency | N | see §4 | — |

- **Within ±20%: quotation v3 is kept as it is**, with no v4.
- Per task the error runs from −54.9% (r05-es: 3 calls, against 11 in the corrected run) to +149.4% (c02-en: 10
  calls, against 6). The prediction prices the corrected run's calls; the model takes a different number of calls
  each run, and that, not the cache, sets the per-task error. Over 20 tasks the differences cancel to −0.9%.
- The hit rate was the one unknown; it came out at the optimistic end. The pessimistic (1/3) and worst (0) scenarios
  stay in the quotation as the bounds for a busier hour ("at times of high demand… increased cache writes", prompt-caching
  docs, read 2026-11-25).

## 6. Cost Explorer and the teardown

Pending: the inventory after `destruir.sh`, and one `GetCostAndUsage` call for 2026-11-26 the next day (0.01 USD,
Manuel's OK given on 2026-11-26).

## 7. Conclusion

- **On Haiku 4.5, a cache point at the end of the history cuts the model cost of the 20 tasks by 45.5%** (0.927825 to
  0.505822 USD) and the p95 per task by 52.5%. Every call that could read did.
- The prediction made before the run was right to 0.9% on the total.
- No latency gain is visible at these prefix sizes. Success (17/20) and week 10's verdict (regression, as before) are
  the corrected run's within the noise.
- The default stays off (`CACHE_PROMPT = "off"`, ADR 0014): activity 9 decides the combined default with the other
  activities' measurements. The cap stays 0.12 USD / 100,000 tokens until then.
