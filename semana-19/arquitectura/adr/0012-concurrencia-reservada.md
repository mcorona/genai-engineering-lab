# ADR 0012: reserved concurrency on the Lambdas, within the account quota

## Context

The account's Lambda concurrent executions quota is **400** (Service Quotas, read on this date). AWS requires leaving a
minimum of 10 unreserved, which the quota allows.

## Alternatives

- **(a)** Reserve concurrency on each Lambda of the workflow; the sum stays far below 400.
- **(b)** No reservation; rely on API throttling. Simpler, but one route can starve the others.

## Decision

**(a).** Concrete values are set in the code with the reason next to each one.

## Consequences

- No quota increase is needed.

## Costs

- Reserved concurrency has no charge of its own (**M**, 0 USD); Lambda is billed per use (`lambda_solicitud`, `lambda_arm_gb_s`, **M**).
