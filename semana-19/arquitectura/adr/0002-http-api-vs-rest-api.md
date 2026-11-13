# ADR 0002: HTTP API or REST API for the front door

## Context

The client calls the LegacyBridge agent through API Gateway. The entry authenticates analysts and approvers with a Cognito JWT authorizer (groups `analista` and `aprobador`). The lab is a demo; production needs more controls. The question is which API type to use in each profile.

## Alternatives

- **HTTP API.** Lower price per request, native JWT authorizer, fewer knobs. No usage plans, no request validation at the gateway, no AWS WAF attachment.
- **REST API.** Usage plans and API keys, request validation with models, AWS WAF attachment, response caching, and more mature access logs. It costs more per request and has more configuration.

## Decision

- **Lab: HTTP API.** It covers the authorizer and the demo's routes, and its price is measured.
- **Prod: REST API** with AWS WAF, usage plans, and request validation, as the plan requires. The lab does not deploy it: prod is only synthesized and costed.

## Consequences

- The lab and prod stacks differ in the API resource. The configuration file that drives the difference (`perfil`) must list it.
- Migrating lab to prod changes the authorizer code path: the REST authorizer takes the Cognito user pool directly.

## Costs (from `semana-19/costos/precios.json` and `modelo.py`)

- HTTP API, per request: **0.0000009 USD** (M, `USE1-ApiGatewayHttpRequest`, 2026-11-12). At 100 queries a day that is 0.0000009 × 3,000 = 0.0027 USD per month.
- REST API, per request: **N**. Not measured in this activity; no figure is used.
- AWS WAF in prod: **N**. Not measured.
