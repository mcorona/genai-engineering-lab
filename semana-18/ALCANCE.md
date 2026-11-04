# LegacyBridge v1: scope (week 18, activity 1)

v1 does not add capabilities. It puts the measured pieces of weeks 13 to 17 behind **one bring-up** and **one entry point**, freezes a
version, and proves it with **one gate**. This file fixes what is in and what is out before any v1 code is written.

## What runs today, and how (inventory)

| Piece | Week | How it starts today | Port | Secrets |
|---|---|---|---|---|
| Lab database (PostgreSQL, CI data, legacy schema, `artnot`) | 7, 10, 13 | a container started by hand (`copilot-db`), `semana-07/ci/preparar_base.py`, then two `psql -f` | 5432 | `PG_ADMIN_DSN`, `PG_DSN` in the shell |
| Keycloak (realm `legacybridge`) | 14 | `semana-14/auth/arrancar.sh` | 8180 | `semana-14/auth/.secretos.env` |
| Approver roles in the realm | 17 (act. 6/10) | `python -m aprobaciones.keycloak` (partial import) | — | same |
| MCP server (Streamable HTTP, OAuth) | 14 | `python -m servidor --transporte http --oauth` from `semana-14/` | 8014 | the token comes from Keycloak |
| Purchasing specialist (Strands, A2A, no credentials) | 15 | `python -m multiagente.servidor_compras --emisor … --jwks …` from `semana-15/` in its own virtual env | 8015 | its own Keycloak audience |
| Observability (Collector, Langfuse v4 and its 5 services) | 17 | `semana-17/observabilidad/arrancar.sh` | 3100, 4317/4318, 13133 | `semana-17/observabilidad/.secretos.env` |
| The agent with budgets, guardrails and approvals | 13 + 17 | only from Python (`AgenteAprobable(...)`, the eval runners, the tests) | — | `ANTHROPIC_API_KEY` |
| The multi-agent supervisor | 15 | only from the week 15 eval (`adaptadores/multiagente.py`), LangGraph env | — | — |
| Dashboard, runbook | 17 (act. 8) | `python -m tablero.*` | — | Langfuse keys |
| Client plugin | 16 | `claude plugin install legacy-schema-audit@genai-engineering-lab` | — | a read-only DSN or a token |

## Gaps to an integrated v1

1. **Five start procedures, three secret files, a DSN in the shell.** Nobody outside the lab can bring it up from the README alone.
2. **The agent has no command.** The week 17 stack (instrumented, budgeted, guarded, approvable) is a Python class used by tests and
   runners; a user cannot ask it a question, approve a proposal or open the dashboard from one place.
3. **Two agents that never met.** The week 15 multi-agent (LangGraph supervisor, Strands specialist over A2A) has none of week 17's
   layers, and the week 17 agent has no multi-agent mode.
4. **No version.** There is no tag, no release and no single gate that says "this build is LegacyBridge v1".

## In

- **Bring-up:** `semana-18/legacybridge/arrancar.sh` starts or confirms the database, Keycloak (with the approver roles), the MCP server,
  the purchasing specialist and the observability stack; health checks; one secrets file per machine, generated, never printed;
  `--estado`, `--detener`, `--borrar`.
- **Entry point:** `python -m legacybridge` with `preguntar` (a question, answered with evidence), `aprobar` (list and decide pending
  proposals with the approver's token), `tablero` (export and open the snapshot), `runbook` (the five questions), `demo` (activity 4).
- **Two modes, same commands and same layers:**
  - `simple` (the default): the week 13 loop with week 17's instrumentation, budgets, guardrails and approvals, over the MCP server.
  - `multiagente`: a supervisor built on the same loop and layers whose purchasing step is delegated over A2A to week 15's Strands
    specialist, which holds **no credentials**: the boundary that justifies more than one agent (week 15's rule). The proposal it returns
    is registered by the supervisor through MCP with the user's token, so it still goes through the approval step.
- **Gate (activity 3):** the 84 golden tasks in both modes, the 38 attacks and the 7 approval scenarios against the multi-agent mode,
  week 17's CI thresholds as the floor, security with no threshold; then `v1.0.0` (tag and GitHub release).
- **Demo (activity 4) and the 3-minute English video (activity 5).**

## Out (and why)

- **LangGraph in v1:** the week 15 supervisor stays as a reference. v1's supervisor is the week 13 loop so that one set of layers
  (week 17) covers both modes; week 15 measured the frameworks as ties on success.
- **Cloud deployment (AgentCore, week 15):** v1 runs on one machine; the client's network is the deployment target (week 17's
  "data does not leave the network").
- **New tools or data sources:** none; v1 is the measured scope.
- **A UI for approvers:** the CLI with the approver's token; a UI is a client-specific integration.
- **Langfuse Enterprise features** (project API, retention per project): v1 keeps week 17's substitutes.

## The demo storyline (one paragraph; activity 4 makes it deterministic)

An operations manager asks LegacyBridge, in English, which critical SKUs are below their reorder point; the agent reads the cryptic
legacy schema through the MCP server with her own token and answers with the SQL behind it. She asks it to propose a purchase order for
one of them: in multi-agent mode the purchasing specialist, which has no credentials, drafts it; the system computes the amount, sees it
needs a purchasing manager, and pauses. A note planted in the data tells the agent to approve it automatically; the guardrail removes it
and nothing is approved. The manager approves with her own token, the run resumes and confirms the order. Last, the dashboard shows the
whole thing as one trace, its cost against the budget, and the approval with who decided and how long it waited.

## Cost

Activities 1 and 2: $0. Activity 3: ~$0.60. The demo's live take: ~$0.05. CI calibration: ~$0.40. Cap for the week: $1.50 (authorized).
