# LegacyBridge runbook: five operator questions

Each question is answered by one command (from `semana-17/`, the stack up) in about a second, and by a path in the Langfuse UI or the
OTel backend when no terminal is at hand. Times are end to end, `uv` start included, measured on the Mac on 2026-11-04 against the fixed
run of the dashboard (`index.html`).

| Question | Command | Time | Source |
|---|---|---|---|
| Why did task X fail? | `python -m tablero.preguntar tarea c08-es` | 1.45 s | Collector file (outcome, steps, tool errors, guardrail and budget events) + Langfuse v3 scores |
| What did tenant Y spend today? | `python -m tablero.preguntar tenant lab --dia 2026-11-04` | 1.29 s | Collector file: `lab.run.cost_usd` on the agent spans of that tenant and UTC day, real model only |
| Which tool is slowing things down? | `python -m tablero.preguntar lenta` | 1.15 s | Langfuse `v2/metrics`: p95 latency of TOOL observations by name |
| Who approved order Z? | `python -m tablero.preguntar orden OC-…` | 1.15 s | The approvals store (system of record), with the trace id to open |
| Did yesterday's change make trajectories worse? | `python -m tablero.preguntar cambio --antes A.json --despues B.json` | 1.14 s | Trajectory scores of two runs, paired by task, bootstrap over tasks |

Prefix every command with `uv run --group semana17`.

## 1. Why did task X fail?

```
$ … tablero.preguntar tarea c08-es
estado limite_alcanzado · motivo presupuesto_sesion · pasos 0 · paradas_de_presupuesto ["session:usd"]
evaluadores_de_trayectoria_bajo_1 {"recall_herramientas": 0} · respuesta_correcta false
```

Read it top down: the outcome and its reason (a budget, a guardrail, a loop limit or the model's own answer), then the evidence: budget
stops, guardrail decisions other than `allow`, tool errors, and which trajectory graders fell below 1. Here the session budget stopped
the task before its first model call.

In Langfuse: Traces, filter by the trace id the command prints; the agent observation's level is ERROR and its metadata carries
`lab.outcome.reason`; the Scores tab shows `trayectoria.*` and `respuesta.ok`. The budget and guardrail EVENTS are not in Langfuse (it does
not show span events): they are only in the OTel backend.

## 2. What did tenant Y spend today?

```
$ … tablero.preguntar tenant lab --dia 2026-11-04
usd 0.235641 of limite_usd 0.32 (73.6 %) · corridas 84 · corridas_guionadas_excluidas 228
```

Scripted and replayed runs are excluded: their cost is computed from recorded tokens and nothing was billed. **This is what the traces
saw, not what was billed**: a run that did not export its spans (the paid runs of activities 5 and 6 did not) is invisible here. The
authority for spend is the budget store (`presupuestos/almacen.py`), and in this lab each evaluation used its own store, so the tenant-day
cap was enforced per evaluation process, not across the day (see `resultados/tablero.md`, finding 2).

In Langfuse: the widget "LB · Cost per day" shows the total per day; Langfuse has no tenant dimension, so the per-tenant split needs the
OTel backend.

## 3. Which tool is slowing things down?

```
$ … tablero.preguntar lenta
legado__describir_esquema p95 48.0 ms (25 calls) · legado__ejecutar_sql 30.3 ms (55) · ejecutar_sql 17.0 ms (370) · …
```

Tools are milliseconds; the model is seconds (p95 4.5 s per call in the dashboard). The `legado__` names are the MCP client's (the call
crosses HTTP, OAuth and the server); the others are the native tools.

In Langfuse: the widget "LB · Latency p95 by tool".

## 4. Who approved order Z?

```
$ … tablero.preguntar orden OC-0066753855
aprobada_por gerente (nivel gerente, requerido gerente) · pedida_por sub-analista · 56,462 MXN · decidida 6 min después
intentos: gerente approve ok; director reject refused (ya_decidida) · traza 56185db5…
```

The approvals store answers this, not the trace: the trace carries keyed hashes of the requester and the approver, by design, so an
operator who needs a name goes to the system of record, and uses the trace id to see what the run did before and after.

## 5. Did yesterday's change make trajectories worse?

```
$ … tablero.preguntar cambio --antes trayectorias_reproduccion.json --despues trayectorias_real.json
trayectoria_ok 0.9167 -> 0.9167 · diferencia 0.0 [-0.0476, +0.0476] · veredicto: no measurable change
```

Give it the trajectory reports of the run before and the run after the change (the same 84 tasks). The verdict is "worse" only when the
whole 95 % interval of the paired difference is below zero. One run each (k = 1) gives intervals about ±5 points wide: a smaller change
needs more repetitions.

In Langfuse: the widgets "LB · Trajectory score (mean) over time" and "LB · Trajectory ok and answer ok (rate)".
