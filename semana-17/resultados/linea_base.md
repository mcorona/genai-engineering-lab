# Activity 1: baseline of the observability capabilities

Verified on 2026-11-03 on the Mac (Python 3.13.14) and in the lab container (Python 3.13.16), with the pins of
[`preparar/versiones.json`](../preparar/versiones.json). Everything marked **M** was checked by running code in
[`linea_base/verificar.py`](../linea_base/verificar.py): 10 probes, each in its own subprocess, **$0 and no model call**
except the one `claude_code` probe, which uses the Claude Code subscription (not the API). Raw evidence:
[`linea_base_mac.json`](linea_base_mac.json), [`linea_base_contenedor.json`](linea_base_contenedor.json) and
[`linea_base_mac_claude_code.json`](linea_base_mac_claude_code.json). Tests:
[`tests/test_linea_base.py`](../tests/test_linea_base.py).

**M** = measured by running code in this activity · **D** = documented (docs, source code or `--help`), not exercised
here · **N** = not verified yet.

```bash
cd semana-17
uv run --group semana17 python linea_base/verificar.py --langfuse    # Mac: 9 probes, throwaway Langfuse v4 in Docker
uv run --group semana17 python linea_base/verificar.py --solo paquetes,semconv,util_genai,collector,mcp,agent_sdk,frameworks,repo
uv run --group semana17 python linea_base/verificar.py --con-modelo --solo claude_code   # 1 tiny call, subscription
```

## Results by environment

| Where | Probes | Result |
|---|---|---|
| Mac | `paquetes`, `semconv`, `util_genai`, `collector` (Docker image by digest), `mcp`, `agent_sdk`, `frameworks`, `repo`, `langfuse` | **9/9 OK** |
| Container | the same without `langfuse` (no Docker inside) | **8/8 OK**, the Collector runs as the 0.164.0 binary |
| Mac, with the model | `claude_code` (Claude Code 2.1.317 on the subscription) | **OK**, exit 0 in 10 s |

The 11 tests of `semana-17/tests` pass on the Mac and in the container.

## Capability matrix

### Semantic conventions and instrumentation

| Capability | What was found | Status |
|---|---|---|
| OTel GenAI semantic conventions: status | They live in the `open-telemetry/semantic-conventions-genai` repo, checked at commit `95aff9c`. **All 266 entries are `development`** and there is no tagged release. Schema `gen-ai-dev/1.42.0-dev` | M |
| OTel GenAI semantic conventions: names | 9 operations: `chat`, `generate_content`, `text_completion`, `embeddings`, `retrieval`, `create_agent`, `invoke_agent`, `execute_tool`, `invoke_workflow`. `gen_ai.system` is deprecated in favor of `gen_ai.provider.name`. The installed package `opentelemetry-semantic-conventions` 0.66b2 defines the 16 attributes the lab checks (operation, provider, request and response model, input, output, cache read, cache creation and reasoning tokens, agent name, tool name, call id and type, conversation id, input and output messages) | M |
| Cache token names differ between libraries | The semconv package uses `gen_ai.usage.cache_creation.input_tokens`; `opentelemetry-util-genai` writes `cache_write`. The lab therefore locks the span shape with a test (activity 3) | M |
| Instrumentation chosen: `opentelemetry-util-genai` 1.3b0 | Emits `invoke_agent legacybridge`, `chat claude-haiku-5-5` and `execute_tool describir_esquema` with the `gen_ai.*` attributes above | M |
| Content capture of the instrumentation | **Off by default**: no `gen_ai.input.messages` or `gen_ai.output.messages`. With `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_ONLY` both appear. The other values are `NO_CONTENT`, `EVENT_ONLY` and `SPAN_AND_EVENT` | M (off and `SPAN_ONLY`) · D (the other two) |

### Python SDK and Collector

