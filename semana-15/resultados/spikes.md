# Activity 6: spikes, OpenAI Agents SDK and Google ADK

Code: [`adaptadores/openai_agents.py`](../adaptadores/openai_agents.py) and [`adaptadores/google_adk.py`](../adaptadores/google_adk.py). Tests: [`tests/test_spikes.py`](../tests/test_spikes.py) (14, no API calls). Run: [`eval/spikes.py`](../eval/spikes.py). Generated tables: [`spikes_tablas.md`](spikes_tablas.md).

**Setup**
- **Agent:** the same agent as LangGraph and Strands (week 13 prompt, `responder` and limits), with **Claude through LiteLLM** and the week 14 MCP tools under the analyst's Keycloak token.
- **Tasks:** the week 13 CI set (10 tasks × ES/EN), k = 1.
- **Cost:** **$0.1562** (estimate $0.12, cap $0.30).

## Results

| Agent | pass@1 (95% CI) | Cost / task | Tokens in | p50 / p95 (s) | Steps | Tool calls |
|---|---|---|---|---|---|---|
| OpenAI Agents SDK | **0.950** (0.764 to 0.991) | $0.0032 | 22,662 | 7.2 / 28.4 | 3.90 | 5.75 |
| Google ADK | **0.950** (0.764 to 0.991) | **$0.0046** | **36,204** | 13.9 / 25.5 | 3.70 | 5.90 |
| LangGraph (activity 5, same tasks, k = 3) | 1.000 (0.940 to 1.000) | $0.0030 | 21,400 | 6.4 / 19.5 | 3.65 | 5.63 |
| Strands (activity 5, same tasks, k = 3) | 1.000 (0.940 to 1.000) | $0.0029 | 21,097 | 6.5 / 19.0 | 3.58 | 5.62 |
| Own loop (week 13, k = 3) | 1.000 (0.940 to 1.000) | $0.0027 | 19,130 | 6.6 / 14.9 | 3.58 | 5.50 |

Each spike failed one run, both on the ambiguous task `a01`: it answered instead of asking for clarification (`a01-en` in OpenAI, `a01-es` in ADK). With k = 1 and 20 runs, 0.950 is not distinguishable from 1.000 (the intervals overlap). The spikes measure friction and cost, not a quality ranking.

## Friction found (all verified in code, most by a test)

| Area | OpenAI Agents SDK 0.24 | Google ADK 2.13 |
|---|---|---|
| **MCP** | Protocol 2026-07-28. Tool results reach hooks as a Python `repr` of the content blocks, not JSON | Protocol 2025-11-25. It passes the **whole** MCP result to the model (text + `structuredContent` + `_meta`): each result costs about twice as many tokens. That is the +69% input tokens and +53% cost against LangGraph (measured with the simulated model: 10,954 against 5,623 message characters on the same task) |
| **OAuth** | Bearer header; `auth` accepts an `httpx.Auth` (activity 1) | Bearer header; `auth_scheme` / `auth_credential` or `header_provider` (activity 1) |
| **Claude through LiteLLM** | `ModelSettings.extra_body` makes LiteLLM 1.83 send the key **`extra_body` literally inside the JSON**, which the Anthropic API would reject. `reasoning_effort` silently turns into `thinking` with a 1,024-token budget. Only `extra_args` sends `output_config` as intended. A test now guards this | `output_config` passes through cleanly. The native `Claude` class only works through Vertex AI |
| **Prompt** | Identical to week 13 | ADK **always appends** "You are an agent. Your internal name is …" to the system prompt, and it treats `{...}` in the instruction as state variables, so the instruction must be a function. The prompt is week 13's plus one line |
| **Cost reporting** | Tokens per call (`on_llm_end`); LiteLLM prices them ($0.00027 for 1,200/300, matching our table) | Tokens in `usage_metadata`; LiteLLM prices them |
| **Rules (limits, `responder`, traces)** | `RunHooks` plus a `tool_use_behavior` that ends the run only on a valid answer. Stopping means raising an exception from a hook | Agent callbacks; `before_model` stops by returning a response without calling the model; `skip_summarization` ends the run after a valid answer |
| **Tracing** | Own tracing, **exported to OpenAI by default** (disabled here) | Native OpenTelemetry GenAI |
| **Multi-agent** | Handoffs and `Agent.as_tool` | `sub_agents`, `AgentTool`, and Sequential/Parallel/Loop workflow agents |
| **Human in the loop** | Approval items for MCP tools | `require_confirmation` on toolsets |

## Reading

1. **All four frameworks reproduce the same agent.** The 14 equivalence tests pass for both spikes as they did for LangGraph and Strands. Quality depends on the model and the prompt (the same `a01` ambiguity shows up across frameworks), not on the framework.
2. **Where cost hides.** ADK's default of forwarding the full MCP result makes the same agent 53% more expensive per task with no gain in quality. In a framework comparison, the token budget of tool results matters more than the framework's own overhead.
3. **LiteLLM is a layer to test, not to trust.** Two of the three ways of passing a provider parameter did something other than intended, silently. Anyone using Claude through LiteLLM needs a test that inspects the actual request, as `test_spikes.py` does with the simulated model.
