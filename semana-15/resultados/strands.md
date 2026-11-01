# Activity 4: the agent in Strands Agents

Code: [`adaptadores/strands.py`](../adaptadores/strands.py) (about 164 lines of code without docstrings; LangGraph: 145). Tests: [`tests/test_equivalencia.py`](../tests/test_equivalencia.py), **the same 15 tests as LangGraph**, run against the week 13 own loop with the same simulated model script and the same week 14 MCP server ($0).

## Same agent, different design

Strands is a model-driven loop: you give it the model, the prompt and the tools, and the framework runs the loop. There is no graph to draw. The week 13 rules go in through **hooks**, the framework's extension mechanism:

| Hook | Week 13 rule it enforces |
|---|---|
| `BeforeModelCallEvent` | Before each model call: 3 tool errors in a row, then steps, total tokens (the cost cap) and time, in the week 13 order. It stops with `cancel`; the cancelled call is not counted as a step |
| `AfterModelCallEvent` | Counts the step, tokens, cost and requested tools; writes the `modelo` trace; `max_tokens` with no tool use stops the run |
| `BeforeToolCallEvent` | `max_herramientas` before each tool; `responder` must be alone in its turn; **interrupt before `proponer_orden_compra`** |
| `AfterToolCallEvent` | Reads each tool's result (the server's structured errors included) and writes the `herramienta` trace |

| Setting | Why |
|---|---|
| `AnthropicModel` (direct, not Bedrock) with `output_config={"effort": "low"}` and the week 13 output tokens | Same model and same request as the week 13 loop and LangGraph |
| `MCPClient` with the user's Bearer token | Week 14 server, protocol 2026-07-28 (activity 1) |
| `SequentialToolExecutor` | Strands runs a turn's tools **concurrently by default**; week 13 runs them in order, and the MCP call order is part of the equivalence test |
| `NullConversationManager` | The default sliding window could trim the conversation; week 13 never does |
| `responder` as a `PythonAgentTool` with week 13's JSON Schema and validation | A valid answer ends the loop with `agent.cancel(after_current_tools=True)` (the old `stop_event_loop` flag is deprecated in 1.63) |
| Reminder | A second invocation with the same text as week 13, then `sin_responder` |
| Human in the loop | `event.interrupt()`; the agent returns `stop_reason="interrupt"` and resumes with `interruptResponse`. Same policies and `decidir` hook as LangGraph |

## Tests (same as activity 3)

| Test | LangGraph | Strands |
|---|---|---|
| Contract equivalence, 7 scripts: same result, MCP calls and model requests | ✅ 7/7 | ✅ 7/7 |
| Limits `max_pasos`, `max_herramientas`, `max_tokens_total` | ✅ 3/3 | ✅ 3/3 |
| 3 tool errors in a row | ✅ | ✅ |
| Interrupt, approve / reject | ✅ 2/2 | ✅ 2/2 |
| No policy: no interrupt | ✅ | ✅ |
| Profile without the purchasing scope: no pause, no call | ✅ | ✅ |

## Findings

1. **Token usage arrives too late for a hook.** `AfterModelCallEvent` carries no usage, and the agent's metrics are updated *after* that hook runs. The adapter reads each call's usage from the stream's `metadata` event through a thin `AnthropicModel` subclass. LangGraph puts it on the message (`usage_metadata`).
2. **Concurrent tools by default.** With Strands' default executor, the MCP call order within a turn is not deterministic. For a legacy system with a database behind it, sequential execution is the safe default.
3. **Two different ways to express the same rules.** In LangGraph the rules are graph edges and node code. In Strands they are callbacks around a loop you do not own. Strands needed 19 more lines and more knowledge of the framework's internals: when metrics update, how a cancelled call is reported, how interrupts resume. LangGraph needed an explicit state schema. Both reproduce week 13 exactly. This goes into the decision matrix (activity 9).
