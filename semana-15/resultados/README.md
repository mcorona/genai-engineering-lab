# Week 15 results (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 15 README](../README.md)

The reports and recorded runs of week 15: the week 13 agent rebuilt in LangGraph and Strands, the spikes with the
OpenAI Agents SDK and Google ADK, the multi-agent system over A2A, Strands on Bedrock AgentCore, and the capability
probes behind the decision matrix. Each eval runner (`eval/correr.py`, `eval/spikes.py`, `eval/multiagente.py`,
`eval/agentcore.py`) writes a detail file, a metadata file, a trace file and a generated table file (`*_tablas.md`); the probes in `linea_base/` write one JSON file each. The other Markdown files
are the English analysis of each activity.

**Recorded evidence:** the JSON and JSONL files are the raw outputs of the runs, kept exactly as recorded (not
edited, not translated). The agent's answers in them are in Spanish or English, depending on the task's language.
The English summary of the results is in section 3 of the [week 15 README](../README.md) and in the English reports
of this folder: [`linea_base.md`](linea_base.md), [`arnes.md`](arnes.md), [`langgraph.md`](langgraph.md),
[`strands.md`](strands.md), [`frameworks.md`](frameworks.md), [`spikes.md`](spikes.md),
[`multiagente.md`](multiagente.md), [`agentcore.md`](agentcore.md), [`matriz_decision.md`](matriz_decision.md) and
[`ci.md`](ci.md).

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `linea_base.md`, `arnes.md`, `langgraph.md`, `strands.md`, `frameworks.md`, `spikes.md`, `multiagente.md`, `agentcore.md`, `ci.md` | The English analysis of activities 1 to 8 and 10 | Written with each activity; they cite the files below |
| `matriz_decision.md` | The decision matrix for clients (activity 9). Its tables are regenerated from the scores and evidence links in `eval/matriz.py` | `eval/matriz.py`; checked by `tests/test_matriz.py` |
| `frameworks_detalle.jsonl`, `frameworks_seguridad_detalle.jsonl`, `frameworks_meta.json`, `frameworks_resumen.json`, `frameworks_tablas.md` | Activity 5: LangGraph vs. Strands on the same tasks (one row per framework, task and repetition), the security cases per framework, run metadata, the machine-readable summary with paired comparisons against the week 13 runs, and the generated tables | Written by `eval/correr.py`; the task detail is read as a reference by `eval/spikes.py`, `eval/multiagente.py` and `eval/agentcore.py` |
| `spikes_detalle.jsonl`, `spikes_meta.json`, `spikes_tablas.md` | Activity 6: the OpenAI Agents SDK and Google ADK spikes | Written by `eval/spikes.py` |
| `multiagente_detalle.jsonl`, `multiagente_meta.json`, `multiagente_tablas.md` | Activity 7: the multi-agent system (supervisor, specialists, purchasing specialist over A2A) | Written by `eval/multiagente.py` |
| `agentcore_detalle.jsonl`, `agentcore_meta.json`, `agentcore_tablas.md` | Activity 8: Strands on AgentCore Runtime, the run reported in `agentcore.md` | Written by `eval/agentcore.py` |
| `agentcore_corrida1_*.json*` | Activity 8: the first AgentCore run, which failed before calling the model (see "Problems found" in `agentcore.md`). Kept as evidence | Written by `eval/agentcore.py`; kept under this name |
| `trazas/*.jsonl` | Traces of each eval: one event per line (model call, tool call, final answer and stop), in the harness's common format | Written by `eval/correr.py` (`frameworks`), `eval/spikes.py`, `eval/multiagente.py` and `eval/agentcore.py` |
| `sonda_anthropic.json` | Activity 1 probe: how each framework calls the Anthropic API (integration, usage and cost reported, requests seen) | Written by `linea_base/sonda_anthropic.py`; read by `tests/test_arnes.py` |
| `sonda_trazas.json` | Activity 1 probe: the OpenTelemetry spans and GenAI attributes each framework emits | Written by `linea_base/sonda_trazas.py` |
| `sonda_a2a.json` | Activity 1 probe: the A2A agent card, protocol version, declared security and calls without a token, for Strands and Google ADK | Written by `linea_base/sonda_a2a.py` |
| `spike_mcp.json` | Activity 1 spike: each framework against the week 14 MCP server with OAuth (tools listed, one call) | Written by `linea_base/orquestar.py` |

