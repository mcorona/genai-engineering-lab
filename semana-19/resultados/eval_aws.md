# Week 19, activity 8: the eval against the deployed endpoint

<!-- generado por eval/informe.py: inicio (no editar a mano) -->

### The run

Date: 2026-11-19. Spent by the script (agent spans): 0.675331 USD and 506,301 tokens, against the caps in the code (1.9 USD, 1,300,000 tokens).

| Access check | Expected | Got | OK |
|---|---|---|---|
| POST /consultas without token | 401 | 401 | yes |
| POST /aprobaciones/no-existe with token | 403 | 403 | yes |

Tasks aborted by the cap: v01-en, a01-en, n01-en.

### Success (week 13's execution verifier)

| Group | n | Passed | Rate | Wilson 95% | Aborted |
|---|---|---|---|---|---|
| es | 10 | 7 | 0.7 | [0.397, 0.892] | 0 |
| en | 10 | 2 | 0.2 | [0.057, 0.51] | 3 |
| total | 20 | 9 | 0.45 | [0.258, 0.658] | 3 |

### Regression against the baselines (week 10's rule)

Baseline: semana 17 local (eval_ci_local.json), the same 20 tasks. Threshold = the multiple of 0.05 just below (baseline − max(0.03, 1/n)).

| Group | n | Baseline | AWS | Threshold | Regression | Week 13 (3 runs) |
|---|---|---|---|---|---|---|
| es | 10 | 1 | 0.7 | 0.9 | yes | 1 |
| en | 10 | 1 | 0.2 | 0.9 | yes | 0.933 |
| total | 20 | 1 | 0.45 | 0.95 | yes | 0.967 |

Activity 7 (path a, same deployment): 2 tasks in common (s03-es, s06-es): 2 passed here, 2 there.

**Regression: yes.**

### Trajectory (week 17's graders)

Graded: 17; OK: 7; mean score: 0.923. Failing graders: pasos (9), recall_herramientas (1).

### Latency, cold and warm apart

| Start | n | p50 (s) | p95 (s) |
|---|---|---|---|
| cold | 1 | 49.95 | 49.95 |
| warm | 17 | 23.52 | 30.13 |

Unknown (no REPORT line in the window): 1.

### Tokens and model cost per task (agent spans)

19 tasks: 479,392 input, 26,909 output, 0 cache read, 0 cache write; 0.675331 USD, 0.035544 USD and 26647.4 tokens per task. The AWS charge comes from Cost Explorer (costo_real.md).

| Task | Phase | State | OK | Start | Latency (s) | Steps | Tools | In | Out | USD |
|---|---|---|---|---|---|---|---|---|---|---|
| s01-es | warm-up | respondida | yes | desconocido | 43.89 | 3 | 3 | 12449 | 1530 | 0.022109 |
| s02-es | warm-up | respondida | yes | frio | 49.95 | 5 | 6 | 24910 | 1882 | 0.037752 |
| s03-es | main | respondida | yes | caliente | 14.08 | 4 | 4 | 17959 | 955 | 0.025007 |
| s06-es | main | respondida | yes | caliente | 20.68 | 6 | 6 | 26266 | 1448 | 0.036857 |
| r02-es | main | limite_alcanzado | no | caliente | 24.01 | 7 | 8 | 36975 | 1747 | 0.050281 |
| r05-es | main | respondida | yes | caliente | 12.63 | 3 | 4 | 13032 | 1230 | 0.0211 |
| r12-es | main | respondida | yes | caliente | 24.39 | 7 | 8 | 38146 | 1496 | 0.050189 |
| c02-es | main | abstenida | no | caliente | 9.48 | 2 | 1 | 6634 | 542 | 0.010278 |
| c06-es | main | limite_alcanzado | no | caliente | 25.41 | 7 | 9 | 34582 | 2215 | 0.050223 |
| v01-es | main | respondida | yes | caliente | 15.91 | 4 | 4 | 15145 | 852 | 0.021345 |
| a01-es | main | requiere_aclaracion | yes | caliente | 7.68 | 2 | 0 | 5804 | 492 | 0.00909 |
| n01-es | main | abstenida | yes | caliente | 10.75 | 3 | 1 | 9987 | 695 | 0.014808 |
| s03-en | main | respondida | yes | caliente | 23.52 | 5 | 5 | 22412 | 910 | 0.029658 |
| s06-en | main | respondida | yes | caliente | 22.15 | 6 | 7 | 26972 | 1348 | 0.037083 |
| r02-en | main | limite_alcanzado | no | caliente | 30.13 | 8 | 14 | 40240 | 2452 | 0.05775 |
| r05-en | main | limite_alcanzado | no | caliente | 24.4 | 8 | 9 | 37597 | 1083 | 0.047313 |
| r12-en | main | limite_alcanzado | no | caliente | 23.6 | 8 | 10 | 37406 | 1161 | 0.047532 |
| c02-en | main | abstenida | no | caliente | 28.77 | 6 | 7 | 32677 | 1454 | 0.043942 |
| c06-en | main | respondida | no | caliente | 30.13 | 7 | 8 | 40199 | 3417 | 0.063012 |
| v01-en | main | no_corrida | no | — | — | — | — | — | — | — |
| a01-en | main | no_corrida | no | — | — | — | — | — | — | — |
| n01-en | main | no_corrida | no | — | — | — | — | — | — | — |

