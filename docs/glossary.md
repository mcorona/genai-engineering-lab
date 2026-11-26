# Glossary

The lab's documentation is in English. Its folder names, file names, JSON keys, command-line flags, stack names and
status values are in Spanish, because they belong to the measured system. Recorded runs, frozen gold sets and tests
depend on them (see [language-audit.md](language-audit.md)). This page explains every Spanish term a reader will meet.

How to read a name: split it on `_`, `-` and `.`, then look up each word in the [word list](#word-list). For example,
`costo_usd_por_consulta` = cost, USD, per query; `tokens_salida` = output tokens; `corrida_sin_plugin_haiku` = run
without the plugin, on Haiku. Terms whose meaning is not the sum of their words have their own sections:

- [Weeks, phases and plans](#weeks-phases-and-plans)
- [Folders](#folders)
- [File names](#file-names)
- [Status values and verdicts](#status-values-and-verdicts)
- [Categories and task types](#categories-and-task-types)
- [Frequent JSON and CSV keys](#frequent-json-and-csv-keys)
- [Command-line flags](#command-line-flags)
- [AWS stacks and resources](#aws-stacks-and-resources)
- [The legacy schema](#the-legacy-schema)
- [Business vocabulary](#business-vocabulary)
- [Word list](#word-list)
- [Term list: one English term per concept](#term-list-one-english-term-per-concept)

## Weeks, phases and plans

| Term | Meaning |
|---|---|
| `semana-NN` | Week NN of the lab's study program, one folder per week. A week is a unit of work, not a calendar week. The root README lists all the weeks in [Weeks at a glance](../README.md#weeks-at-a-glance) |
| `semana19`, `semana20` (no hyphen) | The same week, in names where a hyphen is not allowed: AWS stacks, `uv` dependency groups (`uv sync --group semana19`) |
| `FasXSemaNN.md` | The plan of phase X, week NN (*Fase*, *Semana*). Example: `Fas5Sema19.md` = phase 5, week 19. It holds the activities, decisions and the Log |
| `actividad-N`, `actividad N` | Activity N of the week. Each activity closes with a PR |
| Fase 1 … Fase 5 | Phase 1 … phase 5 of the program (fundamentals; prompts, evals and NLQ; RAG and data; agents and MCP; LLMOps and production) |
| criterio de salida | Exit criterion of a week or phase ([exit-criteria.md](exit-criteria.md)) |
| `ALCANCE.md` | Scope document (week 18) |
| `oferta.md` | Service offer (week 16) |
| Log, *Bitácora* | The dated record at the end of each plan |

## Folders

| Folder | Meaning |
|---|---|
| `adaptadores/` | adapters (one per agent framework or trace source) |
| `agente/`, `agentes/` | agent, agents |
| `agente_remoto/` | remote agent (an agent that uses the remote MCP server) |
| `agente_sdk/` | the agent built with the Claude Agent SDK |
| `aprobaciones/` | approvals (human approval of purchase orders) |
| `arnes/` | harness (the code that runs one agent under every framework) |
| `arquitectura/`, `arquitectura/adr/` | architecture, architecture decision records |
| `ataques/` | attack cases |
| `atribucion/` | cost attribution |
| `auditoria/` | audit output (the plugin's deliverables) |
| `capturas/` | screenshots |
| `cliente/` | client |
| `comparacion/` | comparison |
| `computo/` | compute (the Lambda functions' stack) |
| `comun/`, `_compartido/` | shared code, shared prompt parts |
| `consultas/` | queries (the asynchronous query API) |
| `corpus/`, `corpus_beta/` | the Spanish document corpus of the fictional company (tenant alfa, tenant beta) |
| `corrida/`, `corridas/` | run, runs (recorded runs of an experiment or an eval) |
| `corrida_corregida/` | the corrected run (week 20) |
| `costos/` | costs (price list and cost model) |
| `datasets/` | evaluation sets |
| `destilacion/`, `dpo/`, `entrenamiento/` | distillation, DPO, training (week 4) |
| `ejemplo/` | example output (the plugin's sample audit) |
| `empaquetado/` | packaging |
| `escaneos/` | scanned pages (OCR inputs) |
| `evaluacion/`, `eval/` | evaluation |
| `experimentos/` | experiments |
| `fuentes/` | source documents (week 10) |
| `golden/` | frozen gold sets |
| `guardrail/`, `guardrails/` | guardrails |
| `herramientas/` | agent tools |
| `imagenes/`, `imagenes_inyeccion/` | images, images with injected instructions |
| `ingesta/`, `ingesta/paquete/` | ingestion, the ingestion package uploaded to the managed RAG services (`administrado/`: originals that the service parses and chunks, `adm-*` configurations; `controlado/`: the lab's own chunks, `ctl-*` configurations) |
| `infra/`, `infra/loader/` | infrastructure, the database loader function |
| `instrumentacion/` | instrumentation (OpenTelemetry) |
| `inyeccion/`, `pdf_inyeccion/` | injected-instruction documents |
| `kb_envenenados/` | poisoned knowledge-base documents |
| `legado/` | the legacy schema |
| `linea_base/` | baseline (measurements and checks before a change) |
| `multiagente/` | multi-agent |
| `navegador/` | browser (browser automation) |
| `observabilidad/` | observability stack |
| `ocr_extracciones/`, `pdf_extracciones/`, `imagenes_extracciones/` | OCR, PDF and image extractions |
| `pizarra/` | whiteboard design kit (week 18) |
| `politicas/` | policies (Cedar) |
| `preparar/` | setup (environment checks and version pins) |
| `presupuestos/` | budgets |
| `previos/` | earlier runs, kept for comparison |
| `requisitos/` | requirements (pinned dependencies) |
| `resultados/`, `resultados-n5/` | results and evidence; week 2's preliminary results with N = 5 |
| `rubricas/` | rubrics for the LLM judge |
| `seguridad/`, `seguridad_obs/` | security tests; security of the observability stack |
| `servidor/`, `servidor_mcp/` | server, MCP server |
| `tablero/` | dashboard |
| `trayectorias/` | trajectories (reference tool-call sequences) |
| `trazas/` | traces |
| `verdad/` | ground truth |
| `plugin_minimo/`, `hola-auditoria/` | the minimal plugin of week 16's spike, its "hello audit" skill |
| `auditar/`, `auditoria-completa/`, `solo-diccionario/`, `solo-riesgos/` | the plugin's skills: audit, full audit, data dictionary only, risks only |
| `1-inyeccion_datos/` … `7-tool_poisoning/` | week 16 security cases: data injection, injection in comments and names, fix a value, read credentials, evade with Bash, evade with a subagent, tool poisoning |
| `01-es-diccionario/` … `10-en-pide-borrar/` | the plugin's eval cases: language, then the task (dictionary, risks, full audit, diagram, injected notes, CFO summary, out-of-scope requests marked `neg`: SQL, normalization, new design, a request to delete) |

## File names

| Pattern | Meaning |
|---|---|
| `*_detalle.jsonl`, `*_detalle.csv` | per-item detail of a run (one row per question or task) |
| `*_cache.json` | recorded model responses per question and configuration, reused when a run is repeated |
| `crudo*` | raw output, as returned |
| `resumen*` | summary |
| `manifiesto.json` | manifest: counts and SHA-256 hashes that freeze a gold set or a package |
| `sellos.json` | seals: the hashes of sealed cases (week 18) |
| `verificacion*`, `verificar*.py` | verification |
| `preparar_base.py` | creates the database, its read-only role and the synthetic data |
| `construir*.py` | builds a gold set or a package |
| `correr.py`, `corrida.py` | runs an experiment or an eval |
| `evaluar.py`, `eval_ci.py` | evaluates; the CI eval |
| `desplegar.sh`, `destruir.sh` | deploy, destroy (week 19) |
| `arrancar.sh` | start (a local stack) |
| `inventario*.py`, `inventario*.json` | inventory of cloud resources left after a teardown |
| `cotizacion.md` | the cost quotation: predicted vs. real cost (week 19) |
| `costo_real*` | real cost, from the bill |
| `precios*.json` | price lists, each price with its source and date |
| `diccionario*.json`, `diccionario.yaml` | data dictionary |
| `riesgos*` | risks |
| `relaciones.mmd` | relationships (an ER diagram in Mermaid) |
| `permisos*.json` | permissions (role → allowed tools or tables) |
| `versiones.json` | pinned versions |
| `reglas_legado.md`, `reglas_negocio.json` | the legacy schema's business rules (a prompt; a gold-set input) |
| `tareas_es.jsonl`, `tareas_en.jsonl` | the agent's tasks, in Spanish and in English |
| `*_es.*`, `*_en.*` | the Spanish and the English version of a set |

## Status values and verdicts

| Value | Meaning |
|---|---|
| `respondida` | answered |
| `abstenida` | abstained: the agent declined to answer, as the task expected or not |
| `requiere_aclaracion` | needs clarification (the agent asked a question back) |
| `limite_alcanzado` | limit reached (turns, tokens or budget) |
| `en_espera` | waiting (paused for a human approval) |
| `en_curso` | in progress |
| `completada` | completed |
| `aprobada`, `aprobar` | approved, approve |
| `rechazada`, `rechazado`, `rechazar` | rejected, reject |
| `expirada` | expired (an approval that timed out) |
| `no_corrida` | not run |
| `no_encontrada` | not found |
| `ejecutada` | executed (the SQL or the tool ran) |
| `bloqueado`, `escritura_bloqueada` | blocked; write blocked |
| `permiso_denegado`, `sin_permiso` | permission denied |
| `funcion_prohibida` | forbidden function (rejected by the SQL guard) |
| `error_herramienta` | tool error |
| `funciono` | the attack worked (a table changed, a proposal was registered, or the answer did what the injected note asked) |
| `contenido` | contained: the model saw the injected note and did not obey it |
| `bloqueado_capa`, `bloqueado_guardrail` | blocked by the deterministic layer; stopped by the Bedrock Guardrail |
| `fallo_presupuesto` | the run stopped at the per-task budget, with no attempt seen |
| `sin_evidencia` | no sign that the injected note was read |
| `hallazgo` | finding |
| `ok` | passed |
| `PENDING_APPROVAL`, `APPROVED`, `REJECTED` | the states of a purchase order in the database (`ocp_sts`) |
| `pendiente`, `pendientes` | pending |
| `"quedan": "nada"` | the teardown inventory: **remaining: none**. `"quedan": "revisar"` = remaining: review (something could not be read) |
| `NO MEDIDO` | not measured (never reported as 0) |
| `INSUFICIENTE` | insufficient: the fallback answer of week 5's templates when the input lacks the data |
| `M`, `D`, `N` (price marks) | M = measured with the AWS Price List API (catalog id); D = documented on the official pricing page (link and date); N = not measured, left out of the sum |

## Categories and task types

| Value | Meaning |
|---|---|
| `simple`, `regla`, `compuesta`, `valores`, `ambigua`, `sin_respuesta` | the agent's task types: simple, business rule, compound, value lookup, ambiguous, unanswerable |
| `base`, `seguimiento`, `multisalto`, `multitenant` | question types: base, follow-up, multi-hop, multi-tenant |
| `documental`, `sql`, `mixta`, `no_textual` | routing types of week 10: document, SQL, mixed, non-text (an image) |
| `huerfanos` | orphan rows (a reference to a row that does not exist) |
| `duplicados` | duplicates |
| `nulos_en_clave` | nulls in a key |
| `datos_personales` | personal data (PII) |
| `unidades_inconsistentes` | inconsistent units |
| `reglas_fuera_de_la_base` | business rules that live outside the database |
| `instrucciones_inyectadas`, `notas_inyectadas` | injected instructions, injected notes |
| `inyeccion_regla`, `inyeccion_resultado` | injection in a business rule, injection in a tool result |
| `poisoning_descripcion`, `shadowing`, `rug_pull` | tool poisoning in a description, tool shadowing, rug pull (week 14) |
| `fuga_tenant` | tenant leak |
| `bucle` | loop |

## Frequent JSON and CSV keys

The keys below appear in many recorded files. Any other key can be read with the [word list](#word-list). Each
results folder also gets its own schema of keys in step 4 of the English pass.

| Key | Meaning |
|---|---|
| `modelo` | model id |
| `respuesta`, `respuesta_esperada` | answer, expected answer |
| `costo_usd`, `costo` | cost in USD |
| `latencia_s`, `latencia_p50_s`, `latencia_p95_s` | latency in seconds (median, 95th percentile) |
| `herramientas`, `herramientas_pedidas` | tools, tools requested |
| `corrida`, `corridas`, `por_corrida` | run, runs, per run |
| `resultado`, `resultados`, `resultado_distinto` | result, results, a different result set |
| `coincide_resultado` | the result set matches the reference |
| `tareas`, `por_tarea`, `por_tipo` | tasks, per task, per type |
| `criterios` | criteria |
| `detalle` | detail |
| `nota` | note |
| `texto` | text |
| `tabla`, `tablas`, `tablas_citadas`, `tablas_modificadas` | table(s), cited tables, modified tables |
| `juez`, `costo_juez_usd` | the LLM judge, its cost |
| `consulta`, `consultas` | query, queries |
| `tokens_salida`, `tokens_entrada` | output tokens, input tokens |
| `tokens_cache_lectura`, `tokens_cache_escritura` | cache read tokens, cache write tokens |
| `costo_por_respuesta_correcta` | cost per correct answer |
| `citas_con_pasaje`, `cobertura_cita` | citations that contain the passage, citation coverage |
| `pasajes_en_contexto`, `k_contexto` | passages in the context, k passages in the context |
| `bloqueos_registrados`, `bloqueos_vistos`, `bloqueos_guardrail` | blocks recorded, blocks seen, guardrail blocks |
| `huella_datos_intacta`, `huella_catalogo_intacta` | the data fingerprint and the catalog fingerprint are unchanged (the database was not modified) |
| `secreto_en_respuesta`, `secretos_en_archivos` | a secret in the answer, secrets in files |
| `uso_de_la_sombra` | use of the shadow tool (tool shadowing) |
| `datos_personales_filtrados` | personal data that leaked into a deliverable |
| `max_resultados`, `n_resultados` | maximum results, number of results |
| `omisiones_del_esquema` | schema omissions |
| `turnos`, `turnos_paralelos` | turns, parallel tool-call turns |
| `salida_chars` | output length in characters |
| `presupuesto_tarea` | the task's budget |
| `precision_herramientas` | tool precision |
| `metricas_sin_puntaje` | metrics without a score |
| `costo_evaluacion_corrida_usd` | the cost of evaluating the run, in USD |
| `ventana_utc` | time window, in UTC |
| `solicitudes`, `llamadas` | requests, calls |
| `idioma`, `lang` | language (`es`, `en`) |
| `pregunta`, `question` | question |
| `referencia`, `gold` | reference answer, gold passages |
| `respondible` | answerable |
| `origen` | origin (the set an item comes from) |
| `significado` | meaning (in a data dictionary) |
| `llave_primaria`, `llave_foranea` | primary key, foreign key |
| `quedan`, `no_medido`, `total` | remaining, not measured, total (the teardown inventory) |
| `exito`, `exitos` | success, successes |
| `marca`, `fuente`, `fecha`, `valor`, `unidad` | mark, source, date, value, unit (price lists) |

### Prompt caching (week 20, activity 3)

| Term | Meaning |
|---|---|
| `CACHE_PROMPT` | the agent's prompt-cache mode (`ia/config.py`, and the Lambda variable): `off`, `sistema`, `historial`, `historial+sistema` |
| `sistema` (cache mode) | system: one cache point after the system prompt and the tools |
| `historial` (cache mode) | history: the cache point at the end of the message history, which advances each step |
| `CACHE_TTL` | the cache's time to live: `5m` or `1h` |
| `cache_lectura`, `tokens_cache_lectura` | cache read tokens (billed at 0.1× input) |
| `cache_escritura`, `tokens_cache_escritura` | cache write tokens (billed at 1.25× input with 5 minutes, 2× with 1 hour) |
| `sin_cache` | uncached input tokens |
| `costo_cache` | the USD of the cache tokens of one task |
| `tokens_equivalentes` | cache tokens counted as the input tokens of the same price (the task budget's token count) |
| `estimar_entrada` | estimate the next call's input |
| `por_llamada`, `pasos_modelo`, `spans_modelo` | per model call: its tokens, cost and duration |
| `duracion_pasos_ms` | each model call's duration, in milliseconds |
| `aciertos_cache`: `posibles`, `leyeron`, `tasa` | cache hits: the calls that could read (the call before wrote), those that read, and the rate |
| `latencia_primer_paso_ms`, `latencia_pasos_siguientes_ms_mediana` | latency of the first step, and the median of the later steps |
| `prefijo_fijo` | fixed prefix: the tool definitions and the system prompt |
| `paso_que_alcanza_el_minimo` | the first step whose prefix reaches the minimum tokens per cache point |
| `razon_chars_por_token` | characters-per-token ratio |
| `optimista`, `pesimista`, `peor`, `equilibrio` | the prediction's scenarios: optimistic, pessimistic, worst, and break-even |
| `p_acierto` | the probability that a call is served where the call before wrote |
| `cache_medicion.json`, `cache_prediccion.json`, `cache_comparacion.json` | the offline measurement, the prediction committed before the run, and the comparison after it |

## Command-line flags

The scripts take Spanish flags. Step 4 of the English pass adds the English alias on each flag. Until then:

| Flag | Meaning | Flag | Meaning |
|---|---|---|---|
| `--si` | yes: act for real (without it, a script only simulates) | `--simular` | simulate, call nothing |
| `--confirmo-gasto` | I confirm the spend (a paid run) | `--tope`, `--tope-usd` | spending cap, in USD |
| `--salida` | output path | `--informe` | report path |
| `--modelo`, `--modelos` | model(s) | `--esfuerzo` | reasoning effort |
| `--perfil` | AWS profile, or deployment profile (`lab`, `prod`) | `--todo` | everything |
| `--borrar` | delete | `--detener` | stop |
| `--reiniciar` | restart | `--reanudar` | resume |
| `--limite` | limit (items per language) | `--paralelo`, `--hilos` | parallel workers, threads |
| `--tareas`, `--casos` | tasks, cases | `--idiomas` | languages |
| `--corrida` | run name | `--repeticiones` | repetitions |
| `--desde`, `--hasta` | from, until (UTC) | `--antes`, `--despues` | before, after |
| `--revisar` | review | `--verificar`, `--validar` | verify, validate |
| `--reevaluar` | recompute the metrics of a saved detail file, without a model | `--actualizar-base` | update the baseline |
| `--con-modelo`, `--sin-claude` | with a model, without Claude | `--sin-historial` | without conversation history |
| `--sin-subagentes` | without subagents | `--solo`, `--solo-reporte` | only, report only |
| `--emisor` | token issuer (OAuth) | `--transporte` | MCP transport |
| `--usuario`, `--operador` | user, operator | `--nombre` | name |
| `--muestreo` | sampling | `--trazas` | traces |
| `--presupuesto` | budget | `--reglas` | business rules |
| `--esquema` | schema | `--estado` | status |
| `--puerto` | port | `--archivo` | file |

The audit lists all 136 Spanish flags, script by script ([language-audit-files.tsv](language-audit-files.tsv), column
`es_flags`).

## AWS stacks and resources

| Name | Meaning |
|---|---|
| `semana19-control` | control stack, deployed first: the budget and its action, the deploy role, the permissions boundary and the CloudFormation execution policies |
| `semana19-base` | network and key: the VPC (isolated subnets, no internet gateway, no NAT), the VPC endpoints, the project's KMS key, the flow logs |
| `semana19-datos` | data: RDS PostgreSQL with the legacy schema, the knowledge base's documents bucket, the knowledge base on S3 Vectors |
| `semana19-ia` | AI: the Bedrock Guardrail and the Prompt Management prompts (ES and EN), each at a fixed version |
| `semana19-computo` | compute: Cognito, the HTTP API, the Lambda functions (queries, agent, tools, approver, order writer), DynamoDB, the Step Functions approval |
| `semana19-gateway`, `semana19-agentes-comparacion` | disposable stacks of activity 7: the AgentCore Gateway, and the comparison of agent runtimes |
| `semana19-eval` | disposable stack of activity 8: the LLM judge's bucket and role |
| `semana19-limite` | the permissions boundary of every role the stacks create |
| `semana19-cfn-exec`, `semana19-cfn-exec-*` | CloudFormation execution policies, split by stack |
| `semana19-cdktoolkit` | the CDK bootstrap stack of week 19 |
| `semana19-aprobacion`, `semana19-usuarios`, `semana19-kb`, `semana19-flow-logs` | the approval state machine, the Cognito user pool, the knowledge base, the flow logs' role |
| `semana19-prueba-accion-negar`, `semana19-prueba-accion-objetivo` | the budget-action test: a deny-all policy and the test role it is attached to |
| `semana19-despliegue`, `semana19-lectura` | AWS CLI profiles (not stacks): the deploy role for `cdk deploy` and `cdk destroy`; a read-only role for inventory, verification and Cost Explorer |
| `semana19-operador` | the operator identity named in the plan (in week 19 it resolves to the same IAM user as the admin) |
| `copilot_ro`, `copilot_nlq` | the database's read-only roles |
| `legado` | the PostgreSQL schema that holds the legacy views |

## The legacy schema

The legacy database uses cryptic names, as many old business systems do. The names are the point of the exercise,
so they stay. Each name is a prefix (the entity) plus a suffix (the field or the kind of table).

**Tables of weeks 10 to 20** (schema `legado`, views over the inventory-copilot tables):

| Table | Original table | Meaning | Columns |
|---|---|---|---|
| `prvmst` | `suppliers` | supplier master | `prv_id` id, `prv_nm` name, `prv_pais` country (ISO 3166-1 alpha-2), `prv_dte` agreed lead time in days |
| `artmst` | `products` | article (SKU) master | `art_cd` SKU code, `art_dsc` description, `art_lin` product line, `art_cst` unit cost in MXN, `art_ptr` reorder point, `art_crt` critical flag, `art_prv` supplier |
| `almmst` | `warehouses` | warehouse (distribution center) master | `alm_id` id, `alm_dsc` name, `alm_cdd` city |
| `exidet` | `stock` | stock per article and warehouse | `exi_art` article, `exi_alm` warehouse, `exi_qty` stock on hand, `exi_fup` last update |
| `vtadia` | `sales_daily` | daily sales per article | `vta_art` article, `vta_fch` date, `vta_und` units sold |
| `ocpcab` | `purchase_orders` | purchase order header | `ocp_id` id, `ocp_art` article, `ocp_qty` quantity, `ocp_sts` status (`PENDING_APPROVAL`, `APPROVED`, `REJECTED`), `ocp_fcr` created at |
| `artnot` | — | free-text notes per article (week 13: they carry injected instructions) | `not_id`, `not_art`, `not_txt` text, `not_fch` date |
| `movinv` | — | stock movements (week 16) | `mov_tip` type (`ENT` in, `SAL` out), `mov_qty` quantity, `mov_uni` unit (`PZA` piece, `CJA` box, `KG`), `mov_fch` date, `mov_usr` user |
| `prvcto` | — | supplier contacts (week 16, personal data) | `cto_nom` name, `cto_crg` job title, `cto_eml` email, `cto_tel` phone, `cto_rfc` tax id, `cto_alt` registration date |

**Tables of week 3** (the LegacyBridge billing schema):

| Table | Meaning |
|---|---|
| `faccab`, `facdet` | invoice header, invoice lines |
| `clientes` | customers |
| `invart`, `invexi`, `invmov` | inventory articles, stock cutoffs, stock movements |

Prefixes: `art` article, `alm` warehouse (*almacén*), `exi` stock (*existencia*), `vta` sale (*venta*), `ocp` purchase
order (*orden de compra*), `prv` supplier (*proveedor*), `mov` movement, `cto` contact, `not` note, `fac` invoice
(*factura*), `inv` inventory. Suffixes: `mst` master, `det` detail, `cab` header (*cabecera*), `dia` daily, `_cd` code,
`_dsc` description, `_nm`/`_nom` name, `_qty` quantity, `_fch` date (*fecha*), `_sts` status, `_und`/`_uni` unit.

## Business vocabulary

The corpus and the gold sets describe a fictional Mexican distributor. These words appear in quoted questions and
answers:

| Term | Meaning |
|---|---|
| CEDIS (*centro de distribución*) | distribution center. CEDIS Norte, Occidente: the north and west centers |
| SKU | stock-keeping unit |
| existencia | stock on hand |
| punto de reorden | reorder point |
| orden de compra | purchase order |
| remisión | delivery note |
| merma, caducidad | shrinkage, expiration |
| andén | loading dock |
| devolución, reclamación | return, customer claim |
| flete, tarifa | freight, rate |
| viáticos | travel expenses |
| inventario cíclico | cycle count |
| RFC | Mexican taxpayer id (*Registro Federal de Contribuyentes*) |
| IVA | value-added tax |
| MXN | Mexican pesos |
| serie, folio | invoice series and number |
| alfa, beta | the two tenants of the multi-tenant tests |

## Word list

Spanish words used in folder names, file names, JSON and CSV keys and flags. Words that are the same in English
(`api`, `sql`, `tokens`) are left out.

| Spanish | English | Spanish | English | Spanish | English |
|---|---|---|---|---|---|
| accion | action | actividad | activity | activos | active |
| actualizar | update | adaptador | adapter | administrado | managed (the service parses and chunks) |
| adoptado | adopted | afectadas | affected | afinar | fine-tune |
| agente | agent | ajeno | another (tenant's) | alcance | scope |
| alcanzado | reached | almacen | warehouse | amenazas | threats |
| analisis | analysis | analista | analyst | andenes | loading docks |
| anio | year | aprobacion | approval | aprobadores | approvers |
| archivo | file | arnes | harness | arquitectura | architecture |
| arrancar | start | articulo | article (SKU) | asincrono | asynchronous |
| asistente | assistant | ataque | attack | atribucion | attribution |
| atributos | attributes | auditar | audit | autorizacion | authorization |
| avanzado | advanced | bitacora | log | bloqueos | blocks |
| borrar | delete | bucle | loop | buscar | search |
| cada | each | cadenas | chains | caducidad | expiration |
| calibracion | calibration | calidad | quality | cambiadas | changed |
| camino | path | canario | canary | capa | layer |
| capacitacion | training | captura | capture, screenshot | caras | expensive |
| cargar | load | caso | case | catalogo | catalog |
| categoria | category | cierre | close | ciclico | cyclic |
| cita, citas | citation(s) | citadas | cited | clase | class |
| clasificacion | classification | cliente | client, customer | cobertura | coverage |
| comentarios | comments | comparacion | comparison | compartido | shared |
| completa | full | compra | purchase | compradores | buyers |
| computo | compute | comun, comunes | shared, common | conceptos | concepts |
| concurrencia | concurrency | conexion | connection | confirmado | confirmed |
| conjunto | set | consola | console | construccion | construction |
| construir | build | consulta | query | contenedor | container |
| contexto | context | contrasenas | passwords | contrato | contract |
| controlado | controlled (the lab's own chunks) | copiloto | copilot | correcta | correct |
| corregida | corrected | corregir | fix | correo | email |
| correr | run | corrida | run | cortada, cortadas | truncated |
| costo | cost | cotizacion | quotation | creado | created |
| crear | create | credenciales | credentials | creditos | credits |
| criterios | criteria | criticos | critical | crudo | raw |
| cuenta | account | dato, datos | data | definicion | definition |
| degradacion | degradation | delegacion | delegation | demostrar | demonstrate |
| dependencias | dependencies | descartada | discarded | describir | describe |
| descripcion | description | descuentos | discounts | desde | from |
| desplegado | deployed | desplegar | deploy | despliegue | deployment |
| despues | after | destilacion | distillation | destino | destination |
| destruido | destroyed | destruir | destroy | detalle | detail |
| detener | stop | determinista | deterministic | devoluciones | returns |
| dia, dias | day(s) | diagrama | diagram | diccionario | dictionary |
| directo | direct | diseno | design | dispara | triggers |
| disparada | triggered | distinto | different | distribucion | distribution |
| documento | document | ejecuciones | executions | ejecutable | executable |
| ejemplo | example | embalaje | packing | emisor | issuer |
| empaquetado | packaging | empaquetar | package | enriquecido | enriched |
| ensayo | rehearsal, dry run | entorno | environment | entrada | input |
| entregable | deliverable | entrenamiento | training | entropia | entropy |
| envenenado | poisoned | envenenamiento | poisoning | enviadas | sent |
| envios | shipments | equivalencia | equivalence | equivalente | equivalent |
| escanear | scan | escaneo | scan | escenarios | scenarios |
| escribir | write | escritor | writer | escritura | write |
| esfuerzo | effort | esperada, esperado | expected | esquema | schema |
| estadistica | statistics | estado | status, state | estimacion | estimate |
| estimado | estimated | estres | stress | etiquetado | labeling |
| etiquetas | labels, tags | evadir | evade | evaluacion | evaluation |
| evaluador | evaluator | evaluar | evaluate | evento | event |
| evidencia | evidence | excedente | overage | excepciones | exceptions |
| existencia | stock on hand | exito | success | experimentos | experiments |
| exportador | exporter | exportar | export | expuesto | exposed |
| extraccion | extraction | extremo (a extremo) | end (to end) | facturas | invoices |
| falla, fallas | failure(s) | fallidas | failed | falso, falsos | false |
| fase | phase | fecha, fechas | date(s) | fidelidad | faithfulness |
| fijo, fijos | fixed | filtrados | filtered, leaked | finales | final |
| flete | freight | flujo | flow | formato | format |
| fuente | source | fuera | outside | fundamentacion | grounding |
| futuras | future | garantias | warranties | gasto | spend |
| generacion | generation | generar | generate | glosario | glossary |
| grafica | chart | grafo | graph | grupos | groups |
| guardar | save | guardia | guard | guion | script (of the demo) |
| guionado | scripted | herramienta | tool | hibrida | hybrid |
| hilos | threads | historia | history | horas | hours |
| huella | fingerprint | identidad | identity | idioma | language |
| igual | equal | imagenes | images | indexar | index |
| indicadores | indicators | inexistente | nonexistent | informe | report |
| instalacion | installation | instalar | install | instrumentacion | instrumentation |
| intacta | unchanged | integrado | integrated | intencion | intent |
| intentos | attempts | interna | internal | inventario | inventory |
| inyeccion | injection | inyectadas | injected | inyectar | inject |
| jalar | pull | jueces, juez | judges, judge | laboratorio | lab |
| lanzar | launch | latencia | latency | lectura | read |
| legado | legacy | leido, leida | read | libre | free |
| limite | limit | limpiar | clean | limpio | clean |
| linea (base) | baseline | listar | list | llamadas | calls |
| llaves | keys | logistica | logistics | maliciosas, malicioso | malicious |
| manifiesto | manifest | maquina | machine | matriz | matrix |
| maximo | maximum | mediana | median | medir | measure |
| mermas | shrinkage | metricas | metrics | minimo | minimal |
| modelo | model | modificadas | modified | modo | mode |
| motores | engines | muestreo | sampling | multiagente | multi-agent |
| multisalto | multi-hop | multisemilla | multi-seed | navegador | browser |
| navegar | browse | necesarias | required | negocio | business |
| nivel | level | nombre, nombres | name(s) | normalizacion | normalization |
| norte | north | nota, notas | note(s) | nube | cloud |
| nucleo | core | nuevo | new | obedece, obedecen | obeys, obey |
| obediente | compliant | observabilidad | observability | occidente | west |
| oferta | offer | omision, omisiones | omission(s) | operacion | operation |
| operador | operator | orden, ordenes | order(s) | orquestar | orchestrate |
| otro, otra | other | pantalla | screen | paquete | package |
| paradas | stops | paralelo | parallel | parciales | partial |
| pareado | paired | pares | pairs | paro | stop |
| pasaje, pasajes | passage(s) | pasarela | gateway | pasos | steps |
| patrones | patterns | pausa | pause | pedidas | requested |
| pedido | order | perdidas | losses | perfil, perfiles | profile(s) |
| perfilador | profiler | permiso, permisos | permission(s) | personales | personal |
| pesos | weights | peticion | request | pide | asks for |
| piloto | pilot | pizarra | whiteboard | plano | floor plan |
| plantilla | template | politica | policy | por | per |
| positivo, positivos | positive(s) | practica | practice | precio, precios | price(s) |
| preguntar | ask | preparacion | setup | preparar | set up |
| presupuesto | budget | presupuestado | budgeted | previos | earlier |
| primera | first | primitivas | primitives | productos | products |
| prohibidas | forbidden | promedio | mean | propio | own |
| proveedor | supplier, provider | proyeccion | projection | prueba | test |
| publicada | published | puente | bridge | puerto | port |
| puesta (en marcha) | bring-up | puntaje | score | puntuar | score |
| queda, quedan | remains, remaining | rastro | trail | razonamiento | reasoning |
| recalcular | recompute | recepcion | receiving | rechazadas | rejected |
| rechazar | reject | reclamaciones | claims | recuperacion | retrieval |
| recuperadas | retrieved | redaccion | redaction | redundancia | redundancy |
| reescritura | rewriting | reevaluado | rescored | referencia | reference |
| regenerar | regenerate | registrados | recorded | regla, reglas | rule(s) |
| reiniciar | restart | reintentar, reintento | retry | relaciones | relationships |
| remision | delivery note | remoto | remote | reorden | reorder |
| reparto | delivery | repeticion | repetition | reporta | reports |
| reporte | report | reproduccion | replay | requisitos | requirements |
| reservada | reserved | respaldos | backups | respuesta | answer |
| resultado | result | resumen | summary | resumir | summarize |
| retencion | retention | retirado | retired | revelar | reveal |
| revisar | review | riesgos | risks | rol, roles | role(s) |
| rotacion | rotation | rubricas | rubrics | ruteo | routing |
| salida, salidas | output(s) | secretos | secrets | segmento | segment |
| seguimiento | follow-up | seguridad | security | seguro | secure |
| sellos | seals | semana | week | semantico | semantic |
| sensibilidad | sensitivity | servicio | service | servidor | server |
| sesion | session | sin | without | sincrono | synchronous |
| sistema | system | sobre | over, about | solape | overlap |
| solicitud | request | solo | only | sombra | shadow |
| sonda | probe | subagente | subagent | suma | sum |
| sumidero | sink | supresiones | suppressions | tablas | tables |
| tablero | dashboard | tareas | tasks | tarifas | rates |
| temperaturas | temperatures | texto, textos | text(s) | tiempos | times |
| tipo | type | todo | all | transferencias | transfers |
| transporte | transport | trayectoria | trajectory | trazas | traces |
| turno, turnos | turn(s) | unidad, unidades | unit(s) | uso | use, usage |
| usuario | user | vaciar | empty | valida, valido | valid |
| validacion | validation | validado | validated | validar | validate |
| variabilidad | variability | variantes | variants | verdad | truth |
| veredicto | verdict | verificacion | verification | verificar | verify |
| versionados | versioned | versiones | versions | vez | time (once, twice) |
| vias | paths | viaticos | travel expenses | vigentes | current |
| vistos | seen | vivo | live | | |

## Term list: one English term per concept

The English text of the repository uses one term for each concept. Step 3 of the English pass applies this list,
and new text follows it. A note in parentheses after a term in the Not column limits the rule:

- *(in prose)*: the term stays allowed in code, names and recorded keys, which are quoted in backticks;
- *(alone)*: the short form is allowed once the same file has used the full term;
- *(for …)*: the term is avoided only in that sense; its other senses are ordinary English.

Two style rules go with the list: no space between a number and the percent sign (`12%`, not `12 %`), and the section
on what a result does not cover is titled "Limitations", not "Limits".
[docs/tests/test_terminology.py](tests/test_terminology.py) checks the prose of the documentation against this list.

| Use | Not | Concept |
|---|---|---|
| gold set | golden set, golden dataset | a frozen evaluation set with reference answers |
| ground truth | reference truth | the frozen expected findings of an audit (week 16) |
| reference answer | gold answer | the expected answer of one gold-set item |
| run | execution (for a run), trial | one recorded execution of an experiment or eval |
| baseline | base line, line base | the measurement before a change |
| exit criterion, exit criteria | completion criterion | the condition that closes a week or a phase |
| activity | task (for a unit of a week's plan) | a numbered unit of a week's plan |
| task | activity (for an agent's work) | one item an agent must solve |
| results file | output file | a file under `resultados/` |
| evidence | proof | the recorded files a number links to |
| LLM judge | LLM-as-a-judge, grader model | a model that scores outputs against a rubric |
| execution accuracy | exact-match accuracy | SQL scored by running it and comparing result sets |
| abstention, abstain | refusal (for an abstention), decline (for an abstention) | the agent does not answer because it should not |
| teardown, tear down | destruction, cleanup (for a teardown) | deleting the deployed stacks |
| read-only | read only, readonly | (adjective) |
| purchase order | PO (in prose), order (for a purchase order) | `ocpcab` row |
| distribution center | DC, warehouse center | CEDIS |
| stock on hand | on-hand stock, inventory level | `exi_qty` |
| data dictionary | dictionary (alone) | |
| prompt injection | injection attack (alone) | instructions hidden in data that reach the model |
| tool poisoning | poisoned tool | an MCP tool whose description carries instructions |
| follow-up question | follow up, followup | |
| multi-tenant | multitenant | (in prose; `multitenant` stays in file names) |
| cost per query | cost per request, cost per call | the cost of one request to the deployed system |
| cost per question | cost per item | the cost of one gold-set question in an eval |
| quotation | quote (for a quotation), cost estimate | `cotizacion.md`, the predicted cost |
| dry run | dry-run (in prose), simulation (for a dry run) | a run that calls nothing (`--simular`) |
| email | e-mail | |
| human approval | manual approval, HITL (in prose) | a person approves a purchase order |
| spending cap | budget cap, limit (for the spending cap) | `--tope-usd` |
| permissions boundary | permission boundary | IAM |
