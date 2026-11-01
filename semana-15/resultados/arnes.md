# Activity 2: common harness

Code: [`arnes/`](../arnes/). Tests: [`tests/test_arnes.py`](../tests/test_arnes.py) (27, no API calls, $0). CI: [`eval-semana-15`](../../.github/workflows/eval-semana-15.yml) runs them on every PR that changes week 15 code, with one virtual environment per framework.

## What every framework shares

| Piece | Where | What it guarantees |
|---|---|---|
| **Contract** | [`arnes/contrato.py`](../arnes/contrato.py) | `Resultado`, `Limites`, the system prompt, the task message, the `responder` tool and `RespuestaFinal` **are the week 13 objects**, not copies. They load the same way in each framework's environment, which has no psycopg or sqlglot: a stand-in for the `herramientas` package is used only for that. The test checks that the system prompt has the same SHA-256 in all four environments |
| **Usage and cost** | `normalizar_uso`, `costo` | Tokens are read from any of the four formats seen in activity 1: `input_tokens` (Anthropic, LangChain), `inputTokens` (Strands), `prompt_tokens` (LiteLLM), `prompt_token_count` (ADK), as dicts or objects. `total_tokens` is never summed. Cost always comes from the week 13 price table, even for frameworks that report their own: it matches LiteLLM's $0.00027 for 1,200 in and 300 out |
| **Interface** | [`arnes/adaptador.py`](../arnes/adaptador.py) | `Adaptador.resolver(tarea) -> Resultado`. `Registro` does what every adapter would otherwise reimplement: counts steps, tools, tokens and errors; validates `responder` like week 13; checks limits; recomputes the final cost from the totals; emits the traces |
| **Contract check** | `validar_resultado` | Known state; integer counters ≥ 0; cost equal to the cost of its tokens; a final answer exactly when the model chose the state, matching that state and valid for the task's keys; at least one model step |
| **Traces** | [`arnes/trazas.py`](../arnes/trazas.py) | One JSONL event per model call, tool, final answer and stop. Fields: framework, model, run, task, step, latency, tokens, cost. The same schema for every framework, checked on write. Reused in week 17 |
| **Simulated model** | [`arnes/simulado.py`](../arnes/simulado.py) | A local stand-in of the Anthropic Messages API, with and without SSE streaming, that follows a script. Every framework talks to Claude through that API (natively or through LiteLLM) and accepts another `base_url`. So the same script exercises each framework's real code (its loop, its MCP tool dispatch, its token counting) for $0 |
| **Process bridge** | [`arnes/puente.py`](../arnes/puente.py) | Each framework runs in its own environment, because they pin incompatible versions of `mcp`, `a2a-sdk` and `litellm`. The orchestrator, the database and the verifier stay in the main one. JSON lines over stdin/stdout; one worker process per framework, reused across tasks |
| **Reference adapter** | `AdaptadorPropio` | The week 13 loop unchanged, with the tools from the week 14 MCP server. Its traces are translated to the common schema. It is the baseline for activity 5 |

## Tests

| Group | What they show |
|---|---|
| Contract | `Resultado` is week 13's (same fields, JSON round trip); prompt, task message and `responder` are identical |
| Usage and cost | The 4 framework formats plus an object, partial and empty usage; invalid values rejected; per-step cost adds up to the total; the price matches LiteLLM's from activity 1 |
| `validar_resultado` | Accepts a valid result and flags 7 violations: wrong cost, missing answer, state mismatch, limit with an answer, unknown state, negative steps, no steps |
| `responder` | Missing key and extra field rejected as `respuesta_invalida` (counted as tool errors), then a valid answer accepted |
| Traces | 6 events in order, all valid, framework and task id (`n01-es#2`) on each; incomplete or unknown events rejected |
| Simulated model | Follows the script with and without streaming, then ends with text when the script runs out |
| **Verifier on scripted outputs** (week 14 MCP server with OAuth + reference adapter) | A correct script passes the verifier, with cost exactly the cost of the scripted tokens and one trace event per scripted turn. A script with the wrong SQL fails it. Scripted abstention and clarification pass when they are the expected state and fail when they are not. A script that never calls `responder` ends in `limite_alcanzado` |
| Bridge | The same contract and traces through a worker process |
| Every framework environment | The contract loads in the LangGraph, Strands, OpenAI Agents and ADK environments with the same prompt hash and the same cost |

The LangGraph and Strands adapters (activities 3 and 4) only have to plug into `Registro` and the bridge, and they are tested with the same scripts.
