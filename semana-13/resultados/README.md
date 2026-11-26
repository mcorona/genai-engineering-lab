# Week 13 results (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 13 README](../README.md)

The outputs of the week 13 runs: the agent on the task gold set (pilots, full evaluation, MCP and Claude Agent SDK
variants), the week 10 workflow on the same tasks, and the security suite. `agente/correr.py` writes one detail file
and one trace file per run. The evaluation, comparison and equivalence scripts read them and write the summaries and
reports. Later weeks (14, 15, 17 and 19) read some of these runs as a reference.

**Recorded evidence:** these are the raw outputs of the runs, kept exactly as recorded (not edited, not translated).
The tasks, answers and judge reasons in them are in Spanish or English, depending on the task's language. The English
summary of the results is in the [week 13 README](../README.md) (sections 3 to 10) and in the English reports of this
folder: [`agente.md`](agente.md), [`mcp_equivalencia.md`](mcp_equivalencia.md),
[`agente_vs_workflow.md`](agente_vs_workflow.md), [`seguridad.md`](seguridad.md),
[`ci_calibracion.md`](ci_calibracion.md) and [`patrones.md`](patrones.md).

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `agente.md`, `agente_resumen.json`, `agente_juez_cache.json` | Activity 5: the agent evaluation report, its machine-readable summary per configuration, and the recorded verdicts of the LLM judge on free-text answers | Written by `agente/evaluar.py` |
| `piloto_detalle.jsonl`, `piloto2_detalle.jsonl`, `piloto_mcp_detalle.jsonl`, `piloto_sdk_detalle.jsonl` | Pilot runs on a few tasks: one row per task and repetition. `piloto2` follows two fixes; `piloto_mcp` uses the tools through the MCP server; `piloto_sdk` uses the Claude Agent SDK | Written by `agente/correr.py`; `piloto2` is read by `servidor_mcp/equivalencia.py` |
| `eval_*_detalle.jsonl` | Full gold-set runs, k = 3: Haiku `low` and `medium`, the Claude Agent SDK (`eval_sdk_low`) and the Sonnet subset (`eval_sonnet_low_sub`) | Written by `agente/correr.py`; read by `agente/evaluar.py`, `workflow/comparar.py`, `agente_sdk/comparar.py` and later weeks |
| `trazas/*.jsonl` | One event per line for each run: model calls, tool calls, the final answer and the stop. The name is the run's name | Written by `agente/correr.py` (`seguridad.jsonl` by `seguridad/correr.py`); read by `agente/evaluar.py`, `servidor_mcp/equivalencia.py` (`piloto*.jsonl`) and later weeks |
| `mcp_equivalencia.md`, `mcp_equivalencia.json` | Activity 4: native tools vs. the MCP server (catalog, replayed traces, gold set, permissions). Deterministic, no model calls | Written by `servidor_mcp/equivalencia.py` |
| `workflow_s10_detalle.jsonl` | Activity 6: the week 10 assistant run as a fixed-routing workflow on the gold set | Written by `workflow/correr.py`; read by `workflow/comparar.py` and `agente_sdk/comparar.py` |
| `agente_vs_workflow.md`, `agente_vs_workflow.json` | Activity 6: agent vs. workflow by task type | Written by `workflow/comparar.py` |
| `seguridad.md`, `seguridad_resumen.json`, `seguridad_detalle.jsonl` | Activity 7: the security suite through the agent: report, summary with the database fingerprint before and after, one row per case and repetition | Written by `seguridad/correr.py` |
| `ci_calibracion.md` | Activity 8: the calibration of the CI thresholds, from the first run of `eval-semana-13` | Written with activity 8; the thresholds are set in `ci/eval_ci.py` |
| `patrones.md`, `patrones.json` | Activity 10: hand-written loop vs. Claude Agent SDK vs. workflow on the same gold set | Written by `agente_sdk/comparar.py` |
| `v1/**` | The first full evaluation (v1), before the gold set's wording and the judge were fixed: report, summary, detail and traces. Kept for comparison | Written by `agente/correr.py` and `agente/evaluar.py` |
| `v2_simples/*.jsonl` | The intermediate re-run of the simple tasks, after the first wording of the `filas` fix | Written by `agente/correr.py` |

## Keys

