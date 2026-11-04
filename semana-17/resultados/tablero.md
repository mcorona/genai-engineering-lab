# Activity 8: the LegacyBridge trace dashboard

LegacyBridge now has a dashboard in Langfuse, **defined as code** (11 widgets through the `unstable` dashboards API, recreated by one
idempotent script), and a **static snapshot in the repo** (`resultados/tablero/index.html` and `datos.json`) generated from the Langfuse
API and the Collector's file for a fixed run: the 84 paid tasks of activity 7 and 14 approval runs of activity 6. A **runbook** answers the
five operator questions with one command each, in about a second. Cost: $0.

Files: `tablero/` (`langfuse_tablero.py`, `fuentes.py`, `exportar.py`, `preguntar.py`), `resultados/tablero/` (`index.html`,
`datos.json`, `runbook.md`, `corrida_hitl.json`), `tests/test_tablero.py` (no API, no Docker).

## Plan versus result

| Plan bullet | Result |
|---|---|
| Langfuse dashboards, defined as code where the API allows it, otherwise documented step by step | ✅ `langfuse_tablero.py` creates 11 widgets and the dashboard that places them (`/api/public/unstable/dashboard-widgets` and `/dashboards`, `PATCH` for the layout). Idempotent: it deletes its own dashboard and widgets by name first. ⚠️ The API is `unstable` by name: if it changes, the widget list in the script is the step-by-step definition to rebuild it by hand, and the static export does not depend on it |
| Cost per task, per tenant and per day, against the budget | ⚠️ Partly in Langfuse (cost per day and per model): **Langfuse has no task or tenant dimension.** Per task and per tenant/day against the caps are in the static export, from the `lab.*` attributes in the OTel backend: p50 $0.0025, p95 $0.0047, max $0.0055 per task against $0.0063 (0 over); the tenant's day $0.2356 against $0.32. Langfuse and the loop agree on every trace's cost (max difference $0) |
| Latency p50 and p95 per step type (model, tool, MCP server, SQL) | ✅ in Langfuse (p50 and p95 by observation type, p95 by tool) and in the export: model 1.47 / 4.53 s, client tool 0.003 / 0.014 s, MCP server 0.000 / 0.001 s, SQL 0.003 / 0.004 s, approval decision 0.007 / 0.009 s, whole run 6.3 / 12.2 s |
| Tokens: input, cache read, output and reasoning | ✅ input and output per day in Langfuse; totals in the export (1,730,173 in, 132,148 out). ⚠️ Cache read is 0 because the week 13 loop sets no prompt cache, and reasoning tokens are not reported separately at effort `low` (they are inside output): both panels say so instead of showing an empty bar |
| Tool errors and recovery | ✅ errors by tool in Langfuse; errors and how many were recovered by a later call of the same tool in the export (2 `muestrear_valores` errors, both recovered) |
| Guardrail blocks by type | ⚠️ **Only in the static export**: Langfuse does not show span events (activity 4, finding 3). From the OTel backend: blocks and sanitizations by guardrail and reason, and the audit-mode observations (`salida_fundamentacion`, 3) |
| HITL: requests, waiting time and decisions | ⚠️ **Only in the static export**, for the same reason: 14 requests, every decision by type and reason (applied and refused), waiting time of the applied ones (median 8 min, max 61 min, simulated approver on an injected clock), resumes by final state |
| Trajectory and success scores over time | ✅ in Langfuse (mean trajectory score over time; trajectory ok and answer ok rates) and in the export, per run: replay 0.917 / 0.917, paid run 0.917 / 0.881. `respuesta.ok` (week 13's execution check) was published as a score next to `trayectoria.*` for the 168 runs of activity 7 |
| A static export for the repo, from the Langfuse API, for a fixed eval run | ✅ `exportar.py` (2.5 s): a self-contained page (inline SVG, no script, no external asset, light and dark) and the data behind it |
| Runbook: five operator questions in under a minute each | ✅ `runbook.md` and `preguntar.py`: why did task X fail (1.45 s), what did tenant Y spend today (1.29 s), which tool is slowing things down (1.15 s), who approved order Z (1.15 s), did yesterday's change make trajectories worse (1.14 s), each with its Langfuse path too |
| Cost $0, on the traces of activities 4 to 7 | ✅ $0. ⚠️ The traces of activities 4 to 6's paid runs were not exported to the stack (those runners did not export); the fixed run uses activity 7's paid traces and a $0 rerun of activity 6's scenarios that does export |

## Findings

1. **Two backends are needed, and that is a design decision, not a gap to close later.** Langfuse answers cost, latency, tokens, tool
   errors and scores, by its own dimensions (type, name, model, time, level). The lab's decisions (guardrail, budget, HITL) are span events
   and its business keys (task, tenant, outcome) are span attributes: Langfuse v4 shows neither as a dimension. The OTel backend (here the
   Collector's file; in production any OTLP store) is where an operator answers "why" and "who".
2. **The dashboard shows what was traced, not what was billed, and the tenant's daily cap was per process.** The first answer to "what
   did tenant `lab` spend today" was $0.717 against a $0.32 cap: it added scripted and replayed runs, whose cost is computed from recorded
   tokens. With the real model only it is $0.2356. Two things follow. Runs that do not export their spans (activities 5 and 6's paid runs)
   are invisible to the dashboard, so spend is answered by the budget store. And each evaluation used its own temporary budget store, so the
   tenant-day cap of activity 4 was enforced per evaluation, never across the day: a deployment needs ONE store per tenant.
3. **Who approved an order is answered by the approvals store.** The trace carries keyed hashes of the requester and the approver, with a
   salt per process, so the trace alone cannot name a person (that is the point). The runbook goes to the system of record and uses the
   trace id to show the run around the decision.
4. **The Collector's file also holds message content from week 17's optional Strands run** (`gen_ai.user.message` and similar events,
   activity 3's comparison, where Strands records prompts by default). Activity 9 has to decide what the file keeps and for how long.
5. **Langfuse's metrics API uses milliseconds for observation latency; the observations API uses seconds.** The runbook's tool latencies
   are in ms and the export's in s; both say so.

## Reproduce

```
cd semana-17                                   # the stack up: ./observabilidad/arrancar.sh
uv run --group semana17 python -m aprobaciones.correr_eval --otlp --esquema hitl_tablero --salida resultados/tablero/corrida_hitl.json   # $0
uv run --group semana17 python -m tablero.fuentes            # publishes respuesta.ok for activity 7's runs
uv run --group semana17 python -m tablero.langfuse_tablero   # the dashboard as code
uv run --group semana17 python -m tablero.exportar           # the static snapshot
uv run --group semana17 python -m tablero.preguntar …        # the runbook
```
