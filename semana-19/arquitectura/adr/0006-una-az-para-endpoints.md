# ADR 0006: one AZ for the endpoints in the lab, and what changes in prod

## Context

Interface endpoints are billed per AZ-hour (ADR 0005). Running them in every AZ multiplies that cost. The lab is a demo; prod needs AZ redundancy.

## Alternatives

- **One AZ in the lab, three AZs in prod.** Lowest endpoint cost for the demo; no AZ redundancy in the lab.
- **Three AZs in the lab.** Same redundancy as prod, three times the endpoint hourly cost.

## Decision

**Lab: one AZ** for the endpoints and the tools Lambda. **Prod: three AZs**, with the Multi-AZ database (ADR 0003). The lab accepts that an AZ failure stops the tools; the demo says so.

## Consequences

- The difference between lab and prod is the AZ count in `perfil` (`azs: 1` vs `azs: 3`). This is the value the cost model reads.
- Moving lab to prod multiplies the endpoint hourly cost by 3. That multiplier is N until the endpoint rate is measured.

## Costs (from `modelo.py`)

- Lab: 2 endpoints × 1 AZ × 0.01 USD per endpoint-hour = **0.02 USD per hour** (M).
- Prod: 2 endpoints × 3 AZ × 0.01 USD = **0.06 USD per hour** (M). The prod total stays partial because RDS Multi-AZ is N (ADR 0003).
- Lab total with 8 h per day: 10.24 USD per month with 0 queries, and 249.92 USD with 100 queries per day (both measured, no N).
- Prod total: 22.69 USD per month with 0 queries and 262.37 USD with 100 queries per day, partial (RDS Multi-AZ N).
