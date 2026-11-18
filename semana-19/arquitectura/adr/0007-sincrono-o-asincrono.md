# ADR 0007: asynchronous queries (202 and polling), not a synchronous call

## Context

The HTTP API integration timeout is 30 seconds. The official quota page marks it as not adjustable; a support note on
the same page says otherwise, and that exception is not documented. Week 13 latency for Haiku 4.5 at `low`: p50 7.1 s,
p95 14.8 s. At `medium`: p95 21.0 s. The maximum is not in the table.

## Alternatives

- **Synchronous.** `POST /consultas` waits for the loop. Fits at `low` with margin; at `medium` the p95 leaves about 9 s.
- **Asynchronous.** `POST /consultas` returns 202 with an id; the agent Lambda runs asynchronously; `GET /consultas/{id}`
  reads the result from DynamoDB.

## Decision

**Asynchronous.** The agent Lambda's timeout is below the 30 s integration limit of anything that invokes it, and the
week 17 wall-clock budget is below that timeout. The API never waits on the loop.

## Consequences

- A result store is needed (DynamoDB on-demand, KMS, TTL) with a gateway endpoint if anything in the VPC touches it.
- The client polls; the answer carries its status (`pendiente`, `respondida`, `requiere_aclaracion`, `abstenida`,
  `presupuesto_agotado`).
- Costs: DynamoDB on-demand is not priced in `precios.json`; it is **not quoted** yet.

### Activity 7: the token on the asynchronous path

With `CAMINO_HERRAMIENTAS=gateway` the agent Lambda calls the tools through the AgentCore Gateway as an MCP client,
and the gateway authorizes each call with the USER's token (CUSTOM_JWT inbound, Cedar policies on its claims). The
asynchronous design means the token must travel with the work:

1. `POST /consultas`: the HTTP API's JWT authorizer verifies the access token (issuer, client, scope).
2. The questions function (`consultas/api.py`) puts the token, unchanged, in the asynchronous event of the agent
   Lambda (`InvocationType=Event`) next to the claims. It is **not** written to the results table: the item keeps
   the owner's keyed hash, the state and the expiry only (test: `test_crear_guarda_por_hash_del_sujeto_y_arranca_el_agente`).
3. The worker (`consultas/worker.py`) passes it to the agent (`agente/handler.py`), which opens one MCP session per
   question with `Authorization: Bearer <token>` (`agente/cliente_gateway.py`).
4. The gateway verifies the token again (the pool's discovery URL, the app client, `legado/leer`) and evaluates the
   Cedar policies with its claims as tags (`gateway/politicas/*.cedar`). The tools Lambda never receives the token:
   the gateway calls it with its own role (GATEWAY_IAM_ROLE). The requester of a proposal reaches it as the
   argument `solicitante`, which Cedar allows only when it equals the token's `sub`.

The token is never logged (the worker logs the exception type and trace positions only), never stored and never
returned. While the asynchronous invocation waits in Lambda's internal queue the token is in AWS-managed storage;
the access token's validity (Cognito's default is 60 minutes) bounds that exposure.

**Expiry in the middle of the loop fails closed.** Before each tool call the client reads the token's `exp`
(without verifying: the gateway does that) and does not send a token that expires within 5 seconds; a 401 from the
gateway counts the same. Either way the loop stops at that call and the question ends with week 17's state `error`
and the text "Tu sesión venció…": no retry, no further model turn, the `execute_tool` span records
`error.type=token_vencido` and the `invoke_agent` span is exported as usual (test:
`test_un_token_que_vence_a_mitad_del_bucle_cierra_con_error_y_no_sigue`). With the week 17 wall-clock budget under
30 seconds this only happens to a request that arrived with a token about to expire.

The direct path (`CAMINO_HERRAMIENTAS=directo`, the default) does not use the token: the agent invokes the tools
Lambda with its own role, as in activity 6.

## Costs

- DynamoDB on-demand for the results: **N**, not priced in `precios.json`.
- HTTP API requests: 9e-07 USD each (`apigw_http_solicitud`, **M**); the polling traffic is counted with the queries.
