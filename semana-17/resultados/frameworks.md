# Activity 3, optional: the same task through Strands and LangGraph

Measured on 2026-11-03 on the Mac, **$0 and no model call**: the model is scripted (the same turns as the main scenario of
[`instrumentacion.md`](instrumentacion.md)), and the three runs hit the same real MCP server (OAuth boundary, PostgreSQL legacy
schema). What differs is who traces. Nothing was configured for tracing beyond a global OpenTelemetry `TracerProvider`: what
each framework emits by itself is what is measured. The numbers come from [`frameworks.json`](frameworks.json), written by
[`comparacion/comparar_frameworks.py`](../comparacion/comparar_frameworks.py) (it needs the framework venvs of week 15 and, with
`--langfuse`, the stack of activity 2, so it runs on the Mac); [`tests/test_frameworks.py`](../tests/test_frameworks.py) checks the
committed evidence in CI.

| Run | Code | Versions |
|---|---|---|
| Lab | the week 13 loop with the activity 3 instrumentation | `semana-17/instrumentacion/` |
| Strands | [`agente_strands.py`](../comparacion/agente_strands.py): `Agent` + `MCPClient`, scripted `Model` | strands-agents 1.63.0, mcp 2.3.0 |
| LangGraph | [`agente_langgraph.py`](../comparacion/agente_langgraph.py): `create_react_agent` + `langchain-mcp-adapters`, scripted chat model | langgraph 1.2.19, langchain-core 1.7.3, langchain-mcp-adapters 0.3.2, mcp 1.30.0 |

The framework scripts get the token from an environment variable (never an argument, so it is not in `ps`) and run in the week 15
venvs. Both end with a plain text turn instead of the loop's `responder` tool: the harness around the model is not what is compared.

## The span tree of one task

```
Lab (15 spans, one trace)               Strands (18 spans, one trace: 11 from its process + 7 from the server)
invoke_agent legacybridge               invoke_agent Strands Agents
├─ chat                                 ├─ execute_event_loop_cycle
├─ execute_tool …                       │   ├─ chat
│   └─ MCP send tools/call              │   └─ execute_tool describir_esquema
│       ├─ authorize                    │       └─ MCP send tools/call describir_esquema      (MCP SDK)
│       └─ tools/call                   │           ├─ authorize                              (lab, server)
│           └─ handle_tool              │           └─ tools/call describir_esquema           (MCP SDK, server)
├─ chat                                 │               └─ handle_tool describir_esquema      (lab, server)
├─ execute_tool … → … → SELECT legado   ├─ execute_event_loop_cycle
└─ chat                                 │   ├─ chat
                                        │   └─ execute_tool ejecutar_sql → … → handle_tool → SELECT legado
LangGraph: 0 OpenTelemetry spans        └─ execute_event_loop_cycle
(23 runs in LangSmith's format,             └─ chat
 2 tool calls in 2 unrelated traces on the server)
```

Strands also makes 2 spans before the agent starts (`MCP send server/discover`, `MCP send tools/list`): two traces of their own.
Langfuse stores the Strands trace as 18 observations (1 AGENT, 3 GENERATION, 4 TOOL, 10 SPAN), the same 18.

## The comparison