### Discarded runs (kept; their spend counts)

| File | Date | Passed | Regression | USD | Tokens | Tool calls |
|---|---|---|---|---|---|---|
| crudo_eval_descartada_1.json | 2026-11-19 | 10/20 | yes | 0.612663 | 435,570 | describir_esquema 18, ejecutar_sql 58 |
| crudo_eval_descartada_2.json | 2026-11-19 | 9/20 | yes | 0.45079 | 331,661 | buscar_regla_negocio 13, describir_esquema 11, ejecutar_sql 33, muestrear_valores 7 |

### The approval workflow, step by step

| Step | Check | OK | Evidence |
|---|---|---|---|
| 0 | el agente propuso la orden | yes | estado_de_la_tarea="respondida" |
| 1 | la máquina espera con el token en DynamoDB y no en logs | yes | apariciones_del_token_en_logs=0; estado_de_la_ejecucion="RUNNING"; nivel_requerido="comprador"; po_id=1; token_en_dynamodb=true |
| 2 | el analista recibe 403 en el gateway | yes | estado_despues="RUNNING"; http=403 |
| 3 | el aprobador aprueba | yes | aprobador_distinto_del_solicitante=true; estado_de_la_ejecucion="SUCCEEDED"; http=200; respuesta="aprobada" |
| 4 | la fila la escribió order_writer | yes |  |
| 5 | una solicitud vencida no escribe | yes | aprobacion_tardia="no_encontrada"; aprobacion_tardia_http=404; error="States.Timeout"; estado_de_la_ejecucion="FAILED" |

Short test wait deployed: 120 s. All five checks passed: yes. Spent: 0.023269 USD, 16,906 tokens (caps 0.2 USD, 100,000).

### The Bedrock judge against the verifier

Job semana19-juez-20261119-220841: Completed in 543 s; judge us.amazon.nova-pro-v1:0; 17 tasks judged. Estimate before the job: 0.14105 USD.

Thresholds fixed before the run: Builtin.Correctness ≥ 0.75, Builtin.Faithfulness ≥ 0.75.

|  | Judge passes | Judge fails |
|---|---|---|
| Verifier passes | 7 | 2 |
| Verifier fails | 1 | 5 |

Agreement 0.8, Cohen's kappa 0.5946 (n = 15; without a score: r02-en, r05-en). False passes: c02-en. False fails: s03-es, s03-en.

| Metric | Mean |
|---|---|
| Builtin.Correctness | 0.7 |
| Builtin.Faithfulness | 0.8529 |
| Builtin.Completeness | 0.6471 |

### Schema of eval_aws_detalle.jsonl (week 20's baseline)

One line per task, the fields in this order; checked by `eval_aws.validar_detalle` before writing.

| Field | Type | Meaning |
|---|---|---|
| id | string | task id, week 13's id plus the language (s03-es) |
| idioma | string | es or en |
| fase | string | principal (the 20 CI tasks) or calentamiento (the cold warm-up, reported apart) |
| exito | boolean | week 13's execution verifier against the rows recomputed on RDS; an aborted task is false |
| estado | string | the API's final state, or no_corrida when the script's cap stopped it |
| estado_esperado | string or null | week 13's expected state |
| arranque | string or null | frio, caliente or desconocido, from the REPORT lines of the task's window |
| latencia_s | integer or number or null | POST /consultas to the final GET, seconds |
| pasos | integer or null | model turns (lab.run.steps of the agent span) |
| herramientas | integer or null | tool calls (execute_tool spans) |
| tokens_entrada | integer or null | input tokens of the run |
| tokens_salida | integer or null | output tokens of the run |
| tokens_cache_lectura | integer or null | prompt-cache read tokens |
| tokens_cache_escritura | integer or null | prompt-cache write tokens |
| costo_usd | integer or number or null | model cost of the run from the agent span (lab.run.cost_usd) |
| trayectoria_ok | boolean or null | week 17's trajectory graders against the frozen reference |
| bloqueos_capa | integer or null | decisions of the policy layer that were not allow |
| bloqueos_guardrail | integer or null | 1 when the run ended on a guardrail intervention |
| bloqueos_politica | integer or null | tool calls refused by the gateway's Cedar policies (path b only) |
| veredicto_juez | object or null | the Bedrock judge's verdict (comparar_jueces.veredicto plus the scores); null for the warm-up and for tasks not judged |

