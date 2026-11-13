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

- Interface endpoint, per endpoint per AZ-hour: **N**. The official page (`privatelink/pricing`, read 2026-11-13) does not state the us-east-1 rate. The model lists the line as N and does not add it to the total.
- Interface endpoint, per GB processed: **0.01 USD** (D, same page, "First 1 PB"). The model uses 1 GB per month as a placeholder: 0.01 USD.
- With two endpoints in one AZ, the hourly cost is **2 × N**. It cannot be quoted yet: the total of the lab is partial until it is measured.
