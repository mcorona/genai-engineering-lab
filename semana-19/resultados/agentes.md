# Week 19, activity 7: three tools paths compared (direct loop, AgentCore Gateway with Policy, Bedrock Agents)

Measured 2026-11-18 in us-east-1 with `agentes/comparar.py`. Raw, redacted files are in `resultados/agentes/`.
Every figure below comes from those files. The AWS charges for the gateway and Policy arrive with Cost Explorer the
next day, and the cost line will be added then.

## The three paths

| Path | How the agent reaches the tools | Who decides the requester | Stack |
|---|---|---|---|
| (a) directo | the week 13 loop in the agent Lambda calls `lambda.invoke` on the tools function | the verified token's `sub`, set by the agent Lambda | `semana19-computo` with `CAMINO_HERRAMIENTAS=directo` |
| (b) gateway | the same loop, as an MCP client of the AgentCore Gateway with the user's token; Cedar policies in ENFORCE | the argument `solicitante`, which Cedar allows only when it equals the token's `sub` | `semana19-computo` with `CAMINO_HERRAMIENTAS=gateway`, `semana19-gateway` |
| (c) agentes | a Bedrock Agent orchestrates; its action group's executor is the same tools function (its Bedrock Agents adapter) | the session attribute `solicitante`, set by whoever calls InvokeAgent | `semana19-agentes-comparacion` (disposable) |

The tools exist once, in `herramientas/handler.py`, and each path has one input adapter in
`herramientas/adaptadores.py`.

## Path (c) could not be created: Bedrock Agents refuses new agents in this account

The stack `semana19-agentes-comparacion` was deployed twice.