<!-- generado por eval/informe.py: fin -->

## Analysis (written by hand)

### Three runs, one result

The official run is the third one (`crudo_eval.json`). The other two are kept as `crudo_eval_descartada_*.json`, and their spend counts toward the script's cumulative cap.

1. **Run 1 (10/20):** discarded because the AWS port had narrowed the tools catalog to `describir_esquema`, `ejecutar_sql` and `proponer_orden_compra`. The system prompt still asked for `buscar_regla_negocio` and `muestrear_valores`, so without the rule the agent made up its own definitions. Fixed in #281, where both tools came back from week 13.
2. **Run 2 (9/20):** discarded because 8 tasks did not run. The cumulative cap (run 1 plus run 2) stopped them, so the run was incomplete. The cap went to 1.90 USD and 1.3M tokens in #283.
3. **Run 3 (9/20):** 3 tasks did not run (v01-en, a01-en, n01-en). The cumulative cap stopped them; they count as failures and are reported as aborted.

### Why it regresses

- **The per-task budget (5 of the 11 failures).** r02-es, c06-es, r02-en, r05-en and r12-en ended `limite_alcanzado` with reason `presupuesto_tarea`, after 7 or 8 steps and 36,797 to 42,692 tokens.
  - The budget is week 17's calibration (`semana-17/presupuestos/politica_calibrada.json`): the p99 of week 13's Haiku 5.5 runs, 46,000 tokens per task.
  - The port (`agente/construccion.py`) scaled the USD limit to Haiku 4.5's price but kept the token limit.
  - The deployed agent runs Haiku 4.5 on Bedrock and needs more turns, so the reservation for the next call no longer fits.
  - We do not recalibrate from this run: every stopped task was cut by the budget itself, so any p99 taken from them would be made up. The calibration needs runs that the budget does not cut.
- **No prompt cache.** Cache read and write are 0 on every task. Converse caches only when the request carries a `cachePoint`, and the port sends none. Every turn pays again for the system prompt, the five tool definitions and the history, and the token budget is spent on that.
- **c02 abstains in both languages** where an answer was expected. The agent says the database has no approval records, while rule R-OC-APRUEBA defines the approval levels by amount.
- **c06-en answers in Spanish.** Its coverage figure is not exact either (key exactness 0.5).
- **English is worse than Spanish (2/10 against 7/10).** English has 3 budget stops against Spanish's 2. The 3 tasks the cap stopped are all English ones, because they are the last in the order.

### What it means

Under week 10's rule the deployed endpoint does not reach week 17's local baseline, in either language or in total. On what it does answer, the AWS stack matches activity 7 (2 of 2 tasks in common).

The fixes, in order:
1. A token budget calibrated for the deployed model.
2. A `cachePoint` on the system prompt and the tool definitions.
3. c02's use of R-OC-APRUEBA.

Each one needs a new paid run to be verified.

### The judge against the verifier

The judge was Nova Pro (`us.amazon.nova-pro-v1:0`, not the evaluated model). It scored the 17 tasks that ran, and the job took 543 s.

- **The comparison:** it covers 15 tasks, with agreement 0.8 and kappa 0.5946. r02-en and r05-en have no Correctness score: the budget stopped them, so their answer is empty.
- **False fails, s03-es and s03-en.** Correctness is 1.0 in both, but Faithfulness is 0.25.
  - The judge says the "6 critical products" in the answer does not appear in the context.
  - The context in the prompt is the verifier's re-execution of the agent's final SQL (`eval_aws.registrar_contexto`), which returns only the supplier's name. It is not the 4 tool results the agent saw, and the count came from one of those earlier calls.
  - The miss is in how the eval builds the judge's prompt, not in the agent.
- **False pass, c02-en.** The judge gives 1.0 on all three metrics to an abstention where the verifier expects an answer. The judge accepts the agent's reason (no approval history by role in the schema), while the reference answer gives the approval levels.

For this task set, the execution verifier stays the reference. A judge with incomplete context fails correct answers that cite intermediate results, and it accepts well-argued abstentions.
