# Phase 4 · Week 17: reliability of agents in production

Repo: `mcorona/genai-engineering-lab`. Folder: `semana-17/`. Each activity closes with a PR, green checks and a merge
before moving on to the next. Documentation goes in separate PRs.

- **Topic:** reliability of agents in production:
  - human-in-the-loop;
  - guardrails;
  - token budgets;
  - trajectory evals;
  - observability with OpenTelemetry GenAI and Langfuse.
- **Practice:** a **trace dashboard and a trajectory eval for LegacyBridge**. The week 13 agent runs over the week 14
  MCP server (OAuth, least privilege) and is instrumented end to end: agent → model → MCP client → MCP server →
  database. Every run leaves a trace that can be audited, scored and charged.
- **Criterion 17 (root README):** human-in-the-loop, guardrails and token budgets applied; a trajectory eval and a
  trace dashboard with OpenTelemetry GenAI or Langfuse.
- **Why it matters for clients:** weeks 13 to 16 measured *whether* the agent answers well. A client running it in
  production also asks other questions:
  - why it did what it did;
  - what each task costs;
  - who approved a consequential action;
  - how a regression would be noticed.

  This week turns the agent into something that can be operated, and the dashboard becomes a deliverable of the
  "AI Opportunity & Risk Assessment" service.

## What is reused from weeks 10 to 16

- **The agent and its tasks:**
  - the week 13 loop agent and its Claude Agent SDK version;
  - the 84 golden tasks (42 ES, 42 EN) with execution-based verification;
  - the 10-task CI subset.
- **The remote MCP server:** the week 14 server (Streamable HTTP, Keycloak OAuth with PKCE and an RFC 8707
  audience, scopes, a database role per profile). Also its poisoning cases (38) and the client gateway defenses.
- **Consequential actions:** `proponer_orden_compra` writes only `PENDING_APPROVAL` (week 13). The approval that a
  person must give is still missing, and this week adds it.
- **Week 15 frameworks:** LangGraph `interrupt` and checkpointing as the reference for pausing and resuming; Strands
  and LangGraph native OpenTelemetry as a comparison.
- **Week 16:**
  - the read-only guard (hooks that fail closed, every block logged with a hash);
  - the pattern of a $0 rehearsal before any paid run;
  - evidence uploaded as a CI artifact;
  - redaction (no `init`, `~` instead of the home path, `<tmp>`);
  - the week 10 threshold rule with false-alarm control.
- **Security criteria (no threshold):** 0 writes outside `PENDING_APPROVAL`, 0 leaks, 0 instructions obeyed.
  The week adds one more: **0 secrets or personal values in traces**.

## Default decisions

- **Standard:** OpenTelemetry GenAI semantic conventions for the span model:
  - `invoke_agent {agent}`, `chat {model}` and `execute_tool {tool}`;
  - `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.*`,
    `gen_ai.agent.name` and `gen_ai.tool.name` / `gen_ai.tool.call.id`.

  As of September 2026 every `gen_ai.*` attribute is still **Development**. The GenAI and MCP conventions moved to
  the `semantic-conventions-genai` repo, with schema `gen-ai/1.42.0` and no tagged release. Therefore:
  - the instrumentation library and the schema it targets are pinned;
  - a test locks the span shape the lab emits, so a convention change is a visible diff, not a silent break.
- **Backend:** **Langfuse v4 self-hosted** with Docker Compose: web, worker, PostgreSQL ≥ 15, ClickHouse ≥ 25.12,
  Redis ≥ 7 and MinIO.
  - Traces come in over OTLP HTTP at `/api/public/otel/v1/traces`, with Basic auth (public and secret key).
  - Self-hosted, because a client's legacy data must not leave their network. Langfuse Cloud is documented only as
    an option.
- **Collector in the middle:** an OpenTelemetry Collector between the agent and Langfuse. It does three jobs:
  - **redaction** before export (attributes processor and transform rules for DSNs, tokens, emails, phones and tax
    IDs);
  - fan-out to a **file exporter**, which CI uses to check traces without running Langfuse;
  - tail sampling, kept optional.

  Message content capture is **off by default**. Prompts and completions are captured only in the lab, with
  synthetic data, and never in CI artifacts.
- **Trace propagation across MCP:** a W3C `traceparent` from the client to the week 14 server. Server spans
  (`execute_tool` on the server side, SQL with `db.*` attributes) then join the same trace. The `sub` of the token is
  recorded as a hash, never the token.
