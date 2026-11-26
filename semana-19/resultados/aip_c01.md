# AIP-C01: week 19, by exam domain

Each row: concept → the activity → where the lab shows it → its evidence. Status: **measured**, **documented** (with a link), **partial**, **fails** or **pending**; nothing is marked without its evidence. Domains and weights are the exam guide's ([AIP-C01 exam guide](https://docs.aws.amazon.com/aws-certification/latest/ai-professional-01/ai-professional-01.html)).

## D1: Foundation model integration, data management and compliance (31%)

11 concepts.

| Concept | Activity | Where the lab shows it | Evidence | Status |
|---|---|---|---|---|
| Inference profiles (cross-region) versus base model IDs | 1 | `linea_base/verificar.py`, probe `bedrock`, `inference_profiles` | `resultados/linea_base_mac.json`, `bedrock.inference_profiles` | measured 2026-11-12 |
| On-demand quotas for tokens and requests per minute, per model | 1 | probe `cuotas` (Service Quotas `bedrock`) | `resultados/linea_base_mac.json` | measured 2026-11-12 |
| Model availability by region and access | 1 | probe `bedrock`, `list_foundation_models` | `resultados/linea_base_mac.json` | measured 2026-11-12 |
| Inference profiles (`us.`) and quotas as a model choice constraint | 2 | `semana-19/costos/precios.json` (Haiku 4.5 regional, `us.`); Haiku 5.5 quota 0 | `resultados/linea_base.md` H1, H2; Haiku 5.5 quota request in CASE_OPENED | measured |
| Knowledge Base on S3 Vectors with Titan V2 | 2 | `spike/cdk/app_ia.py`, `spike/terraform/ia.tf` | `spike_iac.json` (`ia`), validate and synth | synthesized; not deployed |
| Knowledge Base on S3 Vectors with Titan V2: recall on column-meaning questions | 4 | `infra/cdk/app.py` (`semana19-datos`), the ingestion step of `desplegar.sh` | `resultados/recall_kb.json`: recall@5 and recall@1 5/5 (6 documents, so recall@1 is the stricter check) | measured 2026-11-14 |
| Prompt Management versions pinned in the request path | 5 | stack `semana19-ia` (`AWS::Bedrock::PromptVersion`, ES and EN) | `tests/test_infra_agentes.py` (the pinned version); the deployed agent reads that version | synth tested; deployed in activities 6 to 9 |
| The agent as an MCP client of the gateway with the user's token, behind a flag (`CAMINO_HERRAMIENTAS`) | 7 | `agente/cliente_gateway.py`, `agente/handler.py` | `agentes.md`: path (b) 9/10, p50 15.76 s, 0.2410 USD | measured 2026-11-18 |
| Two tools paths on the same tasks: direct loop against the gateway | 7 | `agentes/comparar.py` | `agentes.md`: (a) 10/10, p50 18.51 s, 0.2405 USD; (b) 9/10, p50 15.76 s, 0.2410 USD | measured 2026-11-18 |
| Bedrock Agents with the same tools as an action group, as a comparison | 7 | stack `semana19-agentes-comparacion` (#253), its offline tests | `agentes.md`: `CreateAgent` refused by the service ("Maintenance Mode ... accounts without prior service usage"); nothing measured | fails (AWS restriction on the account) |
| Which week 13 to 17 controls survive each orchestration option | 7 | `agentes.md`, "What survives on each path" | (a) and (b) keep budgets, deterministic layer and spans; (c) from the design: loses them | documented (c from the design) |

## D2: Implementation and integration (26%)

11 concepts.

| Concept | Activity | Where the lab shows it | Evidence | Status |
|---|---|---|---|---|
| Converse API with Guardrail | 2 | `semana-19/arquitectura/diagrama.mmd` (agent → Converse); Guardrail in both IaC tools | `resultados/spike_iac.json` (`guardrail_y_kb`) | design and synth; not invoked |
| Prompt Management versions in the request path | 2 | diagram node "Prompt Management version" | `arquitectura/diagrama.svg` | design |
| Serverless patterns: Lambda outside the VPC, HTTP API with JWT, Step Functions with `waitForTaskToken` | 2 | `arquitectura/adr/0002`, `0004`, `0005` | ADRs and the diagram | design; prices M or N per item |
| Deploy in two steps: control by CLI (no assets, no bootstrap) and the bootstrap after it, trusting only the deploy role | 3 | `desplegar.sh` | `test_desplegar_sin_si_no_llama_a_aws`; real runs in activities 3 to 9 (`tiempos_despliegue.jsonl`) | measured |
| AgentCore Gateway with a Lambda target and the tool schemas from one source | 7 | `infra/cdk/app.py` (stack `semana19-gateway`), `gateway/herramientas.json`, `gateway/esquemas.py` | `agentes/crudo_gateway.json`: 10 tasks through the gateway, tool spans `gen_ai.tool.type` = `extension` | measured 2026-11-18 |
| Inbound auth with the Cognito pool (`CUSTOM_JWT`), outbound with the gateway's IAM role | 7 | `infra/cdk/app.py`, `tests/test_infra_gateway.py` | `agentes/politica_en_vivo.json`: real tokens of analista, comprador and aprobador accepted; the role invokes only the tools function | measured 2026-11-18 |
| AgentCore Policy (Cedar) in ENFORCE: protected tool per scope, separation of duties, requester equal to the token's `sub`, `tools/list` filtered per user | 7 | `gateway/politicas/*.cedar`, `tests/test_gateway_politicas.py` | `agentes/politica_en_vivo.json`: 4 of 4 calls as expected (3 denied with −32002, 1 allowed); lists per user in `agentes.md` | measured 2026-11-18 |
| AgentCore charges: gateway invocations and Policy authorizations | 7 | Cost Explorer | `agentes.md`: 56 invocations 0.00028 USD, 55 authorizations 0.001375 USD; total 0.001655 USD | measured 2026-11-19 |
| Keyless CI to AWS with GitHub OIDC, and why the required check stays AWS-free | 10 | week 12's `semana-12/infra/aws_ci_oidc.sh`; decision 1.4 of activity 10 | not used in week 19: an OIDC failure would block the required check, and PRs from forks get no OIDC token | documented |
| A deploy and teardown runbook with measured times | 10 | `semana-19/README.md` | `tiempos_despliegue.jsonl`, `base.md` | measured |
| Verifiable exit criteria: each part of criterion 19 linked to its evidence | 10 | root `README.md`, `docs/exit-criteria.md` | 8 parts, each with its evidence file: 6 met; KMS at rest partial (H10, H14); the mini eval in regression, 9/20 | done 2026-11-23 |

## D3: AI safety, security and governance (20%)

27 concepts.

| Concept | Activity | Where the lab shows it | Evidence | Status |
|---|---|---|---|---|
| Free tier and credits as cost controls | 1 | probe `cuenta` (Free Tier API) and Billing screen | `resultados/linea_base.md` §1: plan PAID measured; credits US$142 with no expiry (D, Billing) | measured (plan) + documented (credits) |
| Budgets with alerts at actual and forecast thresholds | 1 | `infra/presupuesto.py`, deployed in `semana19-control` (activity 3) | the production budget `semana19` read 4.953 USD of gross spend (`seguridad.md`, step 4.5); its action was tested live in activity 9 | measured 2026-11-22 |
| Least-privilege readiness: named admin and operator profiles, no access keys | 1 | `preparar/verificar_entorno.py` | activity 1: admin and operator were one identity (`linea_base.md` §7); activity 3 added the read-only role `semana19-lectura` and the deploy role `semana19-despliegue` (`base.md`) | measured (fixed in activity 3) |
| Tag-based resource inventory and teardown evidence | 1 | `infra/inventario.py` (Tagging API plus name prefix) | `"quedan": "nada"` from the Mac run | measured 2026-11-12 |
| KMS key pending deletion billing | 1 | KMS pricing page (not a catalog item) | `resultados/linea_base.md` §3 (D, with a link) | documented |
| KMS key policy vs IAM policy: the key policy must allow the principal even if IAM does; roles named, root delegates with `kms:*` | 3 | `infra/cdk/app.py` (`Base`, key policy), `infra/cdk/excepciones.py` (RaizDeLaCuenta) | `test_infra_cdk.py` (no open principal; roles named) | synth tested, not deployed |
| `kms:ViaService` / encryption context for a service principal (CloudWatch Logs) | 3 | `LogsDelProyectoConLaLlave` (ArnLike on `kms:EncryptionContext:aws:logs:arn`) | test on the EncryptionContext condition | synth tested |
| Permissions boundary and delegation of role creation (`iam:CreateRole` only with the boundary) | 3 | `politica_limite`, `politica_ejecucion_cfn`, `Despliegue` | `test_todo_rol_creado_por_los_stacks_tiene_el_limite`, `test_despliegue_crea_roles_solo_con_limite` | synth tested |
| Gateway endpoint (S3, route tables, no hourly charge) vs interface endpoint (ENI per AZ, hourly and per GB) | 3 | `Base` (`EndpointS3`, `EndpointLogs`, `EndpointStepFunctions`) | ADR 0005 and 0006, `test_endpoints_son_exactamente_los_del_adr_0005` | synth tested |
| Endpoint policy limited by `aws:PrincipalAccount` | 3 | `politica_cuenta` in `Base` | `test_endpoints_limitados_a_la_cuenta` | synth tested |
| VPC flow logs to an encrypted group with short retention | 3 | `GrupoFlowLogs`, `FlujosDeLaRed` | `test_flow_logs_con_retencion_del_perfil` | synth tested |
| Budget action (APPLY_IAM_POLICY at 100%) and why it must not block deletes | 3 | `AccionPresupuesto`, `CREAR_Y_ACTUALIZAR` | `test_la_congelacion_no_bloquea_borrar` | synth tested; limitation (bootstrap roles) in `resultados/base.md` |
| Cost Anomaly Detection (not deployed: its price is N) | 3 | not in the stack | `test_sin_monitor_de_anomalias_hasta_confirmar_su_precio` | price N |
| Log retention in every group | 3 | `RetencionDeLogs` aspect | `test_todos_los_grupos_de_logs_usan_la_llave_y_tienen_retencion` | tested |
| Bedrock Guardrail as code against a deterministic layer on the same inputs | 5 | `guardrail/comparar_determinista.py`, stack `semana19-ia` | `resultados/comparacion_determinista.json`: 20 golden inputs, 0 blocked by either; 4 attacks, the Guardrail intervened on 1, the deterministic layer blocked 3 (2 tool-definition injections the Guardrail let through) | measured 2026-11-15 |
| Threat model per trust boundary (STRIDE), mapped to OWASP LLM Top 10 | 9 | `seguridad/threat_model.md`, `resultados/seguridad.md` | 11 boundaries, H1–H14, each with its OWASP LLM category | documented |
| Secret scanning of the history and the synthesized templates | 9 | `seguridad/escaneo_secretos.py` (gitleaks) | `resultados/seguridad/secretos.json`: 0 unclassified | measured 2026-11-21 |
| IaC policy scanners with justified suppressions | 9 | checkov and cdk-nag, `seguridad/supresiones.py` | `resultados/seguridad/supresiones.json`: 0 failed, 0 unsuppressed | measured 2026-11-21 |
| IAM Access Analyzer ValidatePolicy, and its false positives | 9 | `seguridad/validar_politicas.py` | `validate_policy.json`: 0 errors; 4 INVALID_ACTION disproved by a live AccessDenied (#306) | measured 2026-11-21 |
| IAM Access Analyzer external access findings | 9 | analyzer of type ACCOUNT, created and deleted | `resultados/seguridad/access_analyzer.json`: 61 analyzed, 0 findings | measured 2026-11-22 |
| Unused access analyzer: what it evaluates and what it bills | 9 | `resultados/seguridad/estimacion.md` | not created: entities younger than the tracking period are not evaluated; 0.20 USD per role or user per month | documented |
| Read-only verification of encryption, public exposure and network | 9 | `seguridad/verificar_desplegado.py` | `verificacion.json`: 5 of 6 ok; H14 new | measured 2026-11-22 |
| Reading a CMK-encrypted Bedrock resource needs kms:Decrypt as well as the Get action | 9 | `semana19-lectura` with `bedrock:GetGuardrail` and `GetPrompt` | still AccessDenied ("insufficient permissions to access this guardrail") | measured 2026-11-22 |
| Indirect prompt injection through data and through a Knowledge Base | 9 | `seguridad/envenenamiento.py`, direct `Retrieve` | 0 of 8 obeyed, twice; poisoned chunks ranked first in Retrieve, unreachable by the agent (H2) | measured 2026-11-22 |
| Sanitizing tool results before the model (defense in depth beside the Guardrail) | 9 | `agente/handler.py` (#310) | 6 of 6 notes sanitized after the fix; the Guardrail blocked 0 in both runs; residual iny-d3 | measured 2026-11-22 |
| Budget action that applies an IAM deny policy, and why it must count gross spend | 9 | `seguridad/prueba_accion_presupuesto.py` (#311, #312) | EXECUTION_SUCCESS: deny policy attached to the test role; the first budget, net of credits, read 0.0 USD and never fired | measured 2026-11-22 |
| Cost of a security review, read back by service and record type | 9 | `seguridad/costo_actividad9.py` (#316) | about 0.73 USD of usage against an estimate of 0.52 nominal and 0.89 upper; the model line reconciles with the spans | measured 2026-11-23 |

## D4: Operational efficiency and optimization (12%)

15 concepts (9 from week 19, 6 from week 20's activity 3).

| Concept | Activity | Where the lab shows it | Evidence | Status |
|---|---|---|---|---|
| Model choice by cost per token against fixed cost per hour | 2 | `semana-19/costos/modelo.py` (per query and per hour, two profiles) | `resultados/cotizacion.md`, per query 0.0799 USD and per hour 0.0219 USD (lab, partial) | measured (partial: endpoints N) |
| Fixed cost versus variable cost (zero queries is only the fixed part) | 2 | `costos/modelo.py` and `tests/test_costos.py` (zero queries test) | `cotizacion.md`: 5.44 USD/month lab with 0 queries (partial) | measured |
| Tokens and model cost per task from the agent spans | 8 | `eval_aws.py` (costo) | 0.035544 USD and 26,647.4 tokens per task (19 tasks) | measured 2026-11-19 |
| Prompt caching on Converse needs a `cachePoint` | 8 | `agente/converse_adaptador.py` (cache tokens read, none sent) | 0 cache read and 0 cache write tokens on every task | fails (not used) |
| Where a cache point can go: the model's minimum per point, counted on the whole prefix | week 20, 3 | `semana-20/cache/medir.py`, ADR 0014 | the fixed prefix (tools and system) is 2,664 tokens, under Haiku 4.5's 4,096, so the point goes at the end of the history (`resultados/cache_medicion.json`) | measured 2026-11-25 |
| Cache TTL by the reuse pattern (5 minutes against 1 hour) | week 20, 3 | ADR 0014, `CACHE_TTL` | the calls of a query are seconds apart and no two queries share a prefix: 1 hour would cost 0.602 USD for the 20 tasks against 0.511 | decided 2026-11-25 |
| Caching saving predicted before the run, with the cross-region hit rate as scenarios | week 20, 3 | `costos/modelo.py` v3, `semana-20/cache/prediccion.py` | 45.0% (every call reads), 3.9% (1/3), −16.7% (none); break-even 0.27; real total within −0.9% of the central (`cotizacion.md`) | measured 2026-11-26 |
| Caching saving measured on the same tasks | week 20, 3 | `semana-20/cache/corrida.py` | 20 tasks: 0.927825 → 0.505822 USD (−45.5%), p95 −52.5%, 55 of 55 possible reads hit, success 17/20 against 16/20 (`semana-20/resultados/cache.md`) | measured 2026-11-26 |
| Cache tokens in the task budget, the span cost and EMF, at their prices | week 20, 3 | `agente/presupuesto.py`, `agente/handler.py` | read 0.1× and write 1.25× input; the test's hand case is 0.007744 USD and 6,240 equivalent tokens (`tests/test_agente_cache.py`) | tested |
| Latency effect of caching | week 20, 3 | the chat spans' durations (`cache_detalle.jsonl`) | no gain at 3,000 to 12,000-token prefixes: task latency over its calls 4.08 s against 4.11 s without the cache | measured 2026-11-26 |
| Per-task token budget calibrated per model | 8 | `agente/construccion.py` (week 17's 46,000 tokens, Haiku 5.5) | 5 of 20 tasks stopped by it on Haiku 4.5 | fails |
| Real cost per query from the bill, reconciled with the spans (other activities' runs on the same UTC day set apart) | 8 | `eval/costo_real.py` | `resultados/costo_real.md`: 0.030913 USD per task for the model alone, 0.038562 USD with every per-query line (upper bound), 57 tasks; the Haiku line minus activity 7's runs equals the spans to the cent | measured 2026-11-21 |
| Quotation error and the model's correction, both versions kept | 8 | `costos/modelo.py --version v1/v2` | `cotizacion.md`: v1 −61.3% per query (model part), v2 −0.1%; per hour −10.3% (lab), prod n/a | measured 2026-11-21 |
| Fixed per hour against per query, from the bill | 8 | `costo_real.FIJOS`, `FUERA` | 0.037562 USD per hour over 26.004 h; VPC above the model (3 interface endpoints, not 2), RDS below (cause not verified) | measured 2026-11-21 |
| Real cost per query from Cost Explorer by the `proyecto` tag, against activity 2's model | 8 | `eval/costo_real.py` | `costo_real.md` (the row above: 0.030913 USD per task for the model, 0.038562 USD upper bound) | measured 2026-11-21 |

## D5: Testing, validation and troubleshooting (11%)

13 concepts.

| Concept | Activity | Where the lab shows it | Evidence | Status |
|---|---|---|---|---|
| Evaluation against the deployed endpoint: public API, real Cognito tokens, execution-based verifier, Wilson 95% CI per language | 8 | `eval/eval_aws.py` | `resultados/eval_aws.md`: 9/20, CI [0.258, 0.658]; es 7/10, en 2/10 | measured 2026-11-19 |
| Regression rule against a baseline (week 10's threshold, week 17 local 20/20) | 8 | `eval_aws.comparar` | `eval_aws.md`: regression yes in es, en and total | measured 2026-11-19 |
| Trajectory graders on the deployed agent's spans (week 17) | 8 | `eval_aws.py` with week 17's graders | 17 graded, 7 OK, mean score 0.923; failing: pasos (9), recall_herramientas (1) | measured 2026-11-19 |
| Cold and warm latency reported apart (Lambda REPORT lines) | 8 | `eval_aws.py` | cold n = 1, 49.95 s; warm n = 17, p50 23.52 s, p95 30.13 s | measured 2026-11-19 |
| Diagnosis from the run's evidence: missing tools in the port (run 1), a per-task budget the deployed model outgrows (run 3) | 8 | `crudo_eval_descartada_1.json`, `crudo_eval.json` | `eval_aws.md` "Analysis": 5 tasks ended `presupuesto_tarea` at 36,797–42,692 tokens | measured 2026-11-19 |
| Hard caps in the eval script; aborted tasks reported as such | 8 | `TOPE_USD`, `TOPE_TOKENS`, `tope_con_lo_previo` | 3 tasks `no_corrida` / `tope_del_script` in the official run | measured 2026-11-19 |
| Human approval end to end (wait, 403 for the analyst, approval, writer role, expiry) | 8 | `eval/aprobacion_e2e.py` | `eval_aws/aprobacion_e2e.json`: every check passed, 0.023269 USD | measured 2026-11-19 |
| Bedrock model evaluation job, LLM as a judge with built-in metrics on precomputed answers (task type `General`) | 8 | `eval/juez_bedrock.py` | `eval_aws/juez_bedrock.json`: Nova Pro, 17 tasks judged, Completed in 543 s | measured 2026-11-19 |
| Where an LLM judge is and is not enough for SQL answers: agreement, kappa, false passes and false fails | 8 | `eval/comparar_jueces.py` | agreement 0.8, kappa 0.5946 (n = 15); false fails s03-es, s03-en (incomplete context); false pass c02-en | measured 2026-11-19 |
| IaC tests in CI with no AWS: synth of every stack, cdk-nag, checkov, gitleaks, no skipped test | 10 | `.github/workflows/eval-semana-19.yml` (jobs `sin-aws`, `spike-iac`) | #318: 707 tests in `sin-aws` and 226 in `spike-iac` passed, 0 skipped; `supresiones.py` verdict ok | measured 2026-11-23 |
| Offline IAM policy linting in CI, every finding classified with its reason | 10 | `seguridad/parliament_offline.py` (#318) | `resultados/seguridad/parliament.json`: 50 policies per profile, 150 findings, 0 unclassified | measured 2026-11-23 |
| A test that the architecture diagram matches the synthesized resources, both ways | 10 | `tests/test_diagrama_vs_stack.py` (#318) | 22 nodes mapped, every component type drawn or listed with a reason; checked by mutation | measured 2026-11-23 |
| Test coverage reported in CI | 10 | `sin-aws` with pytest-cov 7.1.0 | #318: total 53%, `costos/modelo.py` 82% | measured 2026-11-23 |

## Gaps: what the exam guide asks and week 19 did not show

Read against the exam guide's task statements (domain pages linked above) on 2026-11-23. This is the seed of weeks 23
and 24; the weeks that already plan an item are named.

| Task | What week 19 did not show | Where it may come |
|---|---|---|
| 1.2.2, 2.4.4, 2.2.3 | Switching models without code changes, model routing and cascading: the model is one constant (`ia/config.py`) | week 20 (routing and cascading) |
| 1.2.4 | Custom models: fine-tuning, adapters, a model registry, rollback | weeks 23–24 (study) |
| 1.3.1, 1.3.2 | Data quality pipelines (Glue Data Quality) and multimodal inputs | weeks 23–24 |
| 1.4.3, 1.4.5, 1.5.4, 1.5.5 | Vector index tuning, keeping the KB current, hybrid search with reranking, query expansion. The KB is deployed but off the request path (H2) | week 20 (H2), weeks 23–24 |
| 1.6.2, 1.6.6, 2.1.1 | Conversational memory and Prompt Flows; agent frameworks with memory (Strands, Agent Squad) | weeks 23–24 |
| 2.2.1, 4.1.3, 4.2.3 | Provisioned throughput, batch inference and capacity planning | week 20 (batch inference) |
| 2.3.5 | CI/CD with CodePipeline and CodeBuild: the lab's CI is GitHub Actions | weeks 23–24 |
| 2.4.2, 2.5.1 | Streaming responses: the API is asynchronous with polling (ADR 0007) | weeks 23–24 |
| 2.4.3, 2.5.6, 5.2.5 | X-Ray tracing: spans go to CloudWatch Logs only | week 20 |
| 3.2.2, 3.2.3 | PII detection and masking (Comprehend, Macie, Guardrail sensitive information filters) | week 21 (red teaming) or weeks 23–24 |
| 3.3.1, 3.4.2 | Model cards, lineage, fairness metrics | weeks 23–24 |
| 4.1.4 | Semantic caching. Prompt caching is shown since week 20, activity 3 (D4 above); partly closed | weeks 23–24 |
| 4.3.1, 4.3.2 | Dashboards and GenAI KPIs, Bedrock model invocation logging | week 20 |
| 5.1.2, 5.1.3 | A/B and canary tests of configurations; user feedback | weeks 23–24 |
| 5.1.7 | Bedrock Agents evaluation: Bedrock Agents refused new agents in this account (activity 7) | not reachable in this account |

