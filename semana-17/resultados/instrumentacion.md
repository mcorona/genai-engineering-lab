# Activity 3: LegacyBridge instrumented end to end

Measured on 2026-11-03 on the Mac, **$0 and no model call**: the model is scripted, everything else is real (the week 13
agent loop, the week 14 MCP client, a Streamable HTTP server behind the OAuth boundary, PostgreSQL with the legacy schema, the
MCP SDK's own spans, the Collector of activity 2 and Langfuse 4.72.0). The numbers come from
[`instrumentacion.json`](instrumentacion.json), written by
[`instrumentacion/verificar_langfuse.py`](../instrumentacion/verificar_langfuse.py) (it needs the activity 2 stack, so it runs on the
Mac), or from [`tests/test_instrumentacion.py`](../tests/test_instrumentacion.py), which runs in CI.

| File | What it is |
|---|---|
| [`instrumentacion/esquema.py`](../instrumentacion/esquema.py) | The **locked span shape**: every attribute the lab writes, with a validator; the only door is `fijar()` |
| [`instrumentacion/trazas_agente.py`](../instrumentacion/trazas_agente.py) | `invoke_agent` / `chat` / `execute_tool` around the week 13 loop (wraps its `api`, its tools source and `resolver`) |
| [`instrumentacion/trazas_cliente.py`](../instrumentacion/trazas_cliente.py) | `ClienteInstrumentado`: the week 14 client keeps the trace context across its session thread |
| [`instrumentacion/trazas_servidor.py`](../instrumentacion/trazas_servidor.py) | `authorize`, `handle_tool` and `SELECT legado` on the server, continuing the agent's trace (`instrument()` / `uninstrument()`) |
| [`instrumentacion/modelo_guionado.py`](../instrumentacion/modelo_guionado.py) | The scripted model: fixed turns with fixed `usage` and latency |
| [`instrumentacion/laboratorio.py`](../instrumentacion/laboratorio.py) | The bench shared by the tests and the Langfuse check |

No file of week 13 or 14 was edited: the instrumentation wraps the injectable pieces of the loop (`api`, tools source), subclasses
the client, and patches the server in the style of the OTel instrumentors.

## The span tree of one task

```
invoke_agent legacybridge                                   AGENT       who, task, tenant, budget, outcome, run totals
├─ chat claude-haiku-5-5                                    GENERATION  tokens (cache included), cost, finish reason
├─ execute_tool legado__describir_esquema                   TOOL        arguments as size + keyed hash, status
│   └─ MCP send tools/call describir_esquema   (MCP SDK)    SPAN        traceparent in `_meta`
│       ├─ authorize                                        SPAN        token, scopes required / granted / missing, decision
│       └─ tools/call describir_esquema        (MCP SDK)    TOOL
│           └─ handle_tool describir_esquema                SPAN        size + keyed hash of the arguments, status, result size
├─ chat claude-haiku-5-5
├─ execute_tool legado__ejecutar_sql  → … → handle_tool ejecutar_sql → SELECT legado     db.*, query size + keyed hash, rows, role
└─ chat claude-haiku-5-5
```

15 spans in one trace in the main scenario (1 agent, 3 chat, 2 tool, 2 MCP client, 2 authorize, 2 MCP server, 2 handle_tool, 1 SQL).
Langfuse stores 15 observations with the same ids, the same parents and the types above.

## The four bullets of the plan

| Plan bullet | Result | Source |
|---|---|---|
| Span tree shape matches the locked schema | The tree above, asserted node by node; **every attribute of every span of 7 scenarios is in `esquema.py`** (67 keys: 26 agent, 19 chat, 11 tool, 9 authorize, 8 handle_tool, 9 SQL, plus the SDK's) or fails the test; an unknown span name fails too | `test_la_forma_del_arbol…`, `test_ningun_atributo…` |
| Parent/child links cross the MCP boundary | `MCP send tools/call X` is the child of `execute_tool`; `tools/call X` **and** `authorize` are its children; `handle_tool` and `SELECT` follow. One trace id from the agent to the SQL. Without the fix the same run puts all of them in other traces (control test) | `test_los_enlaces…`, `test_sin_propagar…` |
| Token and cost attributes add up to run totals | Input 1980 + 1600 cache read + 800 cache creation, output 310, cost $0.000353: the sum of the three `chat` spans equals the agent span's totals and the loop's own `Resultado`. Same numbers in Langfuse, per generation | `test_los_tokens_y_el_costo…`, `principal` in `instrumentacion.json` |
| No prompt, rows, token or personal value with content capture off | 8 canaries (email, tax ID, phone, SQL literal, prompt, DSN, API key, a motive), the 2 JWTs of the run, the database password, the returned row values and the plain subject: **none in any name, attribute, event or status of any span**, nor in Langfuse or the Collector's file, and no `****` either (no false positive). With `SPAN_ONLY` the lab layer still records none | `test_con_la_captura…`, `test_la_capa…`, `privacidad` |

## What is recorded, and what it deliberately is not

| Span | Recorded | Never recorded |
|---|---|---|
| `invoke_agent` | agent, model, task id, language, tenant, **keyed hash** of the token subject (`user.id`), budget (steps, tool calls, tokens, seconds, output tokens), outcome and reason, run totals (steps, tool calls, errors, tokens, cache tokens, cost) | the task text, the answer |
| `chat` | provider, model, reasoning level (`low`), max tokens, response id and model, finish reason, **total** input tokens, output tokens, cache read and creation, cost, step number; latency is the span's duration | messages, system prompt, tool definitions |
| `execute_tool` | tool name (or `_unknown` if the model invented it), `tool_use` id, step, size and keyed hash of the arguments, result size, status, error type | arguments, results |
| `authorize` | decision (`allow` or `deny_*`), MCP method, tool, scopes required / granted / missing, client, user hash | the token, the headers |
| `handle_tool` | tool, size and keyed hash of the arguments, result size, status, error type, user hash | arguments, results |
| `SELECT legado` | `db.system.name`, `db.namespace`, operation, rows returned, tables named, database role, **size and keyed hash of the SQL** | the SQL text, the rows, the error message |

The hash is HMAC-SHA256 with a salt (`LAB_OBS_SALT`), not a plain SHA-256: a dictionary of `analista` or `SKU-0009` does not break it.
The agent's hash of the arguments equals the server's, which shows the arguments did not change on the way (checked).

## Failures show where they happened

| Scenario | What the trace shows (Langfuse, level `ERROR`) |
|---|---|
| `error_sql` (a wrong column, then a fix) | `execute_tool`, `handle_tool`, the SDK tool span and `SELECT legado` of the first attempt are `ERROR` with `error.type = error_sql`; the second attempt is clean; the run ends `respondida` with `tool_errors = 1` |
| `sin_permiso` (a stale catalog asks for a tool the token no longer allows) | `authorize` is `ERROR` with `deny_insufficient_scope` and `scopes.missing = legado:compras:proponer`; nothing after it ran (no `tools/call`, no `handle_tool`, no SQL) |
| `api_falla` (the second model call raises an error that echoes a DSN, an API key and an email) | the `chat` span and the agent span are `ERROR` with only the class name (`RuntimeError`) and `error`; the message is nowhere |

A profile that never sees the tool does not reach the server at all: the call dies in the client as `_unknown` (tested).

## Findings that change later activities

1. **The MCP SDK carries the trace context in `params._meta`, not in HTTP headers.** The boundary (`Frontera`) answers 401/403
   before the SDK sees the request, so `authorize` has to read the context from the body: `PeticionASGI` keeps a copy of the body
   the boundary reads anyway. A request without `_meta` starts a new trace. Every request that reaches the boundary gets exactly one
   `authorize` span (tested against the boundary's own request log).
2. **The thread hand-off of the week 14 client breaks the trace** (activity 1 finding, now fixed and pinned by a control test): the
   coroutine runs in the session task, whose context is the one from when the session was opened. `ClienteInstrumentado` re-attaches
   the caller's context inside it.
3. **`gen_ai.tool.name` has a side effect in Langfuse.** Any span carrying it becomes a TOOL observation named after the tool. The
   first version put it on `authorize` and `handle_tool`: 4 TOOL observations per call and no `authorize` by name. They now use
   `lab.tool.name`. Two TOOL observations per call remain on purpose: the agent's `execute_tool` (named `legado__…`) and the SDK's
   server span (named `…`); the dashboards of activity 8 must count one of them.
4. **Langfuse subtracts cached tokens from `gen_ai.usage.input_tokens`** (activity 2). The spans therefore carry the TOTAL input,
   as the OTel conventions define it, and Langfuse stores the uncached part: scripted 1180 uncached + 800 cache creation became
   `input 1180, input_cache_creation 800, total 2044`. The probe of the two names for cache creation shows Langfuse 4.72.0 reads both
   `gen_ai.usage.cache_creation.input_tokens` (semconv) and `gen_ai.usage.cache_write.input_tokens` (util-genai 1.3b0): the semconv
   name is the one locked, so the mismatch of activity 1 costs nothing here.
5. **The MCP SDK server calls its own list handler while serving a `tools/call`** and records it as a root `SERVER` span named
   `tools/list`, in a trace of its own and with no HTTP request behind it. The main scenario has 2, one per call. They are noise in
   Langfuse (the trace list shows them); a Collector `filter` on root `tools/list` spans is for activity 9. The session's discovery
   requests (`server/discover`, `tools/list`, `resources/read` when the client opens) are separate traces for the same reason.
6. **The SDK client turns the HTTP 403 into JSON-RPC `-32603`.** Its span says `Server returned an error response` and nothing about
   scopes; only the server's `authorize` span says why.
7. **The span's cost uses `semana-07/prices.json` (input and output only).** The file has no cache rates, so cache tokens are reported
   but not priced; the loop does not use caching, so the cost is exact today. `langfuse.observation.cost_details` makes Langfuse show
   the same total (it would otherwise price the model itself).
8. **Reasoning tokens are not a separate number.** The loop reads input, output and cache fields only; the effort level (`low`) is on
   every `chat` span. If the API counts thinking inside `output_tokens` it is already in the totals; that is checked on the first
   real-model run (activity 4).
9. **Locked shape, ready for the allowlist.** `esquema.claves_permitidas()` gives the 67 keys. Passed through the Collector's real
   `redaction` with `allow_all_keys: false` and exactly those keys (plus the resource's), **no attribute of a real run is lost**, and
   with the current pipeline **none is masked** (no false positive). Activity 9 switches the Collector to that allowlist, which also
   closes the list gap of activity 2: the only list left is `gen_ai.response.finish_reasons`, with a fixed vocabulary.

## What this does not cover

- **No real model.** The `usage` numbers and the latencies are scripted inputs; the tests check that the spans add up to them and last
  at least as long. Activities 4 to 7 run the real model (each with its own estimate and authorization).
- **The optional comparison with LangGraph or Strands was not run.** Activity 1 measured them (LangGraph: 0 native OTel spans, Strands:
  3 spans); the same scripted task through them would need a scripted model per framework and was left out of this activity.
- **One process, one resource.** Agent, client and server share `service.name = legacybridge` in the lab; production would export the
  server from its own service. Only the Streamable HTTP transport is instrumented (stdio has no boundary).
- **Tool calls in one turn run in sequence** (the loop does that); concurrency across tasks is not tested.
- **The server's span name `tools/call X` comes from the request** and is not under the lab's control; the Collector masks patterns in
  span names (activity 2), and a name that matches none passes. Not measured with a hostile name; activity 9 decides.
- **Per-tenant Langfuse projects and retention** are still open (activity 9); `lab.tenant.id` is a single value here.
