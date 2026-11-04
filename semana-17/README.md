# Week 17: reliability of an agent in production

**Outcome.** The LegacyBridge agent of weeks 13 and 14 now runs with the controls a production agent needs, and every one of them leaves a
trace. One task is one OpenTelemetry trace (agent, model calls, MCP client, server, SQL) that reaches a self-hosted Langfuse through a
Collector that redacts by allowlist. Every model call goes through a budget; every request, tool call and answer goes through guardrails; a
purchase-order proposal waits for a person with the right approval level; every run gets a trajectory score; and an operator can answer
five questions about it in about a second. The `eval-semana-17` check runs all of it on every pull request, with a mini eval on the API.

The plan and the log of decisions are in [`Fas4Sema17.md`](Fas4Sema17.md).

## 1. Architecture

```
 LegacyBridge agent (week 13 loop, unchanged)            each layer wraps the loop's two injectable pieces: the model call and the tools
 ├─ AgenteInstrumentado      invoke_agent / chat / execute_tool spans, a locked shape (instrumentacion/esquema.py)
 ├─ AgentePresupuestado      task, session and tenant-day budgets, checked before every model call   → gen_ai.budget.decision
 ├─ AgenteGuardado           input, tool and output guardrails                                     → gen_ai.guardrail.decision
 └─ AgenteAprobable          a proposal pauses the run; a person approves; the run resumes         → gen_ai.hitl.request / decision / resume
        │ MCP (Streamable HTTP, OAuth, trace context in params._meta)
        ▼
 week 14 MCP server ── authorize / handle_tool / SELECT legado spans ──► PostgreSQL (read-only roles; approvals in their own schema)

 spans ──OTLP──► Collector: memory_limiter → redaction (ALLOWLIST: the 105 keys of the locked shape) → transform (names, statuses) → batch
                   ├─► file (JSONL, rotated): the OTel backend, where the span EVENTS and the lab.* keys are read
                   └─► Langfuse v4 self-hosted (web, worker, PostgreSQL, ClickHouse, Redis, MinIO; one project per tenant)
```

The span model follows the OpenTelemetry GenAI conventions (`invoke_agent`, `chat`, `execute_tool`, `gen_ai.*`), which are still
Development: the instrumentation and the schema are pinned, and a test locks the shape the lab emits (67 span keys and 33 event keys, all
numbers, words of fixed lists, identifiers or keyed hashes; no prompt, SQL, row or name ever enters a span).

## 2. Results

| Activity | What it measured | Result | Report |
|---|---|---|---|
| 1. Baseline | What the stack already observed | 10 probes; 3 gaps found and assigned | [linea_base.md](resultados/linea_base.md) |
| 2. Stack | Langfuse v4 and the Collector, self-hosted | a trace reaches both with 0 of 7 canaries; survives restarts and an outage | [stack.md](resultados/stack.md) |
| 3. Instrumentation | One task end to end | 15 spans in one trace, tokens and cost add up, 0 canaries | [instrumentacion.md](resultados/instrumentacion.md) |
| 4. Budgets | 84 tasks with budgets (paid) | **0 caps crossed**; 74/84; 2 tasks stopped with a partial answer | [presupuestos.md](resultados/presupuestos.md) |
| 5. Guardrails | 38 attacks and 84 golden tasks (paid) | **0 obeyed, 0 writes, 0 leaks**; 9 of 10 guardrails with no false positive; 1 rejected and shipped in audit mode | [guardrails.md](resultados/guardrails.md) |
| 6. Human approval | 7 scenarios × ES/EN (paid) | **0 orders without approval**, 0 effects of a rejection, 0 "auto-approve" obeyed; real Keycloak tokens | [aprobaciones.md](resultados/aprobaciones.md) |
| 7. Trajectory eval | 84 tasks, scores to Langfuse (paid) | 91.7 % of trajectories pass; guardrails and budgets did not change the paths | [trayectorias.md](resultados/trayectorias.md) |
| 8. Dashboard | Langfuse as code, a static snapshot, a runbook | 11 widgets; 5 operator questions in ~1.2 s each | [tablero.md](resultados/tablero.md), [snapshot](resultados/tablero/index.html) |
| 9. Security of the observability | Canaries, tenants, retention, injection | **0 of 9 canaries** with content capture off and on; tenant isolation both ways | [seguridad_obs.md](resultados/seguridad_obs.md) |
| 10. CI | The mini eval on every PR | thresholds 0.85 success and 0.90 trajectory (n = 20), security 0 in 3 of 3 runs, ~$0.08 per run | [ci_calibracion.md](resultados/ci_calibracion.md) |

## 3. Security

No threshold: one violation fails. **Writes** outside a proposal: 0 (table fingerprints). **Leaks** by role or tenant: 0. **Instructions
obeyed** from data, tools or rules: 0 (38 attacks, live). **Orders without an approval**: 0, counted by SQL and enforced by the database's
own constraints. **Secrets or personal values in traces**: 0 (canaries in the prompt, arguments, results, answers and a capturing library,
through the real Collector, in Langfuse and the file). **Spend over a cap**: 0 (every task, session and day of every paid run).

What the measurements do not cover, and the reasons, are in each report. The main ones: the guardrail rules are in-sample; one guardrail
(figure grounding) is shipped in audit mode because it failed its false-positive limit; Langfuse OSS has no API for projects and no
retention per project, so both have substitutes; the dashboard sees what was traced, not what was billed.

## 4. CI

`eval-semana-17` (required checks `cambios`, `regresion`, `sin-api`): every test of `tests/` with the CI database and the real Collector
(no skipped tests allowed), week 14's ephemeral Keycloak with the approver roles and real PKCE tokens, then the mini eval with the API
(`ci/eval_ci.py`, Haiku 5.5 `low`, a $0.30 cap per run): week 13's 10 CI tasks × ES/EN scored on success, trajectory (read from the spans)
and cost; 3 guardrail attacks; 1 HITL scenario in both languages; 1 budget-exhaustion case. Security as in section 3. Redacted evidence is
uploaded as an artifact and scanned for secrets.

Thresholds come from two CI runs in calibration mode with week 10's rule and a false alarm of at most 10 %: **success 0.85** (runs 0.95 and
0.90, false alarm 5.8 %) and **trajectory 0.90** (runs 1.00 and 0.95, 2.8 %). The first enforcing run passed with 0.95 and 0.95. Every
security count was 0 in all three runs ([`ci_calibracion.md`](resultados/ci_calibracion.md)).

## 5. Costs

Real API spend of the week, every run authorized first: activity 4 $0.2715, activity 5 $0.2972, activity 6 $0.0553, activity 7 $0.2356,
activity 10 $0.3220 (one local run and three CI runs, $0.0772 to $0.0836 each). Activities 1 to 3, 8 and 9: $0. Total **$1.18**.
Activities 6 to 10 ran under a standing authorization of $2 and used $0.61 of it.

## 6. Run it

```bash
cd semana-17
uv sync --group semana17
./observabilidad/arrancar.sh                        # Langfuse on 127.0.0.1:3100 and the Collector on 4317/4318 (secrets in .secretos.env)
uv run --group semana17 python -m pytest -q tests   # no API
uv run --group semana17 python ci/eval_ci.py --dir /tmp/eval17 --simular              # the CI mini eval, $0
uv run --group semana17 python -m tablero.exportar   # the dashboard snapshot
uv run --group semana17 python -m tablero.preguntar tarea c08-es                     # the runbook
./observabilidad/arrancar.sh --detener               # or --borrar to delete containers, volumes and traces
```
