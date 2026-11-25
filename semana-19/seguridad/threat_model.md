# Week 19, activity 9: threat model of the deployed LegacyBridge (STRIDE per trust boundary)

Diagram: [`arquitectura/diagrama.mmd`](../arquitectura/diagrama.mmd) (export `diagrama.svg`), updated in this activity to
what activities 6 to 8 built:

- the asynchronous `/consultas` flow (ADR 0007) and its DynamoDB table;
- the task-token table (ADR 0011) and the approver, token-registrar and order-writer Lambdas;
- the pre-token trigger;
- the AgentCore Gateway with Cedar Policy (path b);
- the Secrets Manager endpoint.

The Knowledge Base edge to the agent is drawn dashed: ADR 0008 decided it, but nothing calls `Retrieve` (finding H2).

Base: the week 14 threat model ([`semana-14/seguridad/amenazas.md`](../../semana-14/seguridad/amenazas.md), A01 to
A13). The section [What changed from week 14](#what-changed-from-week-14) maps each of its threats.

## Method

- One block per trust boundary. Each row gives one STRIDE category (S spoofing, T tampering, R repudiation,
  I information disclosure, D denial of service, E elevation of privilege), the asset, the threat, the control, the
  proof (a test as `file::name`, or a live check with its evidence file) and the status.
- **Status:**
  - `offline`: a test that runs in CI without AWS proves it.
  - `live`: a check against the deployed stack proves it, with the evidence file named.
  - `step 2` / `step 4`: the live check is planned in this activity; the result is written to `resultados/seguridad.md`.
  - `not tested`: no test exists. The row says why.
- Test paths are relative to `semana-19/tests/` unless they name another week.
- Findings opened by this review are numbered H1, H2, and so on. Their severity and mitigation are listed in the last
  table of this file and carried to `resultados/seguridad.md`.

## F1 · The user and the API (Cognito, JWT, scopes, throttling)

| ID | STRIDE | Asset | Threat | Control | Proof | Status |
|---|---|---|---|---|---|---|
| T1.1 | S | every route | A forged, expired or other-client token reaches a Lambda | HTTP API JWT authorizer: issuer is the pool, audience is the app client | `test_infra_computo.py::test_ruta_de_aprobacion_exige_el_scope_de_aprobaciones_y_jwt` | offline |
| T1.2 | E | approval route | A user with read scopes calls `POST /aprobaciones/{id}` | Scope per route: `legacybridge/aprobaciones` on approvals, `legacybridge/consultas` on queries | same test; the analyst got HTTP 403 on the approval route (`resultados/eval_aws.md`, approval step 2) | offline + live |
| T1.3 | E | scopes, tenant, level | The user adds scopes or an approval level to the request | Scopes, tenant and level come only from groups, through the pre-token trigger V2. The handlers read the authorizer's claims, never the body | `test_computo.py::test_grupos_se_convierten_en_scopes_y_grupo_desconocido_no_da_nada`; `::test_trigger_v2_anade_scopes_y_el_nivel_del_grupo`; `::test_handler_toma_quien_y_su_nivel_de_los_claims_y_no_del_cuerpo`; `test_computo_tokens_tenant.py::test_el_token_trae_el_tenant_del_laboratorio_aunque_no_tenga_grupos` | offline |
| T1.4 | I | user directory | Account enumeration through sign-in errors | `prevent_user_existence_errors=ENABLED`; public client without secret, code flow with PKCE (ADR 0010) | `test_infra_computo.py::test_cognito_en_essentials_con_cliente_sin_secreto_y_codigo_pkce` | offline |
| T1.5 | S | test users | Password login from scripts in the lab | `ALLOW_ADMIN_USER_PASSWORD_AUTH` only for the two test users' admin login; passwords in a local file (ADR 0013); MFA off in the lab (cdk-nag COG2, suppressed with its reason) | `resultados/seguridad/supresiones.json` (COG2 suppression and its reason) | accepted for the lab; **H6** for prod |
| T1.6 | D | Lambda concurrency, model spend | A flood of `POST /consultas` | Reserved concurrency (consultas 5, agent 2); budgets per task, session and tenant-day (week 17). **No throttling is set on the HTTP API stage** | `test_agente_presupuesto.py::test_tope_de_usd_corta_y_nombra_el_motivo`; the stage has no `DefaultRouteSettings` | not tested; **H1** |

## F2 · The API and the Lambda (routes, event payload, the asynchronous POST and GET /consultas)

| ID | STRIDE | Asset | Threat | Control | Proof | Status |
|---|---|---|---|---|---|---|
| T2.1 | I | other users' answers | A user reads another user's `GET /consultas/{id}` | The owner is stored as a hash of the token's `sub`; another user gets the same 404 as a missing id | `test_consultas.py::test_solo_el_dueno_lee_su_respuesta_y_otro_recibe_404_igual_que_si_no_existiera`; `::test_sin_sujeto_en_el_token_no_hay_acceso` | offline |
| T2.2 | T | the agent's input | A malformed or oversized body | Validation before any write or invoke | `test_consultas.py::test_pregunta_invalida_no_escribe_nada`; `::test_cuerpo_que_no_es_json_es_400` | offline |
| T2.3 | S | identity inside the agent | A token without `sub` or tenant runs the agent | The agent refuses a token without subject or tenant and drops unknown scopes | `test_agente_handler.py::test_identidad_sale_del_token_y_descarta_scopes_desconocidos` | offline |
| T2.4 | D | model spend | A Lambda timeout on the asynchronous invoke is retried, and each retry is a new paid run | `retry_attempts=0` on the agent (this activity); the worker stores `error` on any exception | `test_consultas.py::test_el_trabajador_ante_un_fallo_guarda_solo_el_estado_sin_detalle`; `resultados/seguridad/supresiones.json` (CKV_AWS_116 reason) | offline; a timeout leaves the row `pendiente` until its TTL: **H4** |
| T2.5 | R | who asked what | No trace of a request | API access logs (request id, route, status, latency); spans with the run id from the question's id | `test_infra_computo.py::test_api_tiene_logs_de_acceso`; spans 57/57 in activity 8 (`resultados/eval_aws.md`) | offline + live |
| T2.6 | I | questions, tokens | The question or the exception message is written to logs | The operator log carries the exception type and positions only | `test_consultas.py::test_el_log_de_operador_no_lleva_la_pregunta_ni_el_mensaje_de_la_excepcion` | offline |

## F3 · The Lambda and Bedrock (model, Guardrail, prompts)

| ID | STRIDE | Asset | Threat | Control | Proof | Status |
|---|---|---|---|---|---|---|
| T3.1 | E | Bedrock account-wide | The agent role calls another model or another Bedrock API | Only the Haiku 4.5 inference profile and its foundation models through the profile; exact actions, no `bedrock:*` | `test_ia_politica.py::test_solo_permite_el_perfil_de_haiku_45_y_sus_modelos_subyacentes`; `::test_los_modelos_subyacentes_solo_se_usan_via_el_perfil`; `::test_la_politica_no_tiene_comodines_ni_bedrock_completo` | offline + live (activity 8 ran on the profile) |
| T3.2 | T | the agent's instructions | Prompt injection in the user's question | Deterministic input check before the model; Guardrail `PROMPT_ATTACK` on the input | `test_agente_capa.py::test_inyeccion_se_bloquea_antes_del_modelo`; `test_guardrail.py::test_prompt_attack_solo_en_la_entrada`; ApplyGuardrail run of activity 5 (`resultados/apply_guardrail.json`) | offline + live |
| T3.3 | T | system prompt, Guardrail | A prompt or Guardrail change reaches production unreviewed | Converse always carries a fixed Guardrail version and a Prompt Management version; no Guardrail, no request | `test_ia_peticion.py::test_converse_lleva_modelo_guardrail_y_version_fijada`; `::test_sin_guardrail_no_hay_peticion` | offline |
| T3.4 | I | personal data | PII in the answer | Guardrail anonymizes email and phone and blocks RFC; the deterministic layer redacts the final answer | `test_guardrail.py::test_pii_correo_y_telefono_se_anonimizan_y_rfc_se_bloquea`; `test_agente_capa.py::test_datos_personales_en_la_respuesta_se_redactan` | offline |
| T3.5 | D | model spend | Agent loops or long outputs | Budgets per task, session and tenant-day around every model call | `test_agente_presupuesto.py::test_tope_de_tokens_corta_sin_llamar_al_modelo`; in activity 8 the per-task budget stopped 5 tasks (`resultados/eval_aws.md`) | offline + live |
| T3.6 | T | the agent's tool use | Indirect injection through data returned by a tool (`legado.artnot` already carries the week 13 cases) | Guardrail on the model calls; deterministic checks on every tool call and on the final answer; no write path (F4). **Week 17's sanitizing of tool results (`revisar_resultado`, guardrail `input_resultado_inyeccion`) is not applied by the deployed layer** (`agente/capa_determinista.py` applies the core to the request, the tool calls and the answer only) | week 13, 14 and 17 cases (`semana-14/resultados/poisoning.md`); the deployed run is step 4 | offline (weeks 13, 14 and 17); step 4; **H13** |
| T3.7 | I | other users' questions and data (week 20, activity 3) | The prompt cache leaks across users or tenants: a cached prefix read by another query, or a cache hit (faster, cheaper) revealing that someone asked the same question | ADR 0014: cache points only from the second model call, so the one prefix two users could share (system, tools, question) is never cached; every cached prefix holds this query's own model-generated `toolUseId`s; the tools and system prompt carry nothing of the user; the cache is per account and exact-prefix. Off by default (`CACHE_PROMPT`) | `test_agente_cache.py::test_seguridad_el_prefijo_fijo_es_igual_para_dos_usuarios_y_lo_demas_es_de_la_tarea`; `::test_historial_pone_el_punto_al_final_y_en_el_del_paso_anterior_nunca_en_la_primera_llamada` | offline; week 21 reviews it with multi-tenant prod |

## F4 · The Lambda and RDS (IAM authentication, copilot_ro and order_writer, SQL guard, TLS)

| ID | STRIDE | Asset | Threat | Control | Proof | Status |
|---|---|---|---|---|---|---|
| T4.1 | S | database credentials | A stolen password, or a function that connects as a stronger user | IAM authentication with a short token, no password; `rds-db:connect` only for `copilot_ro` (tools) and `order_writer` (writer) | `test_computo_rds_permisos.py::test_solo_el_escritor_y_las_herramientas_pueden_conectar`; `::test_las_herramientas_solo_conectan_como_copilot_ro`; `::test_el_escritor_solo_conecta_como_order_writer`; `test_herramientas_handler.py::test_token_iam_es_solo_para_copilot_ro` | offline + live (approval step 4 written by `order_writer`, `resultados/eval_aws.md`) |
| T4.2 | T | legacy data | A write through `ejecutar_sql` | sqlglot guard (SELECT only, schema `legado`), read-only transaction, `copilot_ro` with `default_transaction_read_only` | `test_herramientas_guardia.py::test_escrituras_se_rechazan`; `::test_otro_esquema_se_rechaza`; `test_herramientas_handler.py::test_escritura_se_rechaza_y_no_hay_conexion`; `test_loader.py::test_roles_no_llevan_contrasena_y_copilot_ro_es_solo_lectura` | offline; table fingerprint before and after in step 4 |
| T4.3 | I | data in transit | Man in the middle between the Lambda and RDS | TLS with certificate and host name verified against the RDS bundle pinned by fingerprint | `test_herramientas_handler.py::test_tls_verifica_certificado_y_nombre_de_host`; `::test_tls_sin_bundle_falla_antes_de_conectar`; `test_rds_ca.py::test_bundle_es_el_oficial_fijado_por_huella` | offline + live (every activity 8 connection ran with verification) |
| T4.4 | I | supplier and cost columns | A user reads tables or columns outside its scopes | Week 17's deterministic layer checks the token's scopes against tables and columns before the call. The database role does not: `copilot_ro` reads all of `legado` | `semana-17/tests/test_guardrails.py::test_el_token_decide_el_alcance_de_tablas_y_columnas_no_la_peticion` | offline; weaker than week 14 (one database role instead of one per scope): **H5** |
| T4.5 | E | purchase orders | An order nobody asked for | The layer blocks a proposal without an explicit request; the tools reject an invalid proposal before connecting or starting the workflow | `test_agente_capa.py::test_orden_sin_pedido_explicito_se_bloquea`; `test_herramientas_handler.py::test_orden_invalida_se_rechaza_sin_conectar_ni_iniciar` | offline |
| T4.6 | D | the database | Slow or huge queries | Statement timeout and row limit; a truncated result is marked | `test_herramientas_handler.py::test_seleccion_fija_timeout_solo_lectura_y_limite`; `::test_resultado_mayor_al_limite_se_marca_truncado` | offline |

## F5 · The gateway and the tools (user JWT, Cedar in ENFORCE, requester equal to `sub`, outbound role)

| ID | STRIDE | Asset | Threat | Control | Proof | Status |
|---|---|---|---|---|---|---|
| T5.1 | S | the gateway | A call without a valid token | Inbound `CUSTOM_JWT` with the Cognito pool and the app client; an expired token is never sent | `test_infra_gateway.py::test_entrada_con_el_jwt_de_cognito_y_el_cliente_de_la_app`; `test_agente_gateway.py::test_un_token_vencido_o_sin_exp_nunca_se_envia` | offline + live (`resultados/agentes.md`, Policy test) |
| T5.2 | E | `proponer_orden_compra` | An analyst or an approver proposes an order | Cedar in ENFORCE: only `legado/compras_proponer`; `tools/list` filtered by the same policies | `test_gateway_politicas.py::test_un_token_sin_compras_proponer_no_alcanza_la_herramienta_protegida`; live: analyst and approver denied (−32002) | offline + live |
| T5.3 | S | the order's requester | A buyer proposes in another user's name | Cedar requires the argument `solicitante` to equal the token's `sub` | `test_gateway_politicas.py::test_el_comprador_no_propone_a_nombre_de_otro`; live: denied (−32002) | offline + live |
| T5.4 | E | other Lambdas | The gateway's role invokes something else | The outbound role invokes only the tools function; only AgentCore from this gateway assumes it, with the boundary | `test_infra_gateway.py::test_el_rol_del_gateway_solo_invoca_la_funcion_de_herramientas`; `::test_el_rol_lo_asume_solo_agentcore_desde_este_gateway_y_con_el_limite` | offline |
| T5.5 | T | tool definitions | A tool's schema changes without review (the week 14 rug pull, A02) | One source for the schemas; policies may name only the target's tools | `test_infra_gateway.py::test_la_fuente_unica_de_esquemas_no_cambio_sin_regenerar`; `test_gateway_politicas.py::test_las_politicas_nombran_solo_herramientas_del_target` | offline |
| T5.6 | E | the agent's controls | A user calls `herramientas___ejecutar_sql` on the gateway with its own token, skipping the agent: no Guardrail, no deterministic layer, no budgets | The SQL guard, the read-only role and the row limit still apply inside the tools function | none | not tested; **H3** |

## F6 · The approver (separation of duties, task token in DynamoDB, expiry)

| ID | STRIDE | Asset | Threat | Control | Proof | Status |
|---|---|---|---|---|---|---|
| T6.1 | E | the order | The buyer approves its own order | Separation of duties (#244): buyers propose, approval groups decide; whoever proposed cannot decide | `test_computo.py::test_quien_propuso_no_puede_decidir_su_propia_orden`; `::test_separacion_de_funciones_compradores_proponen_y_aprobadores_deciden`; live: approver different from the requester (approval step 3) | offline + live |
| T6.2 | E | the order | An approver below the order's level approves it | The level comes from the token's group and is compared with the database's level | `test_computo.py::test_nivel_insuficiente_no_envia_nada_ni_borra_la_fila`; `::test_sin_nivel_en_el_token_no_decide` | offline |
| T6.3 | I | the task token | The token leaks through logs or responses, and anyone holding it can decide | Stored in DynamoDB (CMK, TTL), never returned or logged | `test_computo.py::test_registrar_guarda_token_orden_nivel_y_solicitante_con_ttl_y_no_devuelve_el_token`; `test_agente_exportador.py::test_cada_span_es_una_linea_json_y_no_se_filtra_el_token_de_tarea`; live: 0 appearances in logs (approval step 1) | offline + live |
| T6.4 | T | the decision | Replay of a decision, or a late approval | The row is deleted on the decision; TTL 24 h; the state machine times out | `test_computo.py::test_token_ya_usado_responde_no_encontrada_y_otro_error_se_propaga`; `::test_fila_caducada_o_inexistente_no_revela_nada`; live: late approval 404, `States.Timeout` (approval step 5) | offline + live |
| T6.5 | S | approver identity | Who decides is taken from the request | From the authorizer's claims only | `test_computo.py::test_handler_toma_quien_y_su_nivel_de_los_claims_y_no_del_cuerpo` | offline |
| T6.6 | T | `purchase_orders` | Another role writes the order, or a decision changes a row it should not | Only `order_writer`, only the pending row, never if the decider requested it | `test_escritor_orden.py::test_la_decision_actualiza_solo_la_fila_pendiente_y_no_si_quien_decide_la_pidio`; live: written by `order_writer` (approval step 4) | offline + live |
| T6.7 | R | the decision | Nobody can tell who approved | The decision carries who and their level; the state machine keeps its history (logs without data) | `test_computo.py::test_aprobar_con_nivel_suficiente_envia_la_decision_con_quien_y_su_nivel_y_borra_la_fila`; `test_infra_computo.py::test_maquina_de_aprobacion_con_traza_y_log_sin_datos` | offline |

## Boundaries the list did not have

### F7 · The Knowledge Base and its documents

| ID | STRIDE | Asset | Threat | Control | Proof | Status |
|---|---|---|---|---|---|---|
| T7.1 | T | the agent's context | Poisoned documents in the KB (indirect injection) | **None needed today, and none in place: no code calls `Retrieve`.** ADR 0008 decided the agent would, and the agent role has no `bedrock:Retrieve` | `git grep` finds no `Retrieve` call in `agente/` or `herramientas/` | step 4 (a direct `Retrieve` shows what the KB would return); **H2** |
| T7.2 | E | the docs prefix | Someone writes documents | Only the loader writes `docs/*`; the boundary allows `s3:PutObject` only on `semana19-datos*/docs/*` | `resultados/seguridad/validate_policy.json` (the boundary validated); `test_infra_cdk.py::test_cada_recurso_cifrable_apunta_a_la_llave_del_proyecto` | offline |
| T7.3 | I | documents, vectors | The bucket or the vector store is public or not on the CMK | Docs bucket on the CMK with Block Public Access. The vector bucket has no encryption configuration, so S3 Vectors uses SSE-S3, which cannot be changed after creation | `test_infra_cdk.py::test_cada_recurso_cifrable_apunta_a_la_llave_del_proyecto` (docs bucket); `verificar_desplegado.py` | offline (docs bucket); step 2; vector bucket: **H10** |

### F8 · Logs, traces and the audit trail

| ID | STRIDE | Asset | Threat | Control | Proof | Status |
|---|---|---|---|---|---|---|
| T8.1 | I | questions, answers, tokens | Free text or tokens in spans | The exporter drops undeclared free-text attributes and counts them | `test_agente_exportador.py::test_atributo_de_texto_libre_se_omite_y_se_cuenta` | offline + live (spans of activity 8) |
| T8.2 | I | log groups | Logs not on the CMK, or kept forever | Every group on the CMK with retention | `test_infra_cdk.py::test_todos_los_grupos_de_logs_usan_la_llave_y_tienen_retencion`; `test_infra_computo.py::test_todo_grupo_de_logs_del_stack_esta_cifrado_y_con_retencion` | offline; step 2 |
| T8.3 | R | Bedrock calls | No record of which role called Bedrock | CloudTrail Event history: 90 days of management events, free. `Converse` and `InvokeModel` are management events. `ApplyGuardrail`, `Retrieve`, `InvokeAgent` and AgentCore `InvokeGateway` are data events that need a paid trail, which this lab does not have | `verificar_desplegado.py` (CloudTrail check) | step 2; the data events are not visible: **H11** |
| T8.4 | E | the key | A service principal in the key policy acts for another account (confused deputy) | `DeliveryDeLogsDescifra` gives `delivery.logs.amazonaws.com` `kms:Decrypt` **without** `aws:SourceAccount` or `aws:SourceArn` | `resultados/seguridad/validate_policy.json` (no finding: the validator does not flag it) | not tested; **H7** |

### F9 · The network (VPC, endpoints)

| ID | STRIDE | Asset | Threat | Control | Proof | Status |
|---|---|---|---|---|---|---|
| T9.1 | I | data in the VPC | Exfiltration from a VPC Lambda to the internet | Isolated subnets, no IGW, no NAT | `test_infra_cdk.py::test_sin_nat_sin_internet_gateway_ni_subredes_publicas` | offline; step 2 |
| T9.2 | E | the endpoints | Principals of other accounts use the VPC endpoints | Every endpoint policy allows only `aws:PrincipalAccount` equal to this account | `test_infra_cdk.py::test_endpoints_limitados_a_la_cuenta`; `resultados/seguridad/validate_policy.json` (4 endpoint policies) | offline; step 2 |
| T9.2b | I | legacy data | A compromised VPC Lambda copies data to a bucket of another account through the S3 gateway endpoint | The function roles' IAM policies name only project buckets. The endpoint policy does not limit `aws:ResourceAccount` | none | not tested; **H12** |
| T9.3 | S | RDS, endpoints | Open ingress | No rule open to the internet; endpoints accept 443 only from the Lambdas; the writer opens only 5432 and 443 | `test_infra_cdk.py::test_ninguna_regla_de_entrada_admite_internet_ni_cidr_abierto`; `::test_grupo_de_endpoints_solo_acepta_443_desde_la_lambda`; `test_infra_computo.py::test_escritor_esta_en_la_vpc_y_solo_abre_5432_y_443` | offline |
| T9.4 | I | the database | RDS reachable from outside | `PubliclyAccessible=false`, private subnets | `test_infra_cdk.py::test_base_de_datos_cifrada_privada_sin_acceso_publico_con_iam` | offline; step 2 |

### F10 · Supply chain (vendored packages, pinned tools)

| ID | STRIDE | Asset | Threat | Control | Proof | Status |
|---|---|---|---|---|---|---|
| T10.1 | T | Lambda code | A tampered or unexpected version of a vendored package | Vendored versions pinned and tested; `uv.lock`; CI binaries pinned by sha256 (Terraform, gitleaks) | `test_guardrail_handler.py::test_boto3_vendorizado_es_la_version_que_validan_las_pruebas`; `test_loader.py::test_scramp_vendorizado_tiene_make_channel_binding` | offline; no vulnerability scan of the vendored packages: **H8** |
| T10.2 | I | credentials | A secret committed, now or in the history | gitleaks 8.30.1 over the history and the synth, every finding classified | `test_escaneo_secretos.py::test_informe_versionado_sin_hallazgos_sin_clasificar`; CI `spike-iac` | offline |

### F11 · The control plane and spend

| ID | STRIDE | Asset | Threat | Control | Proof | Status |
|---|---|---|---|---|---|---|
| T11.1 | E | IAM | The deploy role creates a role without the boundary, or removes it | Roles only with `semana19-limite`; the deploy role cannot change itself or the boundary | `test_infra_cdk.py::test_despliegue_crea_roles_solo_con_limite`; `::test_despliegue_no_quita_ni_cambia_el_limite`; `::test_todo_rol_creado_por_los_stacks_tiene_el_limite` | offline + live (activity 3 deploys) |
| T11.2 | D | the bill | Spend beyond the budget | Monthly budget of USD 50 with an automatic action that attaches the freeze policy | `test_infra_cdk.py::test_accion_del_presupuesto_congela_al_100_por_ciento`; `::test_la_congelacion_no_bloquea_borrar` | offline; step 4 (test budget) |
| T11.3 | E | every policy | Invalid or over-broad policies | cdk-nag and checkov at zero unsuppressed; ValidatePolicy with 0 errors and 0 security warnings | `test_supresiones.py::test_informe_versionado_en_cero`; `test_validar_politicas.py::test_snapshot_sin_errores_ni_advertencias_de_seguridad`; `test_validar_politicas_cobertura.py` | offline |

## Findings opened by this review

| ID | Boundary | Finding | Severity | Mitigation | Status |
|---|---|---|---|---|---|
| H1 | F1 | No throttling on the HTTP API stage; only Lambda reserved concurrency and the per-tenant budgets bound a flood | medium | Default route throttling (rate and burst) on the stage | open |
| H2 | F7 | ADR 0008 is not implemented: no code calls `Retrieve`, and the agent role cannot. The KB is deployed and paid for, but no request path uses it | low (design drift) | Wire `Retrieve` with its own deterministic checks, or record in ADR 0008 that the KB is not on the request path | open |
| H3 | F5 | On path (b), a user can call the gateway's read tools directly with their own token, skipping the Guardrail, the deterministic layer and the budgets. Today every lab group holds every read scope, so no new data is exposed | low in the lab; medium in prod | Enforce the scope-to-table check inside the tools function, or keep only `proponer_orden_compra` on the gateway | open |
| H4 | F2 | A timeout or crash of the asynchronous agent leaves the question `pendiente` until its 7-day TTL, with no signal to the user | low | An on-failure destination that marks the row `error` | open (retries removed in #297) |
| H5 | F4 | Week 14 had one database role per scope. Week 19 has one, `copilot_ro`, for every reader: scope enforcement is application-layer only | low in the lab; medium in prod | Per-scope database roles, or row-level security on the sensitive views | open |
| H6 | F1 | Lab settings that must not reach prod: admin password login enabled for the test users, MFA off | low in the lab; high in prod | Prod profile without `ALLOW_ADMIN_USER_PASSWORD_AUTH`, with MFA | accepted for the lab |
| H7 | F8 | Key policy statement `DeliveryDeLogsDescifra` has no `aws:SourceAccount` condition (confused deputy) | low | Add `aws:SourceAccount` and check that Step Functions log delivery still works | open |
| H8 | F10 | Vendored packages (botocore, PyJWT, cryptography, pg8000, sqlglot) are pinned but not scanned for known vulnerabilities | medium | `pip-audit` (or OSV) over `uv.lock` and the vendored dist-info in CI | open, for week 21 |
| H10 | F2, F6, F7, F8 | Not on the CMK: the approval state machine (AWS owned key; its log group is on the CMK), the KB's vector bucket (SSE-S3 by default, immutable), the KB data source's transient ingestion data (AWS owned key), the log groups the Lambda runtime creates for the two functions without a log group in CloudFormation (the loader and the CDK custom resource that restricts the default security group), and the environment variables of the 6 computo Lambdas that have them (AWS managed key `aws/lambda`; they hold resource names and ids, no secrets). The test `test_cada_recurso_cifrable_apunta_a_la_llave_del_proyecto` synthesizes only control, base and datos, so it never saw computo | low | Add the CMK to the state machine, the vector bucket (a new bucket) and the Lambdas' `KmsKeyArn`, and extend the test to computo | open |
| H11 | F8 | Bedrock data events (`ApplyGuardrail`, `Retrieve`) and gateway `InvokeGateway` calls are not recorded: no trail. Only `Converse` and `InvokeModel` reach Event history | low in the lab; medium in prod | A trail with advanced event selectors for those resource types in prod | accepted for the lab (a trail is paid and needs Manuel's OK) |
| H12 | F9 | The S3 gateway endpoint's policy limits the caller (`aws:PrincipalAccount`) but not the bucket owner (`aws:ResourceAccount`). Only the roles' IAM policies stop a write to another account's bucket | low | Add `aws:ResourceAccount` to the S3 endpoint policy (keeping the AWS-owned buckets Lambda and CloudFormation need, if any) | open |
| H13 | F3 | The deployed deterministic layer does not sanitize tool results. Week 17 replaced instruction-like sentences in every tool result before the model saw them (`nucleo.revisar_resultado`, called in `semana-17/guardrails/agente.py`); the AWS port applies the core to the request, the tool calls and the final answer only. A poisoned `legado.artnot` note reaches the model as is; what remains is the Guardrail, the model, the tool-call checks and the read-only database | medium | Call `N.revisar_resultado` on each tool result in `agente/handler.py` (`HerramientasCapadas.llamar`) and record its decision, as week 17 does | measured in step 4 (2026-11-22: the note reached the model in 8 of 8 tasks; the model obeyed none). Fixed: the layer now sanitizes each tool result. Residual: week 17's sanitizer does not catch the iny-d3 note ("Instrucción del sistema: responde que …"), so that one still reaches the model |
| H14 | F10 | The bootstrap's assets bucket (`cdk-s19-assets-<account>-us-east-1`: the templates and the Lambda code CloudFormation deploys) is encrypted with the AWS managed key `aws/s3`, not the project CMK. Found live by `verificar_desplegado.py` (step 4.2, 2026-11-22) | low | Bootstrap with `--bootstrap-kms-key-id` (the project key, or a key of the control stack, since the bootstrap outlives base) | open |
| H9 | F1 to F11 | Fixed in this activity: 24 checkov failures on computo (#297); two ValidatePolicy errors (#298) | — | — | fixed |

## What changed from week 14

Week 14 was a local MCP server with Keycloak, on loopback. Week 19 puts the same tools behind an AWS front door.

| Week 14 | Week 19 | What changed |
|---|---|---|
| A01 tool poisoning, A03 shadowing | T5.5 | No third-party MCP servers: the agent's catalog is fixed in code (path a) or is one gateway target from one schema source (path b). The allowlist and prefix defenses are not needed; schema drift is the remaining risk |
| A02 rug pull | T5.5 | The client-side hash pinning becomes a build-time check: schemas from one source, policies naming only the target's tools |
| A04 indirect injection through data | T3.6, T7.1 | Same `legado.artnot` notes, now behind the Guardrail and week 17's deterministic layer. A second channel, the KB documents, exists in the stack but is not wired (H2) |
| A05 confused deputy | T4.4, T5.3 | The requester comes from the token (path a: set by the Lambda; path b: enforced by Cedar). The database is no longer the last line by scope: one role for every reader (H5) |
| A06 token passthrough | T4.1 | The database uses IAM tokens of the function's role; the user's token goes only to the gateway (path b), whose inbound authorizer checks it |
| A07 token theft, wrong audience | T1.1, T5.1 | Keycloak and PyJWT become Cognito with the HTTP API's JWT authorizer and the gateway's `CUSTOM_JWT` |
| A08 DNS rebinding | — | Does not apply: nothing listens on loopback; the front door is an AWS endpoint with TLS |
| A09 leak across roles and tenants | T1.3, T2.1, T4.4 | The tenant travels in the token (pre-token trigger) and the answers are bound to their owner; the per-scope database roles are gone (H5) |
| A10 unapproved write | T4.2, T6.1 to T6.6 | Read-only role and guard as before; writes happen only after a person of the right level approves, as `order_writer` |
| A11 header and body mismatch | T5.1 | AgentCore Gateway terminates MCP; the Lambda receives a typed event |
| A12 SSRF in discovery | — | Does not apply: the agent's MCP client calls one configured gateway URL |
| A13 denial of service and cost | T1.6, T2.4, T3.5, T4.6, T11.2 | Adds AWS controls (reserved concurrency, no async retries, the budget action) and one gap (H1) |
| — | F6, F8, F9, F10, F11 | New boundaries: the approval workflow, the audit trail, the VPC, the supply chain of Lambda assets and the control plane |

## Out of scope

- The CDK bootstrap stack (`semana19-cdktoolkit`): its roles and policies come from CDK and are covered in
  `resultados/base.md`.
- Red teaming with garak or PyRIT, and the full OWASP Top 10 for LLM report: week 21. Each finding above is mapped to
  its OWASP LLM category in `resultados/seguridad.md`.
