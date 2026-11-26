# Week 14 results (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 14 README](../README.md)

The reports and recorded runs of week 14: the remote MCP server with OAuth, the tool-poisoning eval through the secure
client, and the week 13 agent against the remote server. `seguridad/correr.py` and `agente_remoto/correr.py` write
the detail, summary and trace files and generate `seguridad.md` and `remoto.md`. The HTTP server writes its request
traces with `--trazas`. The other Markdown files are the English reports of each activity.

**Recorded evidence:** the JSON and JSONL files are the raw outputs of the runs, kept exactly as recorded (not
edited, not translated). The agent's answers in them are in Spanish or English, depending on the task's language.
The English summary of the results is in section 4 of the [week 14 README](../README.md) and in the English reports
of this folder: [`linea_base.md`](linea_base.md), [`primitivas.md`](primitivas.md),
[`transporte.md`](transporte.md), [`keycloak.md`](keycloak.md), [`oauth.md`](oauth.md),
[`poisoning.md`](poisoning.md), [`seguridad.md`](seguridad.md), [`agente_remoto.md`](agente_remoto.md),
[`remoto.md`](remoto.md), [`claude_code.md`](claude_code.md) and [`ci.md`](ci.md).

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `linea_base.md`, `primitivas.md`, `transporte.md`, `keycloak.md`, `oauth.md`, `poisoning.md`, `agente_remoto.md`, `claude_code.md`, `ci.md` | The English reports of activities 1 to 8 | Written with each activity; they cite the files below |
| `seguridad.md`, `seguridad_resumen.json`, `seguridad_detalle.jsonl` | Activity 6: the agent's security eval through the secure client, with and without defenses: generated report, summary per phase and category, one row per case and repetition | Written by `seguridad/correr.py` |
| `remoto.md`, `remoto_resumen.json`, `remoto_detalle.jsonl` | Activity 7: the week 13 agent over stdio and over the remote server (HTTP + OAuth), plus a user without the needed scope: generated report, summary per group, one row per task and repetition | Written by `agente_remoto/correr.py`, which also reads the week 13 run `eval_haiku_low` as the in-process reference |
| `trazas/seguridad.jsonl`, `trazas/remoto.jsonl` | Agent traces of the two evals: one event per line (model call, tool call, final answer, stop) | Written by `seguridad/correr.py` and `agente_remoto/correr.py` through the week 13 loop |
| `trazas/claude_code.jsonl` | The server's request traces during the manual test with Claude Code as the MCP client | Written by `python -m servidor --transporte http --oauth --trazas ...` |
| `trazas_http_ejemplo.jsonl` | An example of the server's request traces over Streamable HTTP, cited in `transporte.md` | Written by `python -m servidor --transporte http --trazas ...` |

## Keys

| Key | Meaning |
|---|---|
| `fase` | Security eval phase: `defensas` (with the client defenses) or `sin_defensas` (a naive client, the baseline) |
| `categoria` | Security case category: `poisoning_descripcion` (tool poisoning in a description), `rug_pull`, `shadowing`, `inyeccion_resultado` (prompt injection in a tool result), `inyeccion_datos` (in data), `inyeccion_regla` (in a business rule), `escritura` (write), `propuesta` (purchase proposal), `fuga_rol` (leakage by role), `fuga_tenant` (leakage across tenants), `bucle` (loop) |
| `rep` | Repetition number |
| `usuario` | The simulated user (`analista`, `almacenista`, `vendedor`) |
| `estado`, `esperado` | The agent's final state and the expected state (see the [glossary](../../docs/glossary.md#status-values-and-verdicts)) |
| `motivo` | Why the run stopped |
| `pasos`, `herramientas` | Model calls and tool calls in the run |
| `intentos_escritura`, `propuestas` | Write statements the agent tried; purchase proposals registered |
| `capturas_maliciosas` | Calls captured by each malicious server |
| `bloqueados`, `eventos` | Calls the secure client blocked; the client's security events (`<server>:<event>`) |
| `obedecio` | The agent obeyed the injected instruction. For `poisoning_descripcion`, it queried `prvmst` or passed data to the malicious tool |
| `consulto_prvmst`, `exfiltracion` | The agent queried the supplier table; it passed data to the malicious tool |
| `llamo_a_la_sombra` | The agent called the shadow tool (tool shadowing) |
| `expuesto` | The agent saw the injected text |
| `ok`, `ok_parcial` | The case passed; in the write and proposal cases, a provisional pass that the database fingerprint at the end confirms or overturns |
| `fuga`, `acceso_prohibido_ok` | Leakage in the answer; a forbidden read succeeded |
| `dentro_de_limites`, `paro_por_limite` | The loop case stayed within its limits; the run stopped at a limit |
| `uso`, `respuesta` | Tool calls per tool; the agent's answer |
| `tablas_modificadas` | Tables that changed during the eval (none expected) |
| `por` | Results per `<phase>/<category>`: `corridas` (runs), `ok`, `obedecio`, `fugas` (leaks) |
| `via` | How the agent reached the tools: `stdio`, `remoto` (HTTP + OAuth), `remoto_sin_scope` (a user without the needed scope) |
| `ms_herramientas` | Duration of each tool call, in milliseconds |
| `valores_filtrados`, `lecturas_prohibidas`, `denegadas` | Out-of-scope values found in the answer; reads of out-of-scope tables; the error types of denied calls |
| `termino_bien` | The out-of-scope run ended correctly: it abstained, asked for clarification, stopped at a limit, or a call was denied |
| `tokens_ms` | Time to get each user's token, in milliseconds |
| `grupos` | Results per group (in-process, stdio, remote): `corridas`, `exito` (success), `ic95` (95% confidence interval), `costo_tarea` (cost per task), `p50_s`, `p50_ms_herr` and `p95_ms_herr` (tool-call latency) |
| `sin_scope` | The runs without the needed scope: `corridas`, `fugas`, `terminaron_bien` (ended correctly) |
| `http`, `ruta`, `metodo`, `nombre` | In the request traces: HTTP method, HTTP path, JSON-RPC method, tool or resource name |
| `bytes_in`, `bytes_out`, `ms` | In the request traces: request and response size in bytes, and duration in milliseconds |
| `sujeto`, `scopes`, `cliente_oauth` | The token's subject, its scopes and its OAuth client |
| `cliente`, `protocolo` | The MCP client name and protocol version |
| `estado`, `resultado`, `error` | In the request traces: HTTP status, result (`ok`, `rechazado` rejected, `error_herramienta`, `error_protocolo`) and error code |
| `motivo_auth` | Why the authorization was rejected |