- **Budgets are enforced, not just reported:**
  - per task: tokens and USD, estimated before each model call as in the week 16 computer use loop;
  - per session and per tenant per day.

  On reaching a budget, the agent stops with a partial, honest answer, or degrades to Haiku where that is allowed.
  The budget decision is a span event.
- **Guardrails in three places, each one a span event with its decision:**
  - **input:** injection and scope;
  - **tool:** allowlist, argument validation and the SQL guard;
  - **output:** personal data, grounding in tool results, refusal to invent figures.

  Each guardrail is measured twice: its block rate on attacks, and its **false-positive rate on the golden tasks**.
  A guardrail that breaks good answers is not adopted.
- **Human-in-the-loop for consequential actions only.** A purchase-order proposal pauses the run, persists its
  state, and waits for an approver with a role in Keycloak (not the requester). It resumes or rejects, with a
  timeout, and every step is in the trace. In evals and CI the approver is simulated with fixed decisions.
- **Trajectory eval with deterministic graders on the trace.** It reads the spans (from the file exporter or the
  Langfuse API), and scores against a reference trajectory per task:
  - tool precision and recall;
  - order where order matters;
  - redundant and failed calls;
  - steps against the reference;
  - recovery after a tool error.

  An LLM judge is used only for what code cannot decide, and only after it is validated on known bad trajectories
  (the week 11 lesson with RAGAS). Scores are written back to Langfuse as `scores` on each trace.
- **Model and cost:**
  - Haiku 5.5 `low` for the agent in the evals and in CI, the same as weeks 13 to 15;
  - Sonnet only in a calibration comparison, if it is needed;
  - anything that uses the API is estimated and authorized first, with a cap per run.
- **New folder:** `semana-17/**` is in the `evals-semana-06` paths (done during preparation). Otherwise the required
  `regresion` check blocks the merge (week 16 log).

## Preparation (done before activity 1)

| Item | Where |
|---|---|
| Candidate pins: Python packages (OpenTelemetry 1.45.2 / 0.66b2, Langfuse SDK 5.1.0), images (Langfuse 4.72.0, ClickHouse 26.3.62.3, Collector contrib 0.164.0, Keycloak 26.8.1), the port map and Docker resources | [`preparar/versiones.json`](preparar/versiones.json) |
| A `semana17` dependency group, locked | `pyproject.toml`, `uv.lock` (`uv sync --group semana17`) |
| A readiness check: packages, Docker memory and disk, images, ports, lab database, week 13 data, CI paths. No model, $0 | [`preparar/verificar_entorno.py`](preparar/verificar_entorno.py) |
| Pre-pulling the images (about 3 to 4 GB) | [`preparar/jalar_imagenes.sh`](preparar/jalar_imagenes.sh) |
| `semana-17/**` in the paths of the required `regresion` check | `.github/workflows/evals-semana-06.yml` |
| `eval-semana-17` workflow without API (CI database, readiness check, `semana-17/tests`). Each activity adds its tests | `.github/workflows/eval-semana-17.yml` |
| Secrets and raw traces ignored | `.gitignore` (`semana-17/**/.secretos.env`, `semana-17/observabilidad/datos/`) |

**Port map.** The lab already uses PostgreSQL 5432, Keycloak 8180 and the week 14 MCP server 8014 (LiteLLM uses
4000). Langfuse web goes to **3100** and the Collector to **4317/4318** (health check on 13133). Langfuse's own
PostgreSQL, ClickHouse, Redis and MinIO get **no host port**: they live on the Compose network only. That avoids the
clash with the lab's 5432 and keeps them unreachable from outside.

**Images to pin by digest in activity 1:** MinIO (Chainguard publishes only `:latest` for free), PostgreSQL 17 and
Redis 7 (major tags, as in the Langfuse compose file).

## Dependencies and parallel work

```
1 baseline ──► 2 stack ──► 3 instrumentation ──► 4 budgets ──┐
                                   │                5 guardrails ├──► 8 dashboard ──► 10 CI, README, criterion 17
                                   │                6 HITL ──────┤
                                   │                7 trajectories┘
                                   └──────────────► 9 security of observability
```

Activities 4 to 7 need the instrumentation (3) to put their decisions in the trace, but each has a first part that
needs no trace. Those parts can start in parallel with activity 1:

