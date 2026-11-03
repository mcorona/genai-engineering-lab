# Activity 4: token and cost budgets

Every model call of the LegacyBridge agent now goes through a budget: per task, per session and per tenant per day, each in tokens and in USD.
The 84 tasks of week 13 were run with the budget on (real Claude Haiku 5.5, `low`, k = 1): **no task crossed its cap**, 74 of 84 succeeded,
2 tasks were stopped by the budget with a partial answer that says why, and the run cost $0.2344.

Files: `presupuestos/` (`estimacion.py`, `politica.py`, `almacen.py`, `agente_presupuestado.py`, `calibracion.py`, `correr_eval.py`,
`verificar_langfuse.py`), `tests/test_presupuestos.py` (36 tests, no API), and the evidence in `resultados/presupuestos_*`.

## Plan versus result

| Plan bullet | Result |
|---|---|
| A budget per task, per session and per tenant per day, in tokens and USD; a small store for the per-day budgets | ✅ `politica.py` (three scopes, two dimensions) and `almacen.py` (SQLite, WAL, integer nano-dollars). Reservations are made in one `BEGIN IMMEDIATE` transaction over every scope or none, so two tasks of a tenant can never both get the last dollar (8 threads, 500 trajectories and 8 concurrent tasks in the tests) |
| The loop checks before each model call with the upper estimate (whole previous prompt plus the maximum output) | ✅ `estimacion.py`: previous prompt + previous output + the new message at 1.5 characters per token, plus a 10 % margin. It never fell below the real prompt in 930 recorded calls (minimum ratio 1.096) nor in the 84 paid ones. The output is capped, not guessed: each call is sent with the largest `max_tokens` the tightest scope can pay for |
| At a budget: stop with a partial answer that says why | ✅ 2 in the paid run (`presupuesto_tarea`, `presupuesto_sesion`). The answer names the scope, the limit, the spend and the number of calls, in the task's language (templates, no model call) |
| Where a policy allows it, degrade to a cheaper model | ✅ `Politica.degradar` names the pairs (default: none, Haiku has no cheaper model). Tested on the scripted loop and in Langfuse (`degrada` scenario). It was **not** exercised by the paid run |
| Never retry silently | ✅ an API error releases its reservation and ends the task (`error`), with no second call. The only repetition is re-deciding a call that lost a reservation race, up to 3 times, with fresh numbers and never with another model or prompt |
| Each decision is a `gen_ai` span event with the spend and the limit | ✅ `gen_ai.budget.decision`, 13 numeric or fixed-vocabulary attributes, exactly one per decision in all 84 paid tasks, identical in the Collector's output file. ⚠️ Langfuse v4 does not show span events (finding 2) |
| Eval: the cost distribution of the 84 tasks sets each budget at a calibrated percentile | ✅ `calibracion.py`, table below |
| Then measure success, partial answers and cost with the budget on | ✅ table below |
| The spend never crosses the cap, in any task | ✅ largest task $0.005548 of $0.0063 and 42,915 of 46,000 tokens; largest session $0.0373 of $0.039; the day $0.2344 of $0.32; the store's totals equal the sum of the tasks; 0 reservations left. Also a 5,000-case property test of the policy |
| Cost ~$0.15, authorized first | ✅ authorized before the run with the real estimate. ⚠️ the plan's figure was low: 84 × the week 13 mean of $0.00286 is $0.24. Actual $0.2344 |

## Calibration (week 13, Haiku `low`, 252 runs: 84 tasks × 3)

| | p50 | p90 | p95 | p99 | max | mean |
|---|---|---|---|---|---|---|
| USD per run | 0.002593 | 0.004680 | 0.005237 | 0.006244 | 0.007772 | 0.002856 |
| Tokens per run | 20,996 | 34,842 | 37,971 | 45,624 | 60,308 | 21,665 |

What each task cap would have done to those 252 recorded runs (the same pure `decidir()` as the live agent, replayed):

| Cap at | USD | Tokens | Runs cut | Of them successful | Success lost | Cost with budget | Largest run |
|---|---|---|---|---|---|---|---|
| p90 | 0.00468 | 34,842 | 39 | 38 | 15.1 % | $0.6525 | 0.004542 |
| p95 | 0.005237 | 37,971 | 17 | 17 | 6.8 % | $0.6885 | 0.004942 |
| **p99 (chosen)** | **0.0063** | **46,000** | **4** | **4** | **1.6 %** | **$0.7109** | **0.0056** |
| max | 0.007772 | 60,308 | 1 | 1 | 0.4 % | $0.7179 | 0.006776 |

