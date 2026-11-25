# Week 19, activity 2: predicted vs real cost

Predicted by `semana-19/costos/modelo.py` (`precios.json`). v1 is activity 2's model (token p95 of week 13); v2 is
the correction from activity 8 (the deployed agent's mean tokens). The real and error columns come from Cost
Explorer, read on 2026-11-21 (`resultados/costo_real.md`). Error = (real − predicted) / predicted.

## Parameters used

- Queries per day: 100; stack up 8 h per day; tokens at p95 of week 13 (input 52712, output 3978).
- Haiku 4.5, `us.` profile, regional prices (M, Price List 2026-11-13). Haiku 5.5 has quota 0 and is not used.
- Lambda: 512 MB and 3 s per query (declared assumption). Titan V2: 50 tokens per query. CloudWatch: 20 KB of logs per query. Cognito: 10 MAU. 1 GB of endpoint traffic per month.
- Credits: US$142, no expiry (H5, Manuel's Billing screen, D). Free tier is not applied (not measured).
- Profiles: lab = 1 AZ, Single-AZ database, 0 public IPv4, 2 endpoints, 2 KMS keys; prod = 3 AZ, Multi-AZ database (N), 2 public IPv4, 2 endpoints, 3 KMS keys.

## Predicted per hour and per query

| Version | Profile | Item | Predicted (USD) | Real (USD) | Error % | Marks |
|---|---|---|---|---|---|---|
| v1 | lab | per hour of stack | 0.041890 | 0.037562 | −10.3 | M |
| v1 | lab | per query | 0.07989162 | 0.038562 (bound) / 0.030913 (model) | −51.7 / −61.3 | M (Haiku 4.5, Lambda, Titan, API GW, CloudWatch) |
| v1 | prod | per hour of stack | 0.093260 | n/a | — | partial: RDS Multi-AZ N; prod was never deployed |
| v1 | prod | per query | 0.07989162 | 0.038562 (bound) / 0.030913 (model) | −51.7 / −61.3 | M |
| v2 | lab | per hour of stack | 0.041890 | 0.037562 | −10.3 | M (unchanged from v1) |
| v2 | lab | per query | 0.03094130 | 0.038562 (bound) / 0.030913 (model) | +24.6 / −0.1 | partial: ApplyGuardrail N |
| v2 | prod | per hour of stack | 0.093260 | n/a | — | partial: RDS Multi-AZ N; prod was never deployed |
| v2 | prod | per query | 0.03094130 | 0.038562 (bound) / 0.030913 (model) | +24.6 / −0.1 | partial: ApplyGuardrail N |

## Predicted per month (100 queries/day, 8 h/day)

No month ran at this volume, so there is no real column here.

| Version | Profile | Predicted total (USD) | Net with credits (USD) | Not measured (N, outside total) |
|---|---|---|---|---|
| v1 | lab | 249.9186 | 107.9186 | none |
| v1 | prod | 262.3673 | 120.3673 | RDS Multi-AZ, additional instance |
| v2 | lab | 103.0676 | 0.0000 | ApplyGuardrail, text units |
| v2 | prod | 115.5164 | 0.0000 | RDS Multi-AZ, additional instance; ApplyGuardrail, text units |

## Activity 8: the first real row

Source: Cost Explorer calls 2 and 3 of 3, period [2026-11-19, 2026-11-21) UTC, read on 2026-11-21. The base stack
was up 26.004 h inside it. Every figure in this section is in `resultados/costo_real.md`, which is rendered from
`resultados/eval_aws/costo_real.json`.

**Fixed per hour and per query.**

- **Fixed per hour:** VPC endpoints, RDS, KMS and Secrets Manager, 0.976755 USD, or 0.037562 USD per hour.
- **Per query:** the model, Bedrock, API Gateway, DynamoDB, S3, Lambda and Step Functions, 2.198034 USD over 57
  agent tasks.
- **Set apart:**
  - Cost Explorer itself, 0.02 USD;
  - activity 7's AgentCore charges, 0.001655 USD;
  - activity 7's model spend on the same UTC day, 0.481538 USD. That spend comes from activity 7's own spans; once
    it is set apart, the Haiku line equals activity 8's spans to the cent (1.762053 USD).

**Per query: the dominant item is Claude Haiku 4.5.** It is 1.762053 of the 2.198034 USD per query, or 80%.

- **v1 error: −61.3%** against the model part, and −51.7% against the upper bound, beyond ±20%.
- **Why v1 was off:** v1 priced week 13's local p95, 52,712 input and 3,978 output tokens. The deployed agent's mean
  over the same 57 tasks Cost Explorer billed is 21,273 input and 1,366 output tokens. Two causes:
  - **the statistic:** a p95 priced against a mean bill;
  - **the runs:** week 13's runs were Haiku 5.5 locally, and these are Haiku 4.5 behind the API.
- **No prompt cache:** 0 cached tokens were measured, so caching explains none of the gap.
- **The fix:** v2 takes that mean. It changes the model, not the number.
- **v2 error: −0.1%** against the model part, and +24.6% against the upper bound. The rest of the upper bound is
  Cost Explorer's "Amazon Bedrock" line, 0.432590 USD, which joins the Bedrock judge's job (an eval cost, not a
  query's), ApplyGuardrail and Titan, and cannot be split by service. v2 lists ApplyGuardrail as N until its price
  and units per query are measured.

**Per hour: −10.3% (lab), within ±20%, so the per-hour model is unchanged.** The total hides two items that move in
opposite directions:

| Item | Predicted (USD/h) | Real (USD/h) |
|---|---|---|
| VPC | 0.020000 (2 interface endpoints) | 0.028073 |
| RDS (instance and storage) | 0.019151 | 0.007591 |

- **VPC is higher:** the IaC has 3 interface endpoints (logs and states in the base, Secrets Manager in datos).
- **RDS is lower:** the cause was not verified.
- **Prod:** its per-hour row is n/a, since prod was never deployed.

## Per-item detail

### lab

| Item | Frequency | Mark | Amount | USD |
|---|---|---|---|---|
| KMS, customer managed keys (prorated) | per hour | M | 0.00273973 key-hour | 0.002740 |
| RDS db.t4g.micro, instance | per hour | M | 1 instance-hour | 0.016000 |
| RDS gp3, 20 GB (prorated) | per hour | M | 0.0273973 GB-hour | 0.003151 |
| Public IPv4 in use | per hour | M | 0 address-hour | 0.000000 |
| VPC interface endpoints (endpoints x AZ-hour) | per hour | M | 2 endpoint-AZ-hour | 0.020000 |
| Cognito, MAU | per month | M | 10 MAU | 0.150000 |
| CloudWatch Logs, storage | per month | M | 1 GB-month | 0.030000 |
| VPC endpoints, data processed | per month | M | 1 GB | 0.010000 |
| Step Functions, transitions per approval | per month | D | 0 transitions | 0.000000 |
| Haiku 4.5 (us.), input tokens | per query | M | 0.0527117 M tokens | 0.057983 |
| Haiku 4.5 (us.), output tokens | per query | M | 0.0039783 M tokens | 0.021881 |
| Lambda, GB-second | per query | M | 1.5 GB-s | 0.000016 |
| Lambda, requests | per query | M | 1 request | 0.000000 |
| API Gateway HTTP API, requests | per query | M | 1 request | 0.000001 |
| Titan V2, query embedding | per query | M | 0.05 K tokens | 0.000001 |
| CloudWatch Logs, ingestion | per query | M | 2e-05 GB | 0.000010 |
| AgentCore Gateway, invocations | per query | M | 0 invocations | 0.000000 |

### prod

| Item | Frequency | Mark | Amount | USD |
|---|---|---|---|---|
| KMS, customer managed keys (prorated) | per hour | M | 0.00410959 key-hour | 0.004110 |
| RDS db.t4g.micro, instance | per hour | M | 1 instance-hour | 0.016000 |
| RDS gp3, 20 GB (prorated) | per hour | M | 0.0273973 GB-hour | 0.003151 |
| RDS Multi-AZ, additional instance | per hour | N | 1 instance-hour | N |
| Public IPv4 in use | per hour | M | 2 address-hour | 0.010000 |
| VPC interface endpoints (endpoints x AZ-hour) | per hour | M | 6 endpoint-AZ-hour | 0.060000 |
| Cognito, MAU | per month | M | 10 MAU | 0.150000 |
| CloudWatch Logs, storage | per month | M | 5 GB-month | 0.150000 |
| VPC endpoints, data processed | per month | M | 1 GB | 0.010000 |
| Step Functions, transitions per approval | per month | D | 0 transitions | 0.000000 |
| Haiku 4.5 (us.), input tokens | per query | M | 0.0527117 M tokens | 0.057983 |
| Haiku 4.5 (us.), output tokens | per query | M | 0.0039783 M tokens | 0.021881 |
| Lambda, GB-second | per query | M | 1.5 GB-s | 0.000016 |
| Lambda, requests | per query | M | 1 request | 0.000000 |
| API Gateway HTTP API, requests | per query | M | 1 request | 0.000001 |
| Titan V2, query embedding | per query | M | 0.05 K tokens | 0.000001 |
| CloudWatch Logs, ingestion | per query | M | 2e-05 GB | 0.000010 |
| AgentCore Gateway, invocations | per query | M | 0 invocations | 0.000000 |


## Estimate to authorize activity 3

The base stack of activity 3 (KMS, VPC endpoints, IAM and budget), with 1 AZ in lab. Every item is measured (M), except the per-AZ multiplier of the endpoints, which comes from the official pricing page (D).

| Item | Price | Per hour (lab) |
|---|---|---|
| KMS, 2 customer managed keys | 1.00 USD per key-month (M, `us-east-1-KMS-Keys`) | 0.00273973 |
| Interface endpoints, 2 × 1 AZ | 0.01 USD per endpoint-hour (M, `USE1-VpcEndpoint-Hours`) | 0.02000000 |
| AWS Budgets, 1 budget | 0.00 USD within 62 budget-days a month (M, `BudgetsUsage`) | 0.00000000 |
| IAM | no charge | 0.00000000 |
| **Total per hour (lab)** | | **0.02273973** |

**A session of N hours = 0.02273973 × N USD** (lab). Examples: 1 h = 0.0227 USD; 4 h = 0.0910 USD; 8 h = 0.1819 USD.
Prod (3 AZ, 3 keys): 0.06410959 USD per hour. RDS Multi-AZ is not part of the base stack.

## Activity 7: estimated vs real

Real figures come from Cost Explorer on 2026-11-19: 2 calls, saved in `resultados/agentes/costo_cost_explorer.json`.
Cost Explorer days are UTC, so the runs of the evening of 2026-11-18 (CST) fall on 2026-11-19. Both days were still
marked Estimated. Every charge was covered by credits, so the net is 0. Cost Explorer does not split charges by
activity. Where other runs of the same days share a line, the real figure is an upper bound (≤).

| Item | Estimated (USD) | Real (USD) | Source of the real figure |
|---|---|---|---|
| Model, paths (a) and (b) | 0.24 | 0.6430 | the spans of the three runs: (a) discarded 0.1614, (a) 0.2405, (b) 0.2410. Cost Explorer bills Haiku 4.5 at the same 1.10 and 5.50 USD per million tokens; its line for both days is 0.7689 for 543,238 tokens, against 453,893 in the spans |
| Model, path (c) | ≤ 0.36 | 0 | no agent could be created |
| Gateway invocations and Policy authorizations | 0.0007 | 0.001655 | Cost Explorer: 56 invocations (0.00028) and 55 authorizations (0.001375). Only activity 7 used AgentCore |
| ApplyGuardrail | ≤ 0.29 | ≤ 0.1424 | Cost Explorer: 356 text units per policy over both days, from every run of those days |
| Lambda, API and logs | < 0.01 | 0.000492 | Cost Explorer: API Gateway; Lambda and CloudWatch billed 0 |
| Cost Explorer calls | not estimated | 0.02 | 2 calls at 0.01 USD each |
| **Total new spend of the activity** | **≈ 0.90** | **≤ 0.8075** | −10% at the upper bound |

The total was close, but the items were not:

- **Model cost per task was about twice the estimate.** A task of (a) used 17,146 tokens, against 7,154 to 8,223 input
  tokens per query in activity 6. The week 13 task message and the 4.6 steps per task explain it.
- **The unrun path (c) offset that difference.**
- **AgentCore was 2.4 times its estimate, and still under 0.002 USD.** The estimate counted 30 invocations and 20
  authorizations. The bill counts 56 and 55, which include `tools/list` and the live Policy test.

The stack hours (0.16 in the estimate) were not new spend, since the base stack ran all day.