| Can start now | Part | Needs |
|---|---|---|
| 7 | Reference trajectories for the 84 tasks, and the deterministic graders tested on hand-made good and bad trajectories | `semana-13/golden/tareas_*.jsonl` and the per-task results of week 13 (`eval_*_detalle.jsonl`: steps, tools, minimum steps) |
| 4 | The cost distribution of the 84 tasks (p50, p95, max) and the budget percentiles. The budget logic, tested with a scripted model | The week 13 per-task results (`costo_usd`, `tokens_in`, `tokens_out`) |
| 5 | The deterministic guardrail layer (input, tool, output) and its harness: block rate on the attack cases and false positives on the golden tasks, run offline on saved inputs and outputs | Weeks 13 and 14 security cases and the week 13 saved answers |
| 6 | The approval state machine (request → approve/reject/expire), its persistence, and a distinct approver role in the Keycloak realm, tested without the model | `proponer_orden_compra` (week 13) and the week 14 realm |

What must wait: anything that writes spans (3 first), the dashboard (needs traces from 4 to 7), the security of
observability (needs the stack and the instrumentation), and CI with API (last).

## Activities

### 1. Baseline: current observability capabilities
- Verify on the Mac and in the container, with versions pinned:
  - **OpenTelemetry GenAI** semantic conventions: current names and status, and the content capture variables of
    the chosen instrumentation;
  - the Python SDK and the Collector (`otelcol-contrib`) versions;
  - **Langfuse v4**: images, minimum versions of its dependencies, the OTLP endpoint and auth, how
    `gen_ai.*` maps to observations, scores, the dashboards API and data retention;
  - native OpenTelemetry in the Claude Agent SDK and Claude Code (`CLAUDE_CODE_ENABLE_TELEMETRY`), LangGraph and
    Strands;
  - W3C trace propagation over Streamable HTTP in the MCP SDK.
- A matrix in which each capability is marked M (measured), D (documented) or N (not verified), as in week 16.
- Confirm `semana-17/**` in the `evals-semana-06` paths (added during preparation).
- Replace the candidate pins in `preparar/versiones.json` with the verified ones, and the floating images with digests.
- **Deliverable:** `resultados/linea_base.md` and `linea_base/verificar.py` (checks without the model).
- **Time:** ~1.5 h. **Cost:** $0.

### 2. Observability stack: Collector and Langfuse self-hosted
- Docker Compose with Langfuse v4 (web, worker, PostgreSQL, ClickHouse, Redis, MinIO) and an OpenTelemetry
  Collector. Random secrets in a git-ignored `.secretos.env`, as in the week 14 Keycloak setup. Pinned image tags,
  `arrancar.sh` and `--borrar`.
- Collector pipeline:
  - an OTLP receiver;
  - redaction processors;
  - a batch processor;
  - exporters to Langfuse (OTLP HTTP with Basic auth) and to a JSONL file.
- **Tests:**
  - a synthetic trace arrives in Langfuse and in the file;
  - a canary DSN, token, email and tax ID in span attributes come out redacted in both;
  - the stack is up again after a restart, and fully removed with `--borrar`.
- **Time:** ~2 h. **Cost:** $0.

### 3. Instrumenting LegacyBridge end to end
- Agent spans:
  - `invoke_agent legacybridge` at the root, carrying task id, language, tenant and user (as a hash), the budget
    and the outcome;
  - `chat claude-haiku-5-5` per model call, with tokens including cache read and reasoning, cost and latency;
  - `execute_tool {tool}` per call, with arguments as size and hash only, and status.
- MCP:
  - client spans, with `traceparent` injected in the Streamable HTTP request;
  - server spans that continue the same trace: authorization, scope decision and a SQL span with `db.*`
    attributes.
- Optional: the same task in LangGraph or Strands with their native instrumentation, to compare the span trees.
- **Tests (no API, scripted model):**
  - the span tree shape matches the locked schema;
  - parent and child links cross the MCP boundary;
  - token and cost attributes add up to the run totals;
  - no prompt, result rows, token or personal value is in any attribute with content capture off.
- **Time:** ~2 h. **Cost:** $0, with a scripted model and the trace checked in Langfuse.

### 4. Token and cost budgets
- A budget per task (tokens and USD), per session and per tenant per day, held in the agent (and in a small store for
  the per-day budgets).
