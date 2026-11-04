# Activity 7: trajectory eval

Every run of the LegacyBridge agent now gets a trajectory score, written back to Langfuse on its trace. The trajectory is read **from the
spans** (the same `execute_tool` and `chat` spans the Collector's file and Langfuse hold), compared against a frozen reference for its
golden task, and scored by eight deterministic graders. In the paid run (84 tasks, Haiku 5.5 `low`, guardrails and budgets on, $0.2356)
**91.7 % of the trajectories pass**. The span reading matched the loop's own records on 84 of 84 runs, and 756 of 756 scores were
written and read back.

Files: `trayectorias/` (`criterios.py` written before any run was scored, `construir_referencias.py` with `referencias.jsonl` and
`manifiesto.json`, `evaluadores.py`, `adaptadores.py`, `correr_eval.py`, `puntuar_semana13.py`, `analisis.py`), `tests/test_trayectorias.py`
(146 tests, no API) and the evidence in `resultados/trayectorias_*`.

Part 1 (the references, the graders and their tests) was started by a parallel agent that stopped on an API billing error before it
committed. I reviewed its files, finished the adapter it was fixing (the Agent SDK's trace dialect) and kept its definitions as they were:
they were fixed before anything was scored.

## Plan versus result

| Plan bullet | Result |
|---|---|
| Reference trajectories for the 84 tasks: required tools, allowed extras, order constraints, maximum reasonable steps, forbidden tools | ✅ from the golden task: required = its `herramientas_min`; allowed = the four read-only information tools (and the data tool only where the task has output keys); forbidden = `proponer_orden_compra` on all 84 (they are read-only questions); order only where one tool's information feeds another (schema, rule or sampled values before the SQL); steps = `pasos_min` + a margin per task type. The margin is the only number taken from recorded runs: the p90 of extra steps of the successful runs of a CALIBRATION set (week 13, Haiku `medium`), never of the sets that are scored |
| Frozen with a hash manifest | ✅ `manifiesto.json` holds the sha256 of the references, of both golden files and of the calibration file; `construir_referencias --verificar` rebuilds and compares, and a test fails on any drift |
| Deterministic graders on the trace: precision and recall, order, redundant calls, failed calls and recovery, steps, forbidden tools | ✅ eight pure functions (`evaluadores.py`), definitions in `criterios.py`. A trajectory is `ok` when the seven with a pass rule hold (failed calls are reported, recovery judges them) |
| Validate the metrics on known failures first: a missing tool, the wrong order, loops and a forbidden call must each score as bad | ✅ 17 hand-made bad trajectories, each failing exactly the graders the test names for it, no more and no fewer (a missing tool, SQL in the same turn as the schema, 3 wrong orders, a loop of the same SQL, a loop that also runs out of steps, unrecovered errors, too many steps, a forbidden call, a BLOCKED forbidden call, SQL on an ambiguous question, a tool outside the catalogue...), and 14 good ones that pass every grader |
| An LLM judge only for "was the plan reasonable" on ambiguous tasks, only after it passes validation on ≥10 bad trajectories | ⚠️ **not built, because nothing was left for it to decide.** On the 8 ambiguous tasks of the paid run the deterministic verdict and the golden verdict agree 8 of 8 (the agent either asked for clarification without a data query, or ran SQL and answered); on the 96 recorded ambiguous runs of week 13 they agree 93 of 96. A judge would only add cost and a validation burden |
| Analysis: success against trajectory quality | ✅ cross tables below: correct answers from bad paths and bad answers from good paths are counted for every set |
| Analysis: the loop agent against the Claude Agent SDK agent | ✅ from week 13's recorded runs (k = 3 each, $0). ⚠️ The plan's "84 tasks × 2 agents" paid run was not made for the SDK: the recorded runs already give k = 3, and the finding below is structural, not noise |
| Analysis: before and after the guardrails and budgets | ✅ week 13's loop (neither, k = 3) against this activity's paid run (both, k = 1) |
| With confidence intervals as in week 13 | ✅ week 13's own `boot` (bootstrap over tasks, 2,000 resamples, seed 13) and a paired bootstrap for the differences |
| Scores written back to Langfuse on each trace | ✅ 9 scores per trace (`trayectoria.ok`, `trayectoria.puntaje` and one per graded rule), `POST /api/public/scores`, with an id derived from (trace, name) so a rerun overwrites rather than duplicates. Read back with the v3 API: 84 of 84 found, 84 of 84 with the right value |
| Cost ~$0.40, authorized first | ✅ within the standing $2 authorization: **$0.2356** (84 tasks). Spent in the week so far: $0.2909 of $2 |

## Results

| | Runs | Trajectory ok (95 % CI) | Answer ok (95 % CI) | Good answer, bad path | Bad answer, good path |
|---|---|---|---|---|---|
| Week 13 loop, no guardrails or budget (k = 3) | 252 | 0.921 [0.865, 0.968] | 0.921 [0.861, 0.972] | 8 | 8 |
| Week 13 Agent SDK (k = 3) | 252 | **0.318** [0.234, 0.409] | 0.889 [0.825, 0.944] | 148 | 4 |
| Week 13 Agent SDK, without the steps rule | 252 | 0.941 [0.889, 0.984] | 0.889 [0.825, 0.944] | 4 | 17 |
| **This activity: loop with guardrails and budgets, paid (k = 1)** | 84 | **0.917** [0.857, 0.964] | 0.881 [0.810, 0.952] | 2 | 5 |

| Difference (paired bootstrap over tasks) | Value | 95 % CI |
|---|---|---|
| SDK − loop, trajectory | −0.603 | [−0.691, −0.512] |
| SDK without the steps rule − loop, trajectory | +0.020 | [+0.004, +0.040] |
| SDK − loop, answer | −0.032 | [−0.071, +0.004] |
| After − before guardrails and budgets, trajectory | −0.004 | [−0.044, +0.032] |
| After − before, answer | −0.040 | [−0.095, +0.012] |

What fails in the paid run (7 tasks): `a03` and `a04` in both languages ran SQL on a task that needs a clarification question (`precision`;
their answers fail too, as they did 3 of 3 in week 13); `c08-es` was stopped by the session budget before any model call (`recall`, 0 steps);
`v02-es` and `v03-es` sampled the values AFTER the SQL that filters on them (`orden`), and still answered correctly.

The $0 replay of week 13's recorded turns through today's stack gives the same picture (91.7 %, 84 of 84 adapter matches, the same scores
in Langfuse).

## Findings

1. **The steps ceiling belongs to an agent, not to a task.** All 252 SDK runs make exactly one model call after `responder` (the SDK reads the
   tool result and ends its turn), which the loop never does. That turn alone explains 71 of the SDK's 172 steps failures; the other ~100 are
   longer paths. Without the steps rule the SDK is not worse than the loop (+0.020). The margin was calibrated on the loop and was not
   changed after seeing this (the SDK set is held out): a reference for the SDK would need its own calibration.
2. **A clean path is not a correct answer, and the reverse.** In the paid run 2 answers were right from a path the graders fail (`v02-es` and
   `v03-es`, values sampled late) and 5 answers were wrong from a path that passes (the right tools in the right order computing the wrong
   number). The trajectory score is a second signal next to the golden check, not a replacement for it.
3. **Guardrails and budgets did not change the paths.** −0.004 [−0.044, +0.032] on trajectories. The −0.040 on answers is activity 4 and 5's
   known gap (budget cuts and run-to-run variation), and its interval includes 0.
4. **What the spans cannot show.** A call the guardrails blocked never becomes an `execute_tool` span (they sit outside the instrumented
   tools; the block is a `gen_ai.guardrail.decision` event without the tool's name), and `responder` is not a tool span. The eval adds
   `responder` from the loop's lines; blocked calls are not counted as calls. In the paid run there were none on these tasks.
5. **Langfuse v4's API.** Scores are written with `POST /api/public/scores` and read with `GET /api/public/v3/scores` (cursor pagination;
   `page` is rejected). A v3 score carries no trace id by default, so the eval matches scores by their own deterministic id. The old
   `/api/public/traces/{id}` answers 404 in v4; the traces are checked through `v2/observations`.
6. **The SDK writes its trace lines in another dialect** (no step on tool lines, one model line per assistant message, so one API response
   can be two lines). The adapter handles both, and a test checks that it reproduces the steps, calls and errors every recorded run wrote,
   for all four sets.

## Reproduce

```
cd semana-17
uv run --group semana17 python -m trayectorias.construir_referencias --verificar           # $0, the frozen references
uv run --group semana17 python -m trayectorias.puntuar_semana13                            # $0, the recorded week 13 runs
uv run --group semana17 python -m trayectorias.correr_eval --langfuse                      # $0, replay, scores to Langfuse (stack up)
uv run --group semana17 python -m trayectorias.correr_eval --confirmo-gasto --langfuse     # real model, about $0.24
uv run --group semana17 python -m trayectorias.analisis                                    # $0, confidence intervals
```

Reports: `trayectorias_semana13.json`, `trayectorias_reproduccion.json`, `trayectorias_real.json` (and its console
`trayectorias_real_consola.txt`), `trayectorias_analisis.json`.
