# Activity 1: baseline (frameworks, capabilities and the A2A protocol)

Verified on 2026-10-31. Everything here ran **without the Anthropic API ($0)**: each framework drives a scripted model, talks to a local stand-in of the Anthropic Messages API, or is inspected in code. Each framework runs in its own virtual environment, because they pin incompatible versions of `mcp`, `a2a-sdk` and `litellm` ([`linea_base/preparar.sh`](../linea_base/preparar.sh), pins in [`linea_base/requisitos/`](../linea_base/requisitos/)).

```bash
cd semana-15
./linea_base/preparar.sh                     # one venv per framework (.venvs/, not in Git)
python linea_base/orquestar.py               # MCP spike against the week 14 server with a Keycloak token
python linea_base/sonda_anthropic.py         # Claude integration, tokens and cost, against a local stand-in API
python linea_base/sonda_a2a.py               # A2A server, Agent Card and authentication
python linea_base/sonda_trazas.py            # OpenTelemetry spans and gen_ai.* attributes
```

Raw evidence: [`spike_mcp.json`](spike_mcp.json), [`sonda_anthropic.json`](sonda_anthropic.json), [`sonda_a2a.json`](sonda_a2a.json), [`sonda_trazas.json`](sonda_trazas.json).

## Versions (PyPI, 2026-10-31)

| Package | Version | Released | License | Maturity | What it pins |
|---|---|---|---|---|---|
| `langgraph` | 1.2.19 | 2026-10-30 | MIT | Production/Stable | `langchain-core` 1.x |
| `langchain-mcp-adapters` | 0.3.2 | 2026-08-06 | MIT | 0.x | **`mcp<2.0`** (installs 1.30.0) |
| `langchain-anthropic` | 1.7.7 | 2026-10-27 | MIT | | `anthropic>=0.120` |
| `strands-agents` | 1.63.0 | 2026-10-30 | Apache-2.0 | Production/Stable | `mcp<2.4`; **`a2a-sdk<0.4`** for its A2A extra |
| `bedrock-agentcore` | 1.25.2 | 2026-10-30 | Apache-2.0 | | extras `a2a` (a2a-sdk 0.3) and `a2a-v1` (a2a-sdk ≥ 1.0.1) |
| `openai-agents` | 0.24.0 | 2026-10-15 | MIT | 0.x (no stability classifier) | `mcp<3`; LiteLLM extra |
| `google-adk` | 2.13.0 | 2026-10-23 | Apache-2.0 | 2.x | `mcp<3`, `a2a-sdk<2`, `litellm<1.106.3` |
| `a2a-sdk` | 1.3.0 | 2026-10-27 | Apache-2.0 | | |
| `litellm` | 1.106.6 | 2026-10-28 | MIT | | |

## A2A specification