- The loop checks before each model call, with the upper estimate of week 16 (the whole previous prompt plus the
  maximum output).
- When a budget is reached:
  - the agent stops and gives a partial answer that says why;
  - where a policy allows it, it degrades to a cheaper model;
  - it never retries silently.

  Each decision is a `gen_ai` span event with the spend and the limit.
- **Eval:**
  - the cost distribution of the 84 tasks (p50, p95, max) sets each budget at a calibrated percentile;
  - then measure success, partial answers and cost with the budget on;
  - the spend never crosses the cap, in any task, which is a security-style criterion with no threshold.
- **Time:** ~1.5 h. **Cost:** ~$0.15 (84 tasks × k = 1 with Haiku, reusing week 13 costs; authorized first).

### 5. Guardrails
- **Input:**
  - injection and out-of-scope detection on the user request and on the tool results that come back (data is not
    instructions);
  - a deterministic layer first; a classifier only if it pays its false positives.
- **Tool:**
  - a policy check before each MCP call: allowlist, argument schema, the SQL guard, and tenant and scope
    consistency with the token;
  - with the week 14 gateway defenses for tool poisoning.
- **Output:**
  - personal values blocked;
  - figures must come from tool results (grounding checked against the trace);
  - a refusal message when evidence is missing.
- Every decision is a span event (`guardrail.name`, `decision`, `reason` as a hash or a category).
- **Eval:**
  - **attacks:** the 38 week 14 poisoning cases and the week 13 security cases, by block rate per guardrail, with
    0 obeyed and no threshold;
  - **false positives:** the 84 golden tasks with the guardrails on against off. A guardrail with more than a set
    false-positive rate (fixed before running) is rejected or tuned.
- **Time:** ~2 h. **Cost:** ~$0.30 (authorized first).

### 6. Human-in-the-loop for consequential actions
- `proponer_orden_compra` moves from writing `PENDING_APPROVAL` to an explicit approval step:
  1. the run pauses and its state is persisted (a checkpoint, LangGraph-style, in PostgreSQL);
  2. an approval request records what, why, how much, which evidence and who asked;
  3. an approver with a Keycloak role that is not the requester approves or rejects;
  4. the run resumes, with a timeout that expires the request.
- Every step is in the trace (`hitl.request`, `hitl.decision`, the waiting time), and so is the identity of the
  approver (as a hash).
- **Eval (simulated approver):**
  - 0 orders confirmed without an approval, which is a security criterion;
  - a rejection leaves no side effect;
  - a timeout expires cleanly;
  - an approver who is also the requester is refused;
  - instructions in data that say "auto-approve" are not followed;
  - the latency and cost added by the pause are measured.
- **Time:** ~2 h. **Cost:** ~$0.10 (authorized first).

### 7. Trajectory eval
- **Reference trajectories** for the 84 tasks, derived from the golden SQL and the tools each task needs:
  - the required tools;
  - the allowed extra tools;
  - the order constraints;
  - the maximum reasonable steps;
  - the forbidden tools.

  They are frozen with a hash manifest, like the other golden sets.
- **Deterministic graders on the trace:**
  - tool precision and recall;
  - in-order match where required;
  - redundant calls;
  - failed calls and recovery;
  - steps against the reference;
  - forbidden tools (0 allowed).
- An **LLM judge** is used only for "was the plan reasonable" on ambiguous tasks, and only if it passes a validation
  on 10 or more hand-made bad trajectories first.
- **Validate the metrics on known failures** before using them: trajectories with a missing tool, the wrong order,
  loops and a forbidden call must each score as bad.
- **Analysis:**
  - success against trajectory quality (correct answers with wasteful trajectories, and the reverse);
  - the loop agent against the Claude Agent SDK agent;
  - before and after the guardrails and budgets;
  - with confidence intervals as in week 13.
- Scores are written back to Langfuse on each trace.
- **Time:** ~2 h. **Cost:** ~$0.40 (84 tasks × 2 agents with Haiku; authorized first).

### 8. LegacyBridge trace dashboard
- Langfuse dashboards (defined as code where the API allows it, otherwise documented step by step):
  - **cost:** per task, per tenant and per day, against the budget;
  - **latency:** p50 and p95, per step type (model, tool, MCP server, SQL);
  - **tokens:** input, cache read, output and reasoning;
  - **tool errors and recovery;**
  - **guardrail blocks** by type;
  - **HITL:** requests, waiting time and decisions;
  - **trajectory and success scores** over time.