| Capability | What was found | Status |
|---|---|---|
| Python SDK, semconv and httpx instrumentation | OpenTelemetry SDK 1.45.2, semconv and `instrumentation-httpx` 0.66b2: the installed versions equal the pins on the Mac and in the container, and CI installs the same lock | M |
| Collector contrib 0.164.0 | Runs as a binary in the container and as an image by digest on the Mac. The pipeline OTLP HTTP → `redaction` → `batch` → `file` validates and exports. The exporters are now named `otlp_http` and `otlp_grpc` | M |
| Redaction in the Collector | The 6 canaries (DSN, bearer token, email, phone, tax ID, `sk-ant` key) come out as `****` in the file, and none appears unmasked | M |

### Langfuse v4

| Capability | What was found | Status |
|---|---|---|
| Langfuse images | Web and worker 4.72.0, all 8 images of the lab **pinned by digest** in `versiones.json`. The throwaway stack (`langfuse_prueba.compose.yml`) is ready in 20 s on the Mac, publishes only `127.0.0.1:3100` and `127.0.0.1:4318`, and is fully removed afterwards | M |
| Langfuse dependencies | The stack runs with PostgreSQL 17, ClickHouse 26.3.62.3, Redis 7 and MinIO (Chainguard). The documented minimums are PostgreSQL 15 and ClickHouse 25.12 | M (versions used) · D (minimums) |
| OTLP endpoint and auth | `/api/public/otel/v1/traces` with `Authorization: Basic pk:sk`: **401 without auth, 200 with it** | M |
| Langfuse mapping of `gen_ai.*` to observations | The three span kinds arrive as `AGENT`, `GENERATION` and `TOOL`, and the model arrives as `claude-haiku-5-5`. In the source, the type comes from `gen_ai.operation.name` unless `langfuse.observation.type` is set (`ObservationTypeMapper`) | M (result) · D (rule) |
| **Langfuse usage accounting** | Langfuse subtracts cached tokens from `gen_ai.usage.input_tokens`, because the semconv says input includes them. Sent: input 1020, cache read 900, output 30. Stored: **input 120, cached 900, output 30, total 1050** | M |
| Langfuse scores | Written with `POST /api/public/scores` (200) and read back with `GET /api/public/v3/scores?traceId=` (200) | M |
| Langfuse read APIs | In the default `events_only` mode: v1 `traces/{id}`, `scores` (GET) and `metrics` answer **404**; `v2/observations` and `v2/metrics` answer **200** | M |
| Langfuse dashboards API | `GET /api/public/unstable/dashboards` answers 200. The route is called **unstable**, so activity 8 needs a plan B | M |
| Langfuse data retention | Needs the `data-retention` entitlement, which the `oss` and `self-hosted:pro` plans do not include. `trace-deletion` is available | D |
| Canaries in Langfuse | None of the canaries reached Langfuse or the Collector file | M |

### Native instrumentation of the agent stacks