Week 13 spent $0.7196. A cap is a guarantee, not a saving: the p99 cap saves 1.2 % and removes the tail (week 13's worst run cost 23 % more than the cap).
The session cap ($0.039, 300,000 tokens) and the tenant-day cap ($0.32, 2.4 M tokens) are the p99 of the sum of 10 and of 100 tasks (bootstrap, seed 17, 2,000 draws).

## Evaluation with the budget on (84 tasks, k = 1, Haiku 5.5 `low`, 4 in parallel, sessions of 10 consecutive tasks)

| | Week 13 (same tasks, repetition 0) | Replay of the recorded turns ($0) | **Paid run (real model)** |
|---|---|---|---|
| Success | 78 / 84 (92.86 %; 92.06 % over 3 runs) | 77 / 84 (91.67 %) | **74 / 84 (88.10 %)** |
| Stopped by the budget | – | 1 (`presupuesto_tarea`) | **2** (`presupuesto_tarea`, `presupuesto_sesion`) |
| Cost, total | $0.2399 | $0.2366 | **$0.2344** |
| Cost per task p50 / p95 / max | 0.00259 / 0.00478 / 0.00777 | 0.00259 / 0.00471 / 0.00562 | **0.00268 / 0.00480 / 0.00555** |
| Wall time | – | 0.8 s | 163.6 s |

Where the 10 failures of the paid run come from (every one is checked by `test_cada_fallo_de_la_corrida_pagada_tiene_una_causa_medida`):

* **2 were the budget**: `r07-es` (task budget) and `c08-es` (session budget). Both passed 3 of 3 runs in week 13, so the budget cost two successes (2.4 points; the offline replay predicted 1.6).
* **7 were already failing in week 13**: `a03` and `a04` in both languages and `c05-es` (3 of 3 runs failed), `c05-en` (1 of 3) and `s02-en` (2 of 3).
* **1 is unexplained: `s10-es`**. It passed 3 of 3 in week 13 and spent $0.0026, well under every cap, but the report does not keep that task's `max_tokens` per call, and the run was not repeated. It is reported as run-to-run variation, not proved.

Why `c08-es` was cut: sessions here are 10 consecutive tasks of the golden file, which is ordered by type, so session 02 was `r11`, `r12` and eight `compuesta` tasks, the most expensive type. The other nine tasks cost about $0.0347; week 13's `c08-es` costs $0.00465, so the session would have ended near $0.0393, just over its $0.039. The cap was calibrated on random draws of 10 tasks, not on ten heavy ones, so a heavy session is cut by design. For production the session cap should come from real session sizes and mixes.

## Findings

1. **A degrade priced the run at the wrong model (found by the Langfuse check, fixed).** The week 13 loop prices every call at the model it was built with (`costo(self.modelo, ...)`). After a degrade from Sonnet to Haiku, `lab.run.cost_usd` was 20 times too high while each `chat` span was right. `EstadoPresupuesto.costos_del_bucle` now prices each call at the model that answered, and a corrective `costo` trace line is written when they differ. Regression test in `test_el_agente_degrada_al_modelo_barato_que_la_politica_nombra`. The paid run had no degrade, so it was never affected.
2. **Langfuse v4 does not show span events.** The 13-key `gen_ai.budget.decision` events reach the Collector's output file intact (5 of 5 scenarios, same order and same values as the lab recorded), but Langfuse stores 1 observation per span and no event (`presupuestos_langfuse.json`). In Langfuse a budget decision is visible through the agent span (`lab.outcome.status = limite_alcanzado`, `lab.outcome.reason = presupuesto_tarea | presupuesto_sesion | presupuesto_tenant_dia`, level ERROR) and the model and cost of each generation. The spend and limit per decision live in the OTel backend. Activity 8's dashboard must read budget stops from `lab.outcome.reason`, not from events.
3. **Reservations are conservative.** A call reserves its upper cost (prompt estimate plus up to 4,000 output tokens at the output price, about $0.002 on Haiku) until it settles. Under heavy concurrency on a small shared cap this can refuse a call that would have fit once the others settled. The paid run does not show a case we can attribute to it (finding on `c08-es` above), but the cost is real: the cap is never crossed because it is checked against the worst case.
4. **Two cost sources.** The budget counts the loop's own cost (uncached input and output at the model's price, with cache tokens charged as input in the reservation). Langfuse's table also prices the cache. They agree on this workload because the week 13 loop sets no cache.
5. **The estimator is calibrated to this workload** (JSON tool results escaped inside the next message, 1.5 characters per token). A different tool set or language needs `calibracion.py` run again; the tests recompute the numbers from the committed week 13 files, so they fail if the data and the constants drift apart.

## What it does not cover

* The paid run did not use `degradar`, so degrading is verified on the scripted model and in Langfuse, not on the API.
* Reasoning tokens: Haiku `low` showed no output above its `max_tokens` in 84 tasks (0 estimate overruns); a higher effort or another model needs the same check.
* The store is tested with threads and an injected clock for the UTC day boundary, not with several processes.
* The budget does not cap what a tool costs (the database) or the time a task takes; those are the loop's own limits.

## Reproduce

```
cd semana-17
uv run --group semana17 python -m presupuestos.calibracion                          # $0, writes politica_calibrada.json
uv run --group semana17 python -m presupuestos.correr_eval --reproduccion           # $0, recorded turns of week 13
uv run --group semana17 python -m presupuestos.correr_eval --confirmo-gasto         # real model, about $0.24, needs ANTHROPIC_API_KEY
./observabilidad/arrancar.sh && uv run --group semana17 python -m presupuestos.verificar_langfuse   # $0, Mac
```

The report of the paid run is `presupuestos_eval.json`; its per-task console output is `presupuestos_eval_consola.txt` (the report keeps the aggregates
and the cut tasks only).
