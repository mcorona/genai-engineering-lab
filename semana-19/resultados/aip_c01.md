# AIP-C01: running list (week 19)

Each row: concept → where the lab shows it → evidence. Status: **medido** (M), **D** (documentado con enlace), **parcial** or **falla**; nothing is marked without its evidence. Domains: D1 FM integration and data (31%), D2 implementation (26%), D3 security and governance (20%), D4 efficiency (12%), D5 testing and troubleshooting (11%).

## Activity 1 (D1, D3)

| Concept | Domain | Where the lab shows it | Evidence | Status |
|---|---|---|---|---|
| Inference profiles (cross-region) versus base model IDs | D1 | `linea_base/verificar.py`, sonda `bedrock`, `inference_profiles` | `resultados/linea_base_mac.json`, `bedrock.inference_profiles` | medido 2026-11-12 |
| On-demand quotas for tokens and requests per minute, per model | D1 | sonda `cuotas` (Service Quotas `bedrock`) | `resultados/linea_base_mac.json` | medido 2026-11-12 |
| Model availability by region and access | D1 | sonda `bedrock`, `list_foundation_models` | `resultados/linea_base_mac.json` | medido 2026-11-12 |
| Free tier and credits as cost controls | D3 | sonda `cuenta` (Free Tier API) and Billing screen | `resultados/linea_base.md` §1: plan PAID medido; créditos US$142 sin vencimiento (D, Billing) | medido (plan) + D (créditos) |
| Budgets with alerts at actual and forecast thresholds | D3 | `infra/presupuesto.py` (simulation, tested) | `semana-19/tests/test_preparacion.py` | en simulación |
| Least-privilege readiness: named admin and operator profiles, no access keys | D3 | `preparar/verificar_entorno.py` | operador y admin son la misma identidad (`linea_base.md` §7): excepción abierta | falla |
| Tag-based resource inventory and a teardown proof | D3 | `infra/inventario.py` (Tagging API plus name prefix) | `"quedan": "nada"` from the Mac run | medido 2026-11-12 |
| KMS key pending deletion billing | D3 | KMS pricing doc (no es artículo del catálogo) | `resultados/linea_base.md` §3 (D con enlace) | D |

## Activity 2 (D1, D2, D4)

| Concept | Domain | Where the lab shows it | Evidence | Status |
|---|---|---|---|---|
| Model choice by cost per token against fixed cost per hour | D4 | `semana-19/costos/modelo.py` (per query and per hour, two profiles) | `resultados/cotizacion.md`, per query 0.0799 USD and per hour 0.0219 USD (lab, partial) | medido (partial: endpoints N) |
| Inference profiles (`us.`) and quotas as a model choice constraint | D1 | `semana-19/costos/precios.json` (Haiku 4.5 regional, `us.`); Haiku 5.5 quota 0 | `resultados/linea_base.md` H1, H2; cuota Haiku 5.5 en CASE_OPENED | medido |
| Converse API with Guardrail | D2 | `semana-19/arquitectura/diagrama.mmd` (agent → Converse); Guardrail in both IaC tools | `resultados/spike_iac.json` (`guardrail_y_kb`) | diseño y synth; no invocado |
| Prompt Management versions in the request path | D2 | diagram node "versión de Prompt Management" | `arquitectura/diagrama.svg` | diseño |
| Serverless patterns: Lambda outside the VPC, HTTP API with JWT, Step Functions with `waitForTaskToken` | D2 | `arquitectura/adr/0002`, `0004`, `0005` | ADRs and the diagram | diseño; prices M or N per item |
| Fixed cost versus variable cost (zero queries is only the fixed part) | D4 | `costos/modelo.py` and `tests/test_costos.py` (zero queries test) | `cotizacion.md`: 5.44 USD/month lab with 0 queries (partial) | medido |
| Knowledge Base on S3 Vectors with Titan V2 | D1 | `spike/cdk/app_ia.py`, `spike/terraform/ia.tf` | `spike_iac.json` (`ia`), validate and synth | sintetizado; no desplegado |

## Activity 3 (D3, D2)