| Capability | What was found | Status |
|---|---|---|
| Claude Agent SDK 0.2.175 | `subprocess_cli.py` injects `TRACEPARENT` and `TRACESTATE` of the active span into the CLI's environment. The bundled CLI is 2.1.314 | M |
| Claude Code 2.1.317 telemetry | With `CLAUDE_CODE_ENABLE_TELEMETRY=1` and `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` it exports on `/v1/metrics`, `/v1/logs` and `/v1/traces`: metrics `session.count`, `cost.usage`, `token.usage`, `active_time.total`; spans `claude_code.interaction` and `claude_code.llm_request` with `gen_ai.provider.name`, request model, conversation id, response id, finish reasons and the deprecated `gen_ai.system`; events `user_prompt`, `api_request`, `assistant_response`, `hook_*`, `mcp_server_connection`, `plugin_loaded` and `managed_settings_resolved`. Token counts use **non-standard keys** (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`), not `gen_ai.usage.*` | M |
| Claude Code content controls | The prompt is **not exported by default** (a canary in the prompt never left). The opt-in variables are `OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_TOOL_DETAILS`, `OTEL_LOG_TOOL_CONTENT`, `OTEL_LOG_ASSISTANT_RESPONSES` and `OTEL_LOG_RAW_API_BODIES`; they were not switched on here. Claude Code does not pass `OTEL_*` to its subprocesses | M (default) · D (variables, subprocesses) |
| Strands 1.63.0 | 3 spans (`invoke_agent Strands Agents`, `chat`, `execute_event_loop_cycle`) and 15 `gen_ai.*` attributes, from the week 15 probe ([`sonda_trazas.json`](../../semana-15/resultados/sonda_trazas.json)). It still uses the old `gen_ai.system` and mixes several usage key spellings | M (week 15) |
| LangGraph 1.2.19 | 0 native OTel spans. It uses LangSmith (`LANGSMITH_TRACING`); OpenTelemetry needs an external instrumentation | M (week 15) |

### MCP, repository and CI

| Capability | What was found | Status |
|---|---|---|
| MCP SDK 2.3.0: W3C propagation over Streamable HTTP | `MCP send tools/call X` (CLIENT) is the parent of `tools/call X` (SERVER), in the same trace, through `_meta` (SEP-414). The server adds `gen_ai.operation.name=execute_tool` and `gen_ai.tool.name`. Measured on the Mac and in the container, protocol version `2026-07-28`. Extra `server/discover` spans appear | M |
| MCP: agent span to MCP client span | **Not linked**: the `invoke_agent` span lands in a different trace than the MCP client spans (`agente_a_cliente: false`) | M |
| `semana-17/**` in the `evals-semana-06` paths | Confirmed by the `repo` probe, so the required `regresion` check runs on this folder | M |
| Pins and digests replaced | The candidate pins of `versiones.json` are now the verified ones, and every image has a digest | M |

## Findings that change later activities

1. **Activity 3: the agent span and the MCP client spans are in different traces.** The week 14 `ClienteSeguro` runs the
   calls in another thread or event loop (`call_soon_threadsafe`) without copying the OpenTelemetry context. The
   instrumentation must copy it (`contextvars.copy_context()` or `context.attach`) so agent, client and server share one
   trace.
2. **Activity 3: add the cached tokens to `gen_ai.usage.input_tokens` before exporting.** The Anthropic API reports
   cache read and cache creation apart from `input_tokens`, but the convention (and Langfuse) treat them as part of the
   input. Without the sum, Langfuse shows a smaller input and a wrong total.
3. **Activity 3: lock the span shape with a test.** The conventions are all `development`, and the cache names already
   differ between two libraries.
4. **Activity 2: data retention is not available in the self-hosted plans we can use.** Use `trace-deletion` or a
   deletion job of our own, and document it as the retention policy.
5. **Activity 8: the Langfuse read APIs of v4 are not the v1 ones.** Read with `v2/observations`, `v3/scores` and
   `v2/metrics`. The dashboards API is `unstable`, so the dashboard also needs a documented manual route and a static
   export built from the read APIs.
6. **Activities 3 and 9: Claude Code does not export prompts unless asked.** If it is used as a source of traces, its
   content variables stay off, and its non-standard token keys need a mapping.

## What this baseline does not cover

- **Langfuse in CI.** The probe needs Docker and about 4 GB of RAM, so it runs on the Mac only. CI checks traces on the
  Collector's file output (activity 10).
- **The OTLP gRPC path.** Only OTLP HTTP was exercised.
- **Content capture on in the Collector pipeline.** The canaries were checked with capture off; activity 9 repeats the
  check with capture on.
- **Documented, not run (D).** The `data-retention` entitlement, the `ObservationTypeMapper` rule, the minimum
  dependency versions, the `OTEL_LOG_*` variables of Claude Code and the `EVENT_ONLY` and `SPAN_AND_EVENT` capture modes.