| Key | Meaning |
|---|---|
| `rep` | Repetition number of the task (0 to k − 1) |
| `via` | How the tools are called: `nativo` (native) or `mcp` (through the MCP server) |
| `patron` | The agent pattern: `loop` (the hand-written loop) or `sdk` (the Claude Agent SDK). Absent in the runs recorded before the SDK variant |
| `esfuerzo` | The model's effort setting (`low`, `medium`) |
| `tipo` | In the detail: the task type (see the [gold set README](../golden/README.md)). In the traces: the event type, `modelo` (model call), `herramienta` (tool call), `final` (final answer), `parada` (stop) |
| `estado`, `esperado` | The agent's final state and the expected state: `respondida` (answered), `requiere_aclaracion` (needs clarification), `abstenida` (abstained) |
| `exito` | The task passed |
| `exactitud_claves` | Execution accuracy over the task's output keys |
| `coherencia_claves` | Answer consistency: the reported value matches what the agent's SQL returns |
| `claves` | Per output key: `reportada` (reported), `exacta` (the SQL returns the expected result), `coherente` (consistent), `error` |
| `pasos`, `pasos_min` | Model calls in the run; the minimum the task needs |
| `herramientas` | Number of tool calls |
| `errores_herramienta` | Tool calls that returned an error |
| `tokens_in`, `tokens_out` | Input and output tokens |
| `segundos` | Wall-clock seconds |
| `motivo` | Why the run stopped (`responder` = the model gave its final answer) |
| `final` | The structured final answer: `estado`, `respuesta` (answer), `resultados` (key, SQL, value), `evidencia` (evidence), `supuestos` (assumptions), `pregunta_aclaracion` (clarification question) |
| `ruta` | The workflow's route: `sql` or `mixta` (mixed) in this run (the week 10 router can also choose `documental`, document) |
| `corrida`, `tarea`, `paso`, `ts` | In a trace event: the run, the task ID, the step number and the timestamp |
| `costo_fuente`, `rechazadas_por_esquema_sdk` | In the SDK's `parada` events: where the cost comes from (`sdk` = reported by the SDK, `tokens` = computed from tokens); tool calls the SDK rejected for not matching the tool schema |
| `argumentos`, `ms`, `paralela` | A tool call's arguments, its duration in milliseconds, and whether it ran in a parallel turn |
| `configuracion` | Model and effort of the run |
| `pass@1_ic`, `pass^3_ic` | 95% confidence intervals of pass@1 and pass^3 (bootstrap over tasks) |
| `por_idioma` | Results per language |
| `estados` | Runs per pair of states, as `<expected> -> <final>` |
| `limite_alcanzado` | In the summary: runs that ended at a limit or with an error |
| `aclaracion_correcta`, `abstencion_correcta` | Share of ambiguous tasks with a clarification; share of unanswerable tasks with an abstention |
| `falsa_aclaracion_o_abstencion` | Clarifications or abstentions on tasks that have an answer |
| `juez_texto_libre` | The LLM judge on free text: `evaluadas` (judged), `adecuadas` (adequate), `sin_veredicto` (no verdict), `no_adecuadas` (not adequate, with `razon`, the reason) |
| `trayectoria` | Trajectory metrics: `llamadas` (tool calls), `validas` and `exitosas` (share of valid and of successful calls), `redundantes_por_corrida` and `corridas_con_redundancia` (repeated calls per run, share of runs with one), `pasos_sobre_minimo` (mean ratio of steps to the minimum), `corridas_con_error` (runs with a tool error), `recuperacion_tras_error` (success rate of those runs), `uso_herramientas` (calls per tool) |
| `por_tarea` | Per task: p50 and p95 of steps, tokens, USD and seconds |
| `costo_total_usd` | Total cost of the run, in USD |
| `fallas` | The failed runs, with their key results |
| `diferencias` | Paired differences between configurations: `de` (from), `a` (to), `dif_pass@1`, `ic` (confidence interval) |
| `dif_pass1`, `sdk_menos_loop`, `sdk_menos_workflow` | Paired pass@1 differences per task type: agent minus workflow; SDK minus hand-written loop; SDK minus workflow (each with its 95% confidence interval) |
| `calibracion_juez` | The judge's score on the known good and bad cases |
| `adecuada`, `razon` | In the judge cache: whether the free-text answer is adequate, and why |
| `agente`, `workflow`, `loop`, `sdk` | The patterns compared: the agent (hand-written loop), the workflow, the hand-written loop, the Claude Agent SDK |
| `pass1`, `passk`, `usd`, `seg`, `pasos`, `costo_total` | pass@1, pass^k, USD, seconds and steps (each as p50, p95), and total cost, per task type |
| `rutas_workflow` | How often the workflow took each route, by task type |
| `rol_nativo` | The database role the native tools use |
| `A_catalogo_igual`, `B_trazas`, `C_golden`, `D_permisos` | The four equivalence checks: the same tool catalog, the same results on replayed trace calls, the same gold-set results, the same permission answers |
| `iguales`, `diferentes`, `exactas`, `igual` | Equal, different and exact results; one call with an equal result |
| `tareas_exito` | Gold-set tasks that passed through the MCP server |
| `categoria` | Security case category: `escritura` (write), `propuesta` (purchase proposal), `fuga_rol` (leakage by role), `fuga_tenant` (leakage across tenants), `inyeccion_datos` (prompt injection in SQL results), `inyeccion_regla` (prompt injection in a business rule), `bucle` (loop) |
| `usuario` | The simulated user (`analista`, `almacenista`, `vendedor`) |
| `intentos_escritura`, `propuestas` | Write statements the agent tried to run; purchase proposals registered |
| `uso` | Tool calls per tool in the case |
| `valores_prohibidos`, `fuga` | The values the user must not see; whether any appeared in the answer |
| `acceso_prohibido_ok` | A forbidden read succeeded |
| `ok` | In the security detail: the case passed. In a trace's tool call: the call succeeded |
| `expuesto`, `obedecio`, `juez` | Injection cases: the malicious text reached the agent through a tool result; the agent obeyed it; the LLM judge's reason when the judge decided |
| `dentro_de_limites`, `paro_por_limite` | Loop cases: the run stayed within the step, tool-call and cost limits; the run stopped at a limit |
| `huella_antes`, `huella_despues`, `tablas_modificadas` | The database fingerprint (row count and MD5 per table, plus `objetos_grandes`, the large-object count) before and after the suite; tables that changed |
| `costo_agente_usd` | Cost of the agent runs, in USD |
| `por_categoria` | Runs (`corridas`) and passes (`ok`) per category |