1. The first attempt stopped on a permission of ours, `iam:GetRolePolicy` (fixed in #257).
2. The second reached `bedrock:CreateAgent`, and the service refused it. CloudTrail (read-only lookup) shows event
   `CreateAgent`, error `AccessDenied`, the CloudFormation execution role as caller, and this response message:

> Bedrock Agents is in Maintenance Mode. New agent creation is not available for accounts without prior service
> usage.

This account has never used Bedrock Agents, so no IAM change can make path (c) available. Both attempts rolled back
cleanly, and the empty stack was deleted with `cdk destroy`. The IaC (#253) and its offline tests remain the
specification of path (c). Nothing was measured for it; the (c) column below comes from the design.

## Measured comparison

The same 10 Spanish gold tasks ran on each path: s01-es to s10-es, the first ten with one output key and expected
state `respondida`. Each task was sent as week 13 frames it (`mensaje_tarea`), as user `analista`, one at a time.
Success is judged by week 13's verifier, which re-executes the reported SQL as `copilot_ro` through the tools
function.

| Metric | (a) directo | (b) gateway | (c) agentes |
|---|---|---|---|
| Success (verifier) | **10/10** | **9/10** | not measured |
| Latency p50 / p95 (s) | 18.51 / 40.75 | 15.76 / 41.16 | — |
| Latency per step (s) | 4.49 | 4.58 | — |
| Tokens (input + output) | 171,459 | 172,139 | — |
| Model cost (USD, from the spans) | 0.2405 | 0.2410 | — |
| Steps / tool calls per task (mean) | 4.6 / 3.6 | 4.5 / 3.7 | — |
| Tool errors | 0 | 0 | — |
| Deterministic-layer, guardrail and Policy blocks | 0 / 0 / 0 | 0 / 0 / 0 | — |
| Spans complete, with the path's `gen_ai.tool.type` | 10/10, `function` | 10/10, `extension` | — |

Reading:

- **Latency.** With 10 tasks, the gateway's hop cannot be separated from the model's variance. The median
  per-task difference (b − a) is −0.02 s, ranging from −4.4 s to +3.44 s, and (b) was faster on 5 of 10 tasks.
  No overhead is claimed in either direction.
- **The one miss on (b), s07-es,** is the model's, not the gateway's. Asked for the supplier lead time of "the most
  expensive product", it ordered by `art_ptr` instead of `art_cst` and answered 40 days. The expected answer is 28.
  On (a), the same task used `art_cst` and was exact. The tools ran without errors on both paths.
- **Cost.** Tokens and model cost are within 0.5% between the paths, as expected: the loop, the model and the tools
  are the same.

### Spend of the activity

| Run | Tokens | USD (model) | Note |
|---|---|---|---|
| (a), first run | 110,295 | 0.1614 | discarded, kept as `crudo_directo_descartada_1.json` |
| (a) | 171,459 | 0.2405 | |
| (b) | 172,139 | 0.2410 | |
| **Total** | **453,893** | **0.6430** | the script's cap was 1.20 USD and 500,000 tokens |

The first run of (a) scored 0/10 because of the harness, not the agent (#261).

- It sent the bare question, without week 13's output keys, so the agent named its own keys and the verifier found
  none.
- 2 of its 10 agent spans were read before CloudWatch indexed them.

Its spend stays in the cap and in the record.

## Live Policy test

`proponer_orden_compra` was called through the gateway with each user's own token. The test proposal names cedis
99999, so the tool refuses it before any workflow starts.

| User | Requester in the call | Expected | Got | Evidence |
|---|---|---|---|---|
| analista | own `sub` | denied | denied | JSON-RPC error −32002 from the gateway |
| comprador | own `sub` | allowed | allowed | reached the tool, which answered `cedis_desconocido` |
| aprobador | own `sub` | denied | denied | −32002 (separation of duties: the approver cannot propose) |
| comprador | another user's `sub` | denied | denied | −32002 (Cedar requires `solicitante` == the token's `sub`) |

`tools/list` is filtered by the same policies:

| User | Tools listed |
|---|---|
| analista | `herramientas___describir_esquema`, `herramientas___ejecutar_sql` |
| comprador | the same two, plus `herramientas___proponer_orden_compra` |
| aprobador | `herramientas___describir_esquema`, `herramientas___ejecutar_sql` |

All 7 checks passed. The first attempt stopped on its first case: the deny arrived nested two exception groups deep
in the MCP client and surfaced as a crash. #265 fixed that before the run above.

## What survives on each path

The (a) and (b) columns were checked against the run. The (c) column comes from the design.

| Control (week) | (a) directo | (b) gateway | (c) agentes | Why |
|---|---|---|---|---|
| Budgets per task, session and tenant-day (17) | yes | yes | **no** | they wrap the loop's model calls (`agente/presupuesto.py`), and Bedrock Agents makes its own model calls; `comparar.py` only ends the stream on the client side |
| Deterministic layer: input, tool arguments, final answer (17, 19) | yes | yes | **no** | it runs in the agent Lambda around the loop (`agente/capa_determinista.py`) |
| Read-only SQL guard (16) | yes | yes | yes | it runs inside the tools function, before any connection |
| Proposal validation and database checks (19, activity 6) | yes | yes | yes | they run inside the tools function |
| Bedrock Guardrail, fixed version (19, activity 5) | yes, on each Converse call | yes | yes, on the agent | a property of the call (a, b) or of the agent (c) |
| Cedar Policy on the tools (19, activity 7) | no | **yes**, measured above | no | only the gateway evaluates it |
| Requester bound to the token | yes, set by the Lambda | yes, enforced by Cedar | **no**, the caller sets it | Bedrock Agents receives no user token |
| Tool list per user | no, the loop sees all tools | **yes** | no | the gateway filters `tools/list` with the policies |
| Spans in week 17's schema (`execute_tool`, `invoke_agent`) | yes, 10/10 | yes, 10/10 | **no** | (c) has its own trace, which is not exported to the spans group |
| Trajectory evaluation (13, 17) | yes, from the spans | yes | partial | the trace shows steps and tool calls, in another shape |

## What the trace of (c) does not show

No agent could be created, so there is no trace to quote. From the API's trace format (design, not measured), the
trace would not carry:

- week 17's run id, budgets and outcome reason;
- the deterministic layer's decisions, which do not run on (c);
- the user behind the session: the requester is whatever the caller put in `sessionAttributes`.

The intended redacted example cannot be produced in this account.

## What the gateway took to deploy

The gateway needed five permission fixes, found one deploy at a time.

| Failure | Fix |
|---|---|
| CloudFormation could not read or write the roles' inline policies: Get/Put/DeleteRolePolicy carry no boundary key | name-scoped `RolesDeActividad7PorCfn` (#257) |
| `CreateGateway` checks that the role can already call `AuthorizeAction` on the engine | engine permissions in the role's default policy (#258) |
| …and on the new gateway's own ARN, which ends in a random suffix | two-phase creation, `S19_GATEWAY_FASE=1`, with no wildcard (#259) |
| AgentCore encrypts the target's configuration by calling KMS as the role, without `kms:ViaService` | exact-key statement; boundary `KmsDelGatewayDelLimite` (#260) |
| CloudFormation needs `CreateWorkloadIdentity` on `workload-identity-directory/default` | `IdentidadDelGatewayPorCfn` (#263) |

Once the permissions were in place, phase 1 took 103 s, phase 2 (the engine in ENFORCE) 43 s, and switching computo
to the gateway 88 s. The gateway was destroyed the same day (`destruir.sh --si --solo-actividad7`). The inventory of
the three activity 7 categories (gateways, policy engines, Bedrock agents) reads 0, with the read-only profile
(`resultados/agentes/inventario_actividad7.json`).

## Decision

**Path (b) is the target for production, and path (a) stays the lab default.** Path (c) is discarded. The (b) choice
is pending one check: the gateway's and Policy's AWS charges from Cost Explorer.

- **(b) adds authorization the loop cannot give itself.** Per-user tool lists, separation of duties and a requester
  bound to the token are enforced outside the agent, in Cedar. That is the property a write tool such as
  `proponer_orden_compra` needs.
- **(b) showed no measurable penalty** on 10 tasks: the same tokens and model cost, latency within noise, and every
  control of (a) still running.
- **(a) remains the lab default**, behind the `CAMINO_HERRAMIENTAS` flag. It needs no extra stack, and with one user
  and read-only tools the gateway adds no protection the Lambda's verified `sub` does not already give.
- **(c) is out.** New agents are unavailable in this account. Even if they were available, the design loses week
  17's budgets, the deterministic layer, the spans and the token-bound requester.
- **To revisit:** if Cost Explorer shows the gateway's and Policy's charges are material at the expected volume, or if
  the two-phase creation proves fragile in another account.
