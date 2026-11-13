# ADR 0005: which interface endpoints, and why

## Context

The tools Lambda is in the VPC and reaches RDS privately. It needs two AWS services from inside the VPC, and no internet route. Each interface endpoint is billed per AZ-hour and per GB processed.

## Alternatives

- **Interface endpoints for every service the tools use.** Private, but each endpoint costs per AZ-hour.
- **NAT gateway for outbound calls.** Not priced here; the lab avoids it.
- **Gateway endpoint for S3.** No hourly charge (the S3 gateway endpoint is not priced in the model).

## Decision

Lab and prod use the same set:

- **S3 gateway endpoint** for the bucket of the documents (no hourly cost; not priced in the model).
- **Interface endpoint for CloudWatch Logs** (the tools Lambda writes logs).
- **Interface endpoint for Step Functions (`states`)** (the tools Lambda returns the task token after a human approval).

Anything the database does not need stays outside the VPC: the agent Lambda calls Bedrock and Cognito from outside (ADR 0004).

## Consequences

- Two interface endpoints in each AZ where the tools Lambda runs. The lab uses one AZ (ADR 0006).
- The model counts 2 endpoints (`endpoints: 2` in `modelo.py`).

## Costs (from `precios.json` and `modelo.py`)

- Interface endpoint, per endpoint-hour: **0.01 USD** (M, `USE1-VpcEndpoint-Hours`, SKU `EN2N5TATXE673A3B`, Price List, 2026-11-13). The per-AZ multiplier comes from the official page (D): billing is per hour per AZ where the endpoint is provisioned.
- Interface endpoint, per GB processed: **0.01 USD** (M, `USE1-VpcEndpoint-Bytes`, SKU `DQYYEZBCWSW5XS2R`, first 1 PB tier, 2026-11-13). The model counts 1 GB per month as a placeholder: 0.01 USD.
- Lab: 2 endpoints × 1 AZ × 0.01 USD = **0.02 USD per hour**. Prod: 2 × 3 × 0.01 = **0.06 USD per hour**.