| | Lab | Strands | LangGraph |
|---|---|---|---|
| OpenTelemetry spans by itself | 15 (written by the lab) | 13 (11 in the agent's trace) | **0** |
| Trace continues into the server | yes (after the activity 3 fix) | **yes, out of the box**: the SDK's client span is a child of `execute_tool`, and `authorize`, `tools/call`, `handle_tool` and `SELECT` hang from it | **no**: 2 tool calls, 2 traces, `authorize` has no parent; the server saw 25 spans in 22 traces (one MCP session per call) |
| Attributes inside the locked shape | all (67 keys, tested) | agent 3 of 16, chat 6 of 16, tool 3 of 9; **16 of its 27 distinct keys are in no list of the shape** | none to check |
| Lab keys it never emits | none | agent 23 of 26 (user, tenant, task, budget, outcome, run totals, cost), chat 13 of 19, tool 8 of 11 | all |
| Input tokens | total, cache included | **the same numbers**: 1980, 1220, 1180 (total) | n/a |
| Usage keys on a `chat` span | 4 (`input_tokens`, `output_tokens`, `cache_read`, `cache_creation`) | the same 4 names **plus** duplicates and a sum: `prompt_tokens`, `completion_tokens`, `cache_read_input_tokens`, `cache_write_input_tokens`, `total_tokens` (7 keys for the 3 numbers of the first turn, plus the total) | n/a |
| Content recorded by default | none | **prompt, system prompt, tool arguments and returned rows, as span events** | all of it, in the run tree |
| Cost | the loop's own, from `prices.json` | none: Langfuse prices it | none |

## Findings that change later activities

1. **Strands is the only one of the two whose native spans could be adopted.** It carries the trace context into the MCP request
   (its `MCPClient` merges it into `_meta`, and the SDK's client span becomes the child of `execute_tool`), so the agent's trace
   reaches `authorize`, `handle_tool` and the SQL span with no wrapper. The week 14 client needed one (activity 3, finding 2).
2. **Its default is fail-open.** With nothing configured the task text, the system prompt, the SQL, the tool arguments and the
   returned rows are in span events; the 5 canaries of the task are all in the spans. Through the Collector of activity 2 the email,
   tax id and phone are masked (21 masks), but the prompt marker and the SQL literal reach Langfuse: the pattern masking is a net,
   not a policy. Strands has its own switch, `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_unredacted_attributes=` (an empty list): with it
   **no canary, no SQL, no row and no token is in any span**, none in Langfuse and no mask was needed (0), and the trace still
   continues into the server (the same 18 spans). It is opt-in by environment variable, so a deployment that forgets it leaks:
   the lab's own instrumentation, which cannot write content at all, stays the choice for LegacyBridge, and a team that adopts
   Strands must set the switch and let the Collector allowlist of activity 9 drop what is outside the shape.
3. **Token accounting matches the lab's.** Strands' provider reports the API's uncached input and the cache apart; its tracer adds them
   up for `gen_ai.usage.input_tokens`, so each `chat` span carries 1980, 1220 and 1180, the lab's numbers, and Langfuse stores `input`
   1180, 420 and 380 with the cache in `input_cache_creation` and `input_cached_tokens` (totals 2044, 1316, 1330). The duplicate
   name `cache_write_input_tokens` stays in the first generation's `usageDetails` as a second 800: a dashboard that sums every
   usage key would count it twice (activity 8 must read the named keys).
4. **Two cost sources.** The Strands spans carry no `langfuse.observation.cost_details`, so Langfuse prices them from its own model
   table and prices the cache: $0.000469 for the three generations, against the lab's $0.000353, which covers input and output only
   (`prices.json` has no cache rates). Activity 4 budgets count the loop's own cost and must say so; a dashboard that reads
   Langfuse's cost for a Strands trace reads a different number for the same task.
5. **LangGraph has no OpenTelemetry of its own.** What it builds is a run tree in LangSmith's format (23 runs: chain, llm, tool)
   that holds the prompt, the SQL, the tool arguments and the rows (all 5 canaries are in it). Its way to OpenTelemetry is LangSmith's
   own exporter or an external instrumentor, neither installed in the week 15 environment and neither measured here. Its tools
   reached the real server through `langchain-mcp-adapters` and mcp 1.30.0 (the script tries the real server first, and the
   fallback to canned results was not needed), but with no trace context in the request: the server's spans cannot be tied to the agent's.
6. **Strands' extra spans are noise to filter, not to keep.** `execute_event_loop_cycle` (3) and the discovery spans before the
   agent have no gen_ai operation of the shape; the Collector `filter` of activity 9 is where they go, with the orphan
   `tools/list` spans of activity 3.

## What this does not cover

- **A scripted model.** The `usage` numbers are inputs; Strands' Anthropic provider was fed in the API's own shape, not by the API.
  The first real-model run (activity 4) checks that the real numbers reach the spans the same way.
- **Only Strands' default conventions and its redaction switch.** `gen_ai_latest_experimental` (the newer content and tool attributes),
  `gen_ai_span_attributes_only` and the tool-definition switch were not measured.
- **LangGraph through an external instrumentor** (OpenInference, OpenLLMetry, LangSmith's OpenTelemetry mode) was not measured: none is
  installed. The finding is about what it does with nothing added.
- **One task, one turn at a time.** No errors, no 403, no concurrency through the frameworks; those are measured for the lab's own
  instrumentation in `instrumentacion.md`.
- **The Collector's allowlist** (activity 9) was not applied to these spans; the table above says which keys it would drop.
