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