- A static export for the repo (`resultados/tablero/`) generated from the Langfuse API: charts and tables from a
  fixed eval run. The dashboard is local, so the repo carries a reproducible snapshot and the script that builds it.
- **Runbook:** how to answer five operator questions from the dashboard in under a minute each:
  - why did task X fail;
  - what did tenant Y spend today;
  - which tool is slowing things down;
  - who approved order Z;
  - did yesterday's change make trajectories worse.
- **Time:** ~1.5 h. **Cost:** $0, on the traces of activities 4 to 7.

### 9. Security and privacy of the observability
- **Canaries:** a DSN, an OAuth token, an API key, emails, phones and tax IDs are seeded in data, prompts and tool
  results. None may appear in Langfuse, the Collector file or the CI artifact, with content capture off and on
  (redaction must hold in both cases). No threshold.
- **Access:**
  - Langfuse projects per tenant, so one tenant's traces are invisible to another's keys;
  - keys out of the repo;
  - a retention policy configured and documented.
- **Prompt injection through traces:** a trace viewed by an LLM-powered tool, or a judge reading trace text, treats
  it as data. Covered by the week 16 cases.
- **Time:** ~1 h. **Cost:** $0.

### 10. CI, README and criterion 17
- `eval-semana-17` workflow:
  - ephemeral PostgreSQL, Keycloak and the Collector (file exporter). Langfuse stays out of CI: its ClickHouse
    stack is heavy, and the trace checks run on the OTLP file;
  - tests without API: span schema, propagation, redaction, budgets, guardrail decisions, HITL state machine,
    trajectory graders on fixed traces;
  - a mini eval with API: the 10-task subset with Haiku, scored on success, trajectory and cost, plus 1 HITL case,
    3 guardrail attacks and 1 budget-exhaustion case;
  - thresholds calibrated with the week 10 rule and false-alarm control;
  - security without a threshold (writes, leaks, instructions obeyed, secrets in traces, orders without approval,
    spend over a cap): any failure breaks the PR;
  - redacted evidence uploaded as an artifact.
- `semana-17/README.md`: architecture (span model and pipeline), results, dashboard snapshot, security, costs, and
  how to run the stack.
- Root README: criterion 17 `[x]` and the phase status.
- 100% validation against the plan bullets.
- **Time:** ~2 h. **Cost:** ~$0.10 to $0.20 per CI run (2 calibration runs: ~$0.40). Documentation goes in a
  separate PR, $0.

## Summary

| | |
|---|---|
| Estimated total time | ~17.5 h |
| Estimated API cost | ~$1.00 to $1.50 for activities 4 to 7, plus ~$0.40 for CI calibration. Each paid run is authorized first, with a cap |
| Cloud | None. Langfuse and the Collector are self-hosted in Docker. Langfuse Cloud is documented only as an option |
| Risks | GenAI conventions still Development (pin and lock the schema); Langfuse v4 needs ClickHouse ≥ 25.12 and about 4 GB of RAM (run it on the Mac, not in CI); content capture leaking data (off by default, redaction tested with capture on); guardrail false positives hurting success (measured on the golden tasks before adoption); HITL tests needing a real second user (simulated approver with a distinct Keycloak role); trajectory references too strict for valid alternative plans (allowed extras and order only where it matters) |

## Log

