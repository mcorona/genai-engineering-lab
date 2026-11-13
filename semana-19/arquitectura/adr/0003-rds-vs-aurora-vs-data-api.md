# ADR 0003: RDS PostgreSQL, Aurora Serverless v2 or the Data API

## Context

The tools of the agent read and write the business database (copilot_ro for reads, a write role for approved orders). The access uses IAM authentication. The question is which PostgreSQL service to run, and whether the database needs the VPC at all.

## Alternatives

- **RDS PostgreSQL, db.t4g.micro, Single-AZ.** Fixed cost per hour; the database is in the VPC.
- **Aurora Serverless v2.** Cost per ACU-hour; it can scale down, but the minimum ACU and the scale-to-zero behavior are not measured here (D, Aurora doc).
- **RDS Data API.** No VPC needed: the Lambda calls an HTTPS endpoint. It removes the interface endpoints the database path would need, but its price is not measured in this activity.

## Decision

**RDS PostgreSQL db.t4g.micro for the lab**, Single-AZ, with IAM authentication. It has the lowest measured fixed cost and no ACU behavior to explain in a demo.

**Prod keeps RDS** with Multi-AZ; its price is N, so the prod cost table says so. Aurora Serverless v2 and the Data API are recorded here as options; the Data API would be revisited if the VPC endpoints cost more than the database.

## Consequences

- The database sits in the VPC, so the tools Lambda is in the VPC too (see ADR 0005 for the endpoints).
- Data API would remove the VPC requirement for the database path; it is not chosen because its price is not measured.

## Costs (from `precios.json`)

- db.t4g.micro, per hour: **0.016 USD** (M, `InstanceUsage:db.t4g.micro`, 2026-11-12). Per month: 0.016 × 730 = 11.68 USD.
- gp3 storage, per GB-month: **0.115 USD** (M, `RDS:GP3-Storage`). 20 GB: 2.30 USD per month.
- Aurora Serverless v2, per ACU-hour: **0.12 USD** (M, `Aurora:ServerlessV2Usage`). Not used in the lab; 1 ACU all month would be 0.12 × 730 = 87.60 USD.
- Data API: **N**.
- Multi-AZ instance in prod: **N**.