| Concept | Domain | Where in the repo | Evidence | Status |
|---|---|---|---|---|
| KMS key policy vs IAM policy: the key policy must allow the principal even if IAM does; roles named, root delegates with `kms:*` | D3 | `infra/cdk/app.py` (`Base`, key policy), `infra/cdk/excepciones.py` (RaizDeLaCuenta) | `test_infra_cdk.py` (no open principal; roles named) | synth tested, not deployed |
| `kms:ViaService` / encryption context for a service principal (CloudWatch Logs) | D3 | `LogsDelProyectoConLaLlave` (ArnLike on `kms:EncryptionContext:aws:logs:arn`) | test on the EncryptionContext condition | synth tested |
| Permission boundary and delegation of role creation (`iam:CreateRole` only with the boundary) | D3 | `politica_limite`, `politica_ejecucion_cfn`, `Despliegue` | `test_todo_rol_creado_por_los_stacks_tiene_el_limite`, `test_despliegue_crea_roles_solo_con_limite` | synth tested |
| Gateway endpoint (S3, route tables, no hourly charge) vs interface endpoint (ENI per AZ, hourly and per GB) | D3 | `Base` (`EndpointS3`, `EndpointLogs`, `EndpointStepFunctions`) | ADR 0005 and 0006, `test_endpoints_son_exactamente_los_del_adr_0005` | synth tested |
| Endpoint policy limited by `aws:PrincipalAccount` | D3 | `politica_cuenta` in `Base` | `test_endpoints_limitados_a_la_cuenta` | synth tested |
| VPC flow logs to an encrypted group with short retention | D3 | `GrupoFlowLogs`, `FlujosDeLaRed` | `test_flow_logs_con_retencion_del_perfil` | synth tested |
| Budget action (APPLY_IAM_POLICY at 100 %) and why it must not block deletes | D3 | `AccionPresupuesto`, `CREAR_Y_ACTUALIZAR` | `test_la_congelacion_no_bloquea_borrar` | synth tested; limitation (bootstrap roles) in `resultados/base.md` |
| Cost Anomaly Detection (not deployed: its price is N) | D3 | not in the stack | `test_sin_monitor_de_anomalias_hasta_confirmar_su_precio` | price N |
| Log retention in every group | D3 | `RetencionDeLogs` aspect | `test_todos_los_grupos_de_logs_usan_la_llave_y_tienen_retencion` | tested |
| Deploy in two steps: control by CLI (no assets, no bootstrap) and the bootstrap after it, trusting only the deploy role | D2 | `desplegar.sh` | `test_desplegar_sin_si_no_llama_a_aws` | simulation tested; real run pending |

## Activity 8 (D5, D4)

| Concept | Domain | Where in the repo | Evidence | Status |
|---|---|---|---|---|
| Evaluation against the deployed endpoint: public API, real Cognito tokens, execution-based verifier, Wilson 95% CI per language | D5 | `eval/eval_aws.py` | `resultados/eval_aws.md`: 9/20, CI [0.258, 0.658]; es 7/10, en 2/10 | medido 2026-11-19 |
| Regression rule against a baseline (week 10's threshold, week 17 local 20/20) | D5 | `eval_aws.comparar` | `eval_aws.md`: regression yes in es, en and total | medido 2026-11-19 |
| Trajectory graders on the deployed agent's spans (week 17) | D5 | `eval_aws.py` with week 17's graders | 17 graded, 7 OK, mean score 0.923; failing: pasos (9), recall_herramientas (1) | medido 2026-11-19 |
| Cold and warm latency reported apart (Lambda REPORT lines) | D5 | `eval_aws.py` | cold n = 1, 49.95 s; warm n = 17, p50 23.52 s, p95 30.13 s | medido 2026-11-19 |
| Diagnosis from the run's evidence: missing tools in the port (run 1), a per-task budget the deployed model outgrows (run 3) | D5 | `crudo_eval_descartada_1.json`, `crudo_eval.json` | `eval_aws.md` "Analysis": 5 tasks ended `presupuesto_tarea` at 36,797–42,692 tokens | medido 2026-11-19 |
| Hard caps in the eval script; aborted tasks reported as such | D5 | `TOPE_USD`, `TOPE_TOKENS`, `tope_con_lo_previo` | 3 tasks `no_corrida` / `tope_del_script` in the official run | medido 2026-11-19 |
| Human approval end to end (wait, 403 for the analyst, approval, writer role, expiry) | D5 | `eval/aprobacion_e2e.py` | `eval_aws/aprobacion_e2e.json`: every check passed, 0.023269 USD | medido 2026-11-19 |
| Bedrock model evaluation job, LLM as a judge with built-in metrics on precomputed answers (task type `General`) | D5 | `eval/juez_bedrock.py` | `eval_aws/juez_bedrock.json`: Nova Pro, 17 tasks judged, Completed in 543 s | medido 2026-11-19 |
| Where an LLM judge is and is not enough for SQL answers: agreement, kappa, false passes and false fails | D5 | `eval/comparar_jueces.py` | agreement 0.8, kappa 0.5946 (n = 15); false fails s03-es, s03-en (incomplete context); false pass c02-en | medido 2026-11-19 |
| Tokens and model cost per task from the agent spans | D4 | `eval_aws.py` (costo) | 0.035544 USD and 26,647.4 tokens per task (19 tasks) | medido 2026-11-19 |
| Prompt caching on Converse needs a `cachePoint` | D4 | `agente/converse_adaptador.py` (cache tokens read, none sent) | 0 cache read and 0 cache write tokens on every task | falla (not used) |
| Per-task token budget calibrated per model | D4 | `agente/construccion.py` (week 17's 46,000 tokens, Haiku 5.5) | 5 of 20 tasks stopped by it on Haiku 4.5 | falla |
| Real cost per query from Cost Explorer by the `proyecto` tag, against activity 2's model | D4 | `eval/costo_real.py` | pending: the day after (2026-11-20), 2 calls left in the ledger | pendiente |