## Keys

| Key | Meaning |
|---|---|
| `framework` | The framework that ran the agent (`langgraph`, `strands`, `openai_agents`, `google_adk`) |
| `rep` | Repetition number |
| `tipo` | Task type (see the [week 13 gold set README](../../semana-13/golden/README.md)); in the traces, the event type |
| `estado`, `esperado` | The agent's final state and the expected state (see the [glossary](../../docs/glossary.md#status-values-and-verdicts)) |
| `exito`, `exactitud_claves` | The task passed; execution accuracy over the task's output keys |
| `pasos`, `herramientas`, `errores_herramienta` | Model calls, tool calls and tool errors in the run |
| `segundos`, `motivo`, `respuesta` | Wall-clock seconds; why the run stopped; the agent's answer |
| `categoria`, `usuario` | Security case category and simulated user (as in week 14) |
| `obedecio`, `fuga`, `acceso_prohibido_ok` | The agent obeyed an injected instruction; leakage; a forbidden read succeeded |
| `intentos_escritura`, `propuestas`, `dentro_de_limites` | Write statements tried; purchase proposals; the loop case stayed within its limits |
| `llamadas_maliciosas`, `bloqueados` | Calls that reached a malicious server; calls the client blocked |
| `emisor`, `simulacion` | Token issuer (`keycloak`); whether the run used the simulated model |
| `sin_lanzar`, `minutos`, `tope_usd` | Tasks not launched because of the spending cap; run duration; the spending cap |
| `tablas_modificadas` | Tables that changed during the run (none expected) |
| `grupos` | Results per framework or week 13 reference: `corridas`, `pass1`, `pass3`, `ic95`, `costo_tarea`, `p50_s`, `p95_s`, `por_tipo`, `estados` |
| `comparaciones` | Paired differences between groups: `n_tareas`, `diferencia`, `ic95` |
| `seguridad` | Security results per framework: `casos`, `ok`, `obedecio`, `fugas`, `por_categoria` |
| `desarrollo` | Development cost per framework: `lineas_codigo` (lines of code), `dependencias_directas` (direct dependencies), `paquetes_instalados` (installed packages), `minutos_implementacion` (minutes to implement) |
| `fase` | In the multi-agent detail: `tareas` (gold-set tasks), `compras` (purchasing), `compras_inyeccion` (purchasing with an injected instruction) |
| `delegaciones`, `a2a_peticiones`, `pedidos`, `llamadas_mcp` | Delegations from the supervisor, A2A requests, requests sent to the specialists, MCP calls |
| `pasos_por_agente` | Steps per agent |
| `propuestas_ok`, `sku`, `propuso_sku` | Every proposal stayed `PENDING_APPROVAL` and was not executed; the SKU of the purchasing task; whether a proposal named that SKU |
| `agente` | In the multi-agent traces: the agent that produced the event |
| `destino` | AgentCore eval target: `agentcore` or `local` |
| `arranque` | Startup timing per invocation: `tipo` (`frio` cold, `caliente` warm), process, import and API-key retrieval seconds |
| `cliente_s` | Seconds measured at the client |
| `identidad_sin_usuario` | The call without a runtime user ID: duration, error and whether it answered |
| `integracion`, `uso`, `peticiones` | In the Anthropic probe: how the framework integrates the model, the usage it reports, the requests seen |
| `spans_otel`, `nombres`, `atributos_gen_ai`, `nativo` | In the traces probe: OpenTelemetry spans emitted, their names, the GenAI attributes, and the framework's native tracing |
| `card_campos`, `version_protocolo`, `seguridad_declarada`, `llamadas_sin_token` | In the A2A probe: agent card fields, protocol version, declared security, calls made without a token |
| `llamada`, `extracto` | In the MCP spike: one tool call and an excerpt of its result |
