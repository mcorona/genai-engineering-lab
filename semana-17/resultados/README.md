# Week 17 results (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 17 README](../README.md)

The evidence of week 17's ten activities: the reliability controls of the LegacyBridge agent (tracing, budgets,
guardrails, human approval, trajectory eval, dashboard, security of the observability stack and CI). Each activity
has an English report (`*.md`) and the raw JSON or console files its scripts wrote. Most scripts run in two modes: a
$0 mode (a scripted model, or a replay of week 13's recorded turns) and a paid mode with the real model.

**Recorded evidence:** the JSON, JSONL, TXT and HTML files are the raw outputs of the runs, kept exactly as recorded:
not edited, not translated. The scripts that wrote them are listed below. The English summary of the results is in
the [week 17 README](../README.md#2-results) and in each activity's report: [linea_base.md](linea_base.md),
[stack.md](stack.md), [instrumentacion.md](instrumentacion.md), [frameworks.md](frameworks.md),
[presupuestos.md](presupuestos.md), [guardrails.md](guardrails.md), [aprobaciones.md](aprobaciones.md),
[trayectorias.md](trayectorias.md), [tablero.md](tablero.md), [seguridad_obs.md](seguridad_obs.md) and
[ci_calibracion.md](ci_calibracion.md). This README does not restate the results.

## Files

Script paths are relative to `semana-17/`.

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `*.md` | The English report of each activity, with the results, the limitations and links to the raw files | Written by hand from the raw files |
| `linea_base_*.json` | Activity 1, baseline: one probe report per place (`mac`, `contenedor` = the lab container), plus the Claude Code telemetry probe | `linea_base/verificar.py` / `tests/test_linea_base.py` |
| `stack.json` | Activity 2: the self-hosted Langfuse and Collector stack (start, exposure, OTLP, restarts, outage, delete) | `observabilidad/verificar_stack.py` / `tests/test_stack.py` |
| `muestreo.json` | Activity 2: the Collector's sampling check, reported in `stack.md` | `observabilidad/verificar_muestreo.py` / `tests/test_muestreo.py` |
| `instrumentacion.json` | Activity 3: one task traced end to end, checked in Langfuse | `instrumentacion/verificar_langfuse.py` / `tests/test_instrumentacion.py` |
| `frameworks.json` | Activity 3, optional: the same task through Strands and LangGraph | `comparacion/comparar_frameworks.py` / `tests/test_frameworks.py` |
| `presupuestos_*` | Activity 4, budgets: the calibration of the caps, the paid 84-task run and its $0 replay, the degradation test, the repeated runs and their control, the Langfuse check, and the console output of the paid run | `presupuestos/calibracion.py`, `presupuestos/correr_eval.py`, `presupuestos/resumir_control.py`, `presupuestos/verificar_langfuse.py` / `tests/test_presupuestos.py` |
| `guardrails_*` | Activity 5, guardrails: false positives on the gold set (paid run, replays, the report before tuning), the 38 attacks (real, simulated and obedient model, with the first pass of the obedient run), the held-out set, and the console output of the two paid runs | `guardrails/correr_eval.py`, `guardrails/correr_ataques.py`, `guardrails/correr_heldout.py` / `tests/test_guardrails.py` |
| `aprobaciones_*` | Activity 6, human approval: the scripted and the real-model runs, the console output of the real run, and the Keycloak token check | `aprobaciones/correr_eval.py`, `aprobaciones/keycloak.py` / `tests/test_aprobaciones.py` |
| `trayectorias_*` | Activity 7, trajectory eval: the paid run and its $0 replay, the console output of the paid run, the graders on week 13's recorded runs, and the analysis with confidence intervals | `trayectorias/correr_eval.py`, `trayectorias/puntuar_semana13.py`, `trayectorias/analisis.py` / `tests/test_trayectorias.py`, `tablero/` |
| `tablero/datos.json`, `tablero/index.html` | Activity 8: the dashboard's data and its static, self-contained snapshot page | `tablero/exportar.py` / `tests/test_tablero.py` |
| `tablero/corrida_hitl.json` | Activity 8: a $0 rerun of activity 6's approval eval, with its traces sent to Langfuse for the dashboard (same format as `aprobaciones_*.json`) | `aprobaciones/correr_eval.py --otlp` / `tablero/exportar.py` |
| `tablero/runbook.md` | Activity 8: the runbook, five operator questions with their commands (in English) | Written by hand / answered by `tablero/preguntar.py` |
| `seguridad_obs_*.json` | Activity 9, security of the observability: canaries, retention, tenant isolation | `seguridad_obs/verificar_canarios.py`, `seguridad_obs/retencion.py`, `seguridad_obs/tenants.py` / `tests/test_seguridad_obs.py` |
| `eval_ci_local.json` | Activity 10: the report of the CI mini eval, from a local run with the real model (the script names it `eval_ci.json`) | `ci/eval_ci.py` / `semana-19/eval/eval_aws.py` (week 19's baseline) |

## Keys

| Key | Meaning |
|---|---|
| `fecha` | Date of the run |
| `modo` | Run mode: `modelo real` (the real model, paid), `modelo guionado (sin costo)` (a scripted model, $0), `modelo simulado (sin costo)` (a simulated model, $0), `modelo obediente (guion), sin costo` (a scripted model that obeys every injected instruction, $0), `reproduccion de la semana 13 (sin modelo)` (a replay of week 13's recorded turns, no model call) |
| `modelo`, `esfuerzo` | Model id, reasoning effort |
| `donde` | Where the probes ran: `mac` or `contenedor` (the lab container). Inside the `collector` probe: how the Collector ran (`docker` or `binary`) |
| `sondas` | Probes, one entry per probe |
| `tareas`, `por_tarea` | Tasks, per-task detail |
| `corridas`, `por_corrida` | Runs, per-run detail |
| `por_caso` | Per-case detail (attack or held-out case) |
| `escenarios` | Scenarios |
| `criterios` | The pass criteria, fixed before the run (for example, the maximum of obeyed attacks, writes and leaks) |
| `garantias` | Guarantees: the security counts checked on every run |
| `resultado` | Result |
| `falsos_positivos` | False positives (a guardrail blocked a legitimate task) |
| `tablas_modificadas` | Tables modified (expected: none) |
| `politica` | The budget policy: the caps per task, session and tenant-day |
| `tareas_cortadas` | Tasks stopped by a budget, with the reason (`motivo`) |
| `motivo` | Reason. For a stopped task: `presupuesto_tarea` (the per-task budget) or `presupuesto_sesion` (the session budget). For a finished task: `responder` (the agent answered) |
| `base_semana_13` | The week 13 run used as the comparison |
| `trayectoria_ok`, `puntaje_medio` | The trajectory passes its reference; mean trajectory score |
| `exito_respuesta` | Answer success (the week 13 checker) |
| `canarios` | Canaries: planted secret values that must not reach a trace |
| `umbrales`, `medidos` | The CI thresholds; the measured values |
| `costo_usd`, `costo` | Cost in USD |
| `ok` | The check passed |
