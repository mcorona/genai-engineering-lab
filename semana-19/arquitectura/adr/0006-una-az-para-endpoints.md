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

- Lab: 2 endpoints × 1 AZ × endpoint AZ-hour = **N** (not priced).
- Prod: 2 endpoints × 3 AZ × endpoint AZ-hour = **N**.
- The model's partial total for lab is 5.44 USD per month with 8 h/day and 0 queries, and 245.12 USD with 100 queries/day; both exclude the endpoint lines.