The current version is **A2A v1.0**, under the Agentic AI Foundation since August 2026 ([what's new in v1](https://a2a-protocol.org/latest/whats-new-v1/)). Changes from v0.3 that matter here:
- **Methods** renamed: `message/send` → `SendMessage`, `tasks/get` → `GetTask`, and so on, plus a new `ListTasks`. Aliases exist during the transition.
- **Agent Card:** `supportedInterfaces[]` replaces `url` and `preferredTransport`; each interface declares its own `protocolVersion`, so one agent can serve v0.3 and v1.0 at once. The card can be signed with JWS. Discovery stays at `/.well-known/agent-card.json`.
- **Security:** the implicit and password OAuth flows are gone; the authorization code flow gains `pkceRequired`; device code and mTLS are added.
- **Versioning:** requests carry an `A2A-Version` header. Three bindings with equivalence guarantees: JSON-RPC, gRPC and HTTP+JSON.

## Capability matrix

✅ verified by running code in this activity · 📄 present in the installed package (import or signature checked, not exercised) · ❌ not available.

| Capability | LangGraph | Strands Agents | OpenAI Agents SDK | Google ADK |
|---|---|---|---|---|
| **MCP over Streamable HTTP, Bearer token** | ✅ (adapter) | ✅ | ✅ | ✅ |
| **MCP protocol negotiated with our server** | 2025-11-25 (`mcp` 1.30) | **2026-07-28** | **2026-07-28** | 2025-11-25 (`mcp` 2.3, legacy handshake) |
| HTTP requests for list + 2 tool calls | 11 (a new session per call) | 4 | 4 | 6 |
| Invalid token | ✅ 401, error raised, 0 calls | ✅ | ✅ | ✅ |
| OAuth flow in the client | 📄 `auth` (`httpx.Auth`) | 📄 `auth_provider` (`httpx.Auth`); `auth` is client credentials only | 📄 `auth` (`httpx.Auth`) | 📄 `auth_scheme` / `auth_credential`, `header_provider` |
| Server's untrusted-data marker (`_meta`) reaches the agent | ❌ text only | ❌ text only | ❌ text only | ✅ |
| Tool prefix per server (shadowing) | 📄 `tool_name_prefix` (off by default) | 📄 `prefix` | 📄 duplicates across servers **rejected by default**; optional prefix | 📄 `tool_name_prefix` |
| **Claude (Haiku 5.5)** | ✅ native (`ChatAnthropic`) | ✅ native (`AnthropicModel`, streaming) | ✅ via LiteLLM | ✅ via LiteLLM; native `Claude` class only through Vertex AI |
| Tokens reported | ✅ 1200 / 300 | ✅ 1200 / 300 | ✅ 1200 / 300 | ✅ 1200 / 300 |
| Cost reported | ❌ (computed by our harness) | ❌ | ✅ $0.00027 (LiteLLM) | ✅ $0.00027 (LiteLLM) |
| Scripted agent loop with MCP tools | ✅ | ✅ | ✅ | ✅ |
| **State and checkpoints** | ✅ `InMemorySaver`, history per thread | 📄 session managers, `checkpointing` | 📄 `Session` (SQLite, OpenAI conversations) | 📄 `SessionService` (memory, database, Vertex) |
| **Human-in-the-loop** | ✅ `interrupt()` and `Command(resume=…)` | 📄 `Interrupt` | 📄 tool and MCP approval items | 📄 `require_confirmation` on toolsets |
| Step limit | 📄 `recursion_limit` | 📄 hooks / interventions | 📄 `max_turns` | 📄 `RunConfig` |
| **Multi-agent** | 📄 subgraphs, `langgraph-supervisor` 0.0.31, `Command(goto)` | 📄 `Graph`, `Swarm`, agents as tools | 📄 handoffs, `Agent.as_tool` | 📄 `sub_agents`, Sequential/Parallel/Loop agents, `AgentTool` |
| **A2A server** | ❌ in the library (LangGraph's hosted Agent Server offers it) | ✅ `A2AServer`, **v0.3.0 only** | ❌ | ✅ `to_a2a`, **v1.0** (answers 0.3 calls too) |
| A2A authentication enforced | — | ❌ no option | — | ❌ **declares** OAuth in the card but **accepts calls without a token** |
| **OpenTelemetry GenAI spans** | ❌ 0 spans (LangSmith, or external instrumentation) | ✅ 3 spans, 15 `gen_ai.*` attributes | ❌ 0 OTel spans; own tracing (agent, turn and task spans), **exported to OpenAI by default** | ✅ 3 spans, 9 `gen_ai.*` attributes |
| Managed deployment (from the vendors' documentation; not exercised, see activity 8) | LangSmith Deployment; Vertex AI Agent Engine; AgentCore | **AgentCore** (Runtime, Identity, Gateway, Memory); `bedrock-agentcore` 1.25.2 | self-hosted; AgentCore (any framework) | **Vertex AI Agent Engine**; Cloud Run; AgentCore |

## MCP spike against the week 14 server

[`linea_base/orquestar.py`](../linea_base/orquestar.py) starts the week 14 server (Streamable HTTP + OAuth, scopes, per-profile database role). It hands each framework only the URL and the `analista` token. The evidence comes from the **server's traces**, not from what each framework reports about itself.

| | LangGraph | Strands | OpenAI Agents | Google ADK |
|---|---|---|---|---|
| Tools listed | 6 | 6 | 6 | 6 |
| `describir_esquema` + `ejecutar_sql` (30 critical SKUs) | ✅ | ✅ | ✅ | ✅ |
| Token subject and scopes seen by the server | `analista`, 4 scopes | same | same | same |
| Protocol / methods | 2025-11-25: `initialize` + `notifications/initialized` before **each** list and call | 2026-07-28: `server/discover`, no handshake | 2026-07-28 | 2025-11-25, one session |
| Invalid token | 401, exception, 0 calls run | 401 ×2 | 401 ×2 | 401 ×2 |

The week 14 server stays compatible with both protocol generations, so the comparison in activity 5 is fair. The cost of the older generation shows up in requests, not in tokens: LangGraph's adapter opens a new MCP session for every call, 3 HTTP requests per tool call instead of 1.

## Gaps by framework

- **LangGraph**
  - The MCP adapter stays on `mcp` 1.x: protocol 2025-11-25 and a new session per call. Fine on loopback; on a remote server it adds a round trip per call. It can be avoided by keeping a session open (`client.session(...)`).
  - No A2A and no OpenTelemetry in the library.
  - Cost is not reported, only tokens.
- **Strands**
  - Its A2A is pinned to v0.3 (`a2a-sdk<0.4`), with no authentication option. AgentCore's `a2a-v1` extra is the way to v1.0.
  - Cost is not reported, only tokens.
- **OpenAI Agents SDK**
  - Pre-1.0 versioning.
  - Claude only through LiteLLM.
  - Its tracing **sends data to OpenAI by default**: it must be disabled or replaced (`set_tracing_disabled`, `set_trace_processors`) on any client with a data-residency requirement.
  - No A2A.
- **Google ADK**
  - Claude natively only through Vertex AI; elsewhere through LiteLLM.
  - The A2A card can declare OAuth, but the server does not enforce it: authentication needs our own middleware.
  - The only one that passes the server's untrusted-data marker to the agent.
- **All four**
  - The `_meta` untrusted marker (threat A04) is lost in three of four. The client-side `untrusted_data` envelope from week 14 must be reproduced in each framework's tool hook: LangGraph `tool_interceptors`, OpenAI `tool_output_guardrails`, Strands hooks and ADK callbacks.

## Impact on the plan

1. **The two frameworks for criterion 15 stay LangGraph and Strands.** They are opposite designs (explicit graph against a model-driven loop), they cover the two largest deployment targets (LangSmith/Vertex and AgentCore), and both speak Claude natively. OpenAI Agents SDK and ADK remain spikes.
2. **Activity 2:** the common harness computes cost from tokens with the week 13 price table, because LangGraph and Strands report only tokens. The LiteLLM price for Haiku 5.5 matches ($0.00027 for 1,200 in and 300 out).
3. **Activities 3 to 5:** the week 14 security envelope goes into each framework's tool hook, and the 38 poisoning cases run in both frameworks. LangGraph keeps one MCP session open per run.
4. **Activity 7 (A2A):** the Strands specialist speaks A2A v0.3 and the current spec is v1.0. Options to settle there: an `a2a-sdk` 1.x client with v0.3 compatibility, AgentCore's `a2a-v1` extra, or ADK as the A2A server. In every case authentication is **our middleware** (Keycloak token with its own audience); no framework enforces it by declaring it.
5. **Activity 9 (decision matrix):** the gaps above are already evidence for client-facing criteria (data residency of traces, A2A maturity, protocol generation).
