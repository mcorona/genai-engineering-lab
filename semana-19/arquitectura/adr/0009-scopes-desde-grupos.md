# ADR 0009: scopes from groups through a pre-token generation trigger (V2) on Essentials

## Context

The JWT authorizer of an HTTP API validates scopes; Cognito groups do not become scopes by themselves. A test that a
token without the scope gets 403 needs the check at the authorizer.

## Alternatives

- **(a)** Resource server with scopes `legacybridge/consultas` and `legacybridge/aprobaciones`, plus a pre-token
  generation trigger on event version 2 that adds the scopes from the group. The trigger needs the **Essentials** or
  **Plus** feature plan (confirmed in the Cognito documentation).
- **(b)** Authorizer validates only the audience; the handler checks `cognito:groups`. No trigger, no tier change.

## Decision

**(a).** The 403 is then enforced at the gateway, not in code.

## Consequences

- Cost of Essentials: **0.015 USD per MAU** (`semana-19/costos/precios.json`, Price List). With the two test users the
  upper bound is **0.03 USD per month**. Whether the free tier covers them is **not verified**.
- **Cost authorized by Manuel** (upper bound 0.03 USD per month). Before the deployment (PR 4) the free-tier
  coverage is still to be verified.

## Costs

- Cognito Essentials: 0.015 USD per MAU (`cognito_mau`, **M**). Two test users: **0.03 USD per month upper bound (M)**.
- Free-tier coverage of the two users: **N**, not verified.