- 2026-11-02: plan created after week 16 closed (criterion 16 verified, PR #125).
- 2026-11-02: preparation. Candidate pins, the `semana17` dependency group, the readiness check, image pre-pull, the
  `regresion` paths and an `eval-semana-17` workflow without API. Activities 4 to 7 have parts that can start in parallel
  with activity 1 (see Dependencies).
- 2026-11-03: activity 1, baseline. `linea_base/verificar.py` runs 10 probes with no model: 9/9 on the Mac (with a
  throwaway Langfuse v4), 8/8 in the container, and Claude Code telemetry on the subscription. `resultados/linea_base.md`
  has the M/D/N matrix, checked by `tests/test_linea_base.py`. Pins are verified and all 8 images carry a digest.
  Three findings go to activity 3: the agent span and the MCP client spans land in different traces
  (`ClienteSeguro` loses the context), Langfuse subtracts cached tokens from `input_tokens` (so they must be added
  before exporting), and the cache token names differ between libraries. Langfuse data retention is not in the
  self-hosted plans we can use (activity 2).
- 2026-11-03: activity 2, observability stack. `observabilidad/` has the Compose file (Langfuse v4 with its 5 backing
  services and the Collector, images by digest, 4 host ports all on 127.0.0.1), the Collector pipeline and `arrancar.sh`
  (`--estado`, `--detener`, `--reiniciar`, `--borrar`). `verificar_stack.py` measures it end to end on the Mac: a trace
  reaches Langfuse and the file with 0 of 7 canaries, the stack survives a restart, a Langfuse outage loses nothing and
  `--borrar` leaves 0 containers, volumes and networks (`resultados/stack.md`). Two findings go to activities 3 and 9:
  `redaction` does not read span names, status messages or event names (added `transform/redaccion`), and nothing
  redacts list-valued attributes (known gap; the allowlist mode closes it once the span shape is locked).
- 2026-11-03: activity 3, LegacyBridge instrumented end to end ($0, scripted model). `instrumentacion/` locks the span
  shape (`esquema.py`: 67 attribute keys with validators, no lists, no free text, keyed hashes for users and arguments)
  and wraps the week 13 loop (`invoke_agent` / `chat` / `execute_tool`), the week 14 client (it keeps the trace context
  across its session thread) and the server (`authorize`, `handle_tool`, `SELECT legado`) without editing their files. One
  task is 15 spans in one trace, the same 15 observations in Langfuse; tokens, cost and latency add up to the run totals;
  no canary in any span, in Langfuse or in the Collector's file (`resultados/instrumentacion.md`). Findings for later
  activities: the MCP SDK carries the trace context in `_meta`, not in HTTP headers; `gen_ai.tool.name` turns any span into
  a TOOL in Langfuse; the SDK server emits one orphan root `tools/list` span per call (Collector `filter`, activity 9);
  the optional LangGraph/Strands comparison was not run.
- 2026-11-03: the two optionals of activities 2 and 3, before activity 4 ($0, no model call).
  Tail sampling: `observabilidad/muestreo.yaml` is an overlay merged as a second `--config` with `arrancar.sh --muestreo`
  (errors, tasks not answered and traces over 60 s kept in full, 10 % of the rest); the default stack keeps every trace
  because activity 7 scores them all. Measured with Langfuse: 11 of 11 critical traces kept, 6 of 40 plain ones, canary
  absent, default restored (`resultados/muestreo.json`, `resultados/stack.md`). LangGraph/Strands: the same scripted task
  through both, with the real server (`comparacion/`, `resultados/frameworks.md`). Strands continues the trace into the
  server out of the box and counts tokens like the lab, but records prompt, SQL and rows by default (its own switch,
  `gen_ai_unredacted_attributes=`, removes them); LangGraph emits 0 OpenTelemetry spans and the server cannot link its calls.
- 2026-11-03: activity 4, token and cost budgets. `presupuestos/` puts a budget on every model call of the week 13 loop without
  editing it: per task (memory), per session and per tenant per day (SQLite store, reservations in one `BEGIN IMMEDIATE`
  transaction), in tokens and USD, checked before each call with an upper estimate of the prompt (never below the real one in
  930 recorded calls) and capped by a dynamic `max_tokens`. At a limit the task ends with a partial answer that says why; a
  policy can name a cheaper model; nothing is retried. Each decision is a `gen_ai.budget.decision` span event. The caps come
  from the week 13 cost distribution (p99 of a task: $0.0063 and 46,000 tokens). Paid run, authorized first: 84 tasks with the
  budget on cost $0.2344 (the plan said ~$0.15; 84 × the week 13 mean is $0.24): 74 of 84 succeeded (week 13: 78 of 84 on the same
  repetition), 2 were stopped by the budget (both passed 3 of 3 in week 13), and no task, session or day crossed its cap
  (`resultados/presupuestos.md`). Findings: Langfuse v4 does not show span events (they reach the Collector's file; the agent span
  carries `lab.outcome.reason = presupuesto_*`, which is what activity 8 must read); a degrade made the loop price the run at the
  original model (found by the Langfuse check, fixed); upper-bound reservations are conservative under concurrency; one failure
  (`s10-es`) has no budget cause we can find (no response was cut, and even in the worst case the output limit was above the largest
  output recorded in week 13) and is reported as variation, not proved.
