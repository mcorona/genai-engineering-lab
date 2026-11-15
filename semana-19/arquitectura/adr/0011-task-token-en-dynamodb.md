# ADR 0011: the Step Functions task token lives in DynamoDB, with TTL equal to the approval timeout

## Context

The approval step waits with `.waitForTaskToken`; the approve route needs the token. The token must never appear in logs
or in an API response.

## Alternatives

- **(a)** DynamoDB, on-demand, encrypted with the project key, TTL equal to the approval timeout. The request is written
  by step 1 of the state machine.
- **(b)** A `PENDING_APPROVAL` row in RDS. Forces the approval Lambda into the VPC and mixes the workflow with the
  database.

## Decision

**(a).** Only the approval step writes orders to RDS, through the `order_writer` role created in activity 4.

## Consequences

- The token stays out of logs (checked by a log-capture test) and out of responses.
- Costs: DynamoDB on-demand is not in `precios.json`; **not quoted**.
