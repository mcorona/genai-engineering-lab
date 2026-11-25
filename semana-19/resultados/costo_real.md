# Week 19, activity 8: real cost from Cost Explorer

Rendered by `eval/costo_real.py --informe` from `resultados/eval_aws/costo_real.json`. Do not edit by hand.

## Period and calls

- Period: [2026-11-19, 2026-11-21) UTC, DAILY. The base stack was up 26.004 h inside it (CloudFormation's stack history).
- Two GetCostAndUsage calls (calls 2 and 3 of 3 in `cost_explorer.json`): A filtered by the tag `proyecto=semana19` and grouped by service; B unfiltered, grouped by service and record type.
- Every day still Estimated: yes. Credits covered 3.6780 USD; net 0.0000 USD.
- Agent tasks billed in the period: 57 (crudo_eval.json 19, crudo_eval_descartada_1.json 22, crudo_eval_descartada_2.json 14, aprobacion_e2e.json 2).

## By service (call B, usage)

| Service | Usage (USD) | Split |
|---|---|---|
| Claude Haiku 4.5 (Amazon Bedrock Edition) | 2.243591 | per query |
| Amazon Virtual Private Cloud | 0.730001 | fixed per hour |
| Amazon Bedrock | 0.432590 | per query |
| Amazon Relational Database Service | 0.197395 | fixed per hour |
| AWS Key Management Service | 0.036111 | fixed per hour |
| AWS Cost Explorer | 0.020000 | outside the queries |
| AWS Secrets Manager | 0.013248 | fixed per hour |
| Amazon Simple Storage Service | 0.001998 | per query |
| Amazon Bedrock AgentCore | 0.001655 | outside the queries |
| Amazon API Gateway | 0.001125 | per query |
| Amazon DynamoDB | 0.000268 | per query |
| AWS Budgets | 0.000000 | no charge |
| AWS CloudFormation | 0.000000 | no charge |
| AWS Glue | 0.000000 | no charge |
| AWS Lambda | 0.000000 | no charge |
| AWS Step Functions | 0.000000 | no charge |
| AmazonCloudWatch | 0.000000 | no charge |

## By the tag proyecto=semana19 (call A)

Only tagged resources: inference calls are not resources, so the model lines are missing here.

| Day | Service | USD |
|---|---|---|
| 2026-11-19 | AWS Key Management Service | 0.033333 |
| 2026-11-19 | AWS Lambda | 0.000000 |
| 2026-11-19 | AWS Secrets Manager | 0.013248 |
| 2026-11-19 | Amazon Relational Database Service | 0.197395 |
| 2026-11-19 | Amazon Simple Storage Service | 0.000456 |
| 2026-11-19 | Amazon Virtual Private Cloud | 0.710001 |
| 2026-11-19 | AmazonCloudWatch | 0.000000 |
| 2026-11-20 | AWS Key Management Service | 0.002778 |
| 2026-11-20 | AWS Lambda | 0.000000 |
| 2026-11-20 | Amazon Simple Storage Service | 0.000005 |
| 2026-11-20 | Amazon Virtual Private Cloud | 0.020000 |
| 2026-11-20 | AmazonCloudWatch | 0.000000 |

## Split

- Fixed per hour (VPC, RDS, KMS, Secrets Manager): 0.976755 USD, 0.037562 USD per hour of stack.
- Per query: 2.198034 USD after setting apart the other activities' runs.
- Outside the queries: AWS Cost Explorer 0.020000 USD (the cost calls themselves: measurement, not the workload); Amazon Bedrock AgentCore 0.001655 USD (activity 7's gateway and Policy, destroyed before this run).
- Other activities' model spend in the period, from their spans: `crudo_directo.json` 0.240525 USD; `crudo_gateway.json` 0.241013 USD (activity 7's paths (a) and (b), the evening of 2026-11-18 CST).

**Reconciliation:** the Haiku line minus those runs is 1.762053 USD; the spans of the 57 tasks add up to 1.762053 USD (difference 0.000000).

## Cost per query

- Model alone (exact): 0.030913 USD per task.
- Every per-query line (upper bound): 0.038562 USD per task. Cost Explorer's "Amazon Bedrock" line joins the Bedrock judge's job (an eval cost, not a query's), ApplyGuardrail and Titan; grouping by service cannot split them.

## Predicted against real

| Version | Row | Predicted (USD) | Real (USD) | Error | Real, model alone (USD) | Error | Beyond ±20% |
|---|---|---|---|---|---|---|---|
| v1 | lab.por_consulta | 0.07989162 | 0.038562 | -51.7% | 0.030913 | -61.3% | yes |
| v1 | lab.por_hora | 0.04189041 | 0.037562 | -10.3% | — | — | no |
| v1 | prod.por_consulta | 0.07989162 | 0.038562 | -51.7% | 0.030913 | -61.3% | yes |
| v1 | prod.por_hora | 0.09326027 | n/a | — | — | — | prod was never deployed; the real hours are lab's |
| v2 | lab.por_consulta | 0.03094130 | 0.038562 | +24.6% | 0.030913 | -0.1% | yes |
| v2 | lab.por_hora | 0.04189041 | 0.037562 | -10.3% | — | — | no |
| v2 | prod.por_consulta | 0.03094130 | 0.038562 | +24.6% | 0.030913 | -0.1% | yes |
| v2 | prod.por_hora | 0.09326027 | n/a | — | — | — | prod was never deployed; the real hours are lab's |

## What stayed out or could not be attributed

- The "Amazon Bedrock" line cannot be split between the judge, ApplyGuardrail and Titan; it only enters the upper bound.
- DAILY granularity: anything else that ran on those UTC days is in the lines. The other activities' runs that are known are set apart above.
- The days were still Estimated when read: the final bill may move by cents.

## Week 19 total (activity 10)

One GetCostAndUsage call (`costos/costo_semana.py`, `resultados/costo_semana.json`): the whole account, [2026-11-13, 2026-11-24) UTC, MONTHLY, by service and record type. Still Estimated: yes.

- **Gross: 8.928936 USD**; credits -8.928936 USD; net 0.000000 USD. Weekly cap: 10.00 USD.
- Fixed by the hour (VPC, RDS, KMS, Secrets Manager): 5.302241 USD, 59.4% of the gross.

| Service | Usage (USD) |
|---|---|
| Amazon Virtual Private Cloud | 3.420003 |
| Claude Haiku 4.5 (Amazon Bedrock Edition) | 2.898466 |
| Amazon Relational Database Service | 1.661135 |
| Amazon Bedrock | 0.556655 |
| AWS Key Management Service | 0.163889 |
| AWS Cost Explorer | 0.150000 |
| AWS Secrets Manager | 0.057214 |
| Amazon Simple Storage Service | 0.017830 |
| Amazon Bedrock AgentCore | 0.001655 |
| Amazon API Gateway | 0.001632 |
| Amazon DynamoDB | 0.000397 |
| AmazonCloudWatch | 0.000060 |

Against the written estimates of the activities that created resources (3 to 9):

| Activity | Estimate (USD) | What it covered | Source |
|---|---|---|---|
| 3 | 0.05000 | about 0.05 USD for about 2 h of the base stack at 0.02273973 USD/h | `resultados/base.md` |
| 4 | 0.06000 | about 0.06 USD for a planned session | `resultados/costo_actividad4.md` |
| 5 | — | no written figure: guardrail/prueba_viva.py prints its estimate at run time (cap 5 USD) | `guardrail/prueba_viva.py` |
| 6 | — | no written figure | `Fas5Sema19.md (Log)` |
| 7 | 0.90000 | about 0.90 USD | `Fas5Sema19.md (Log, 2026-11-18)` |
| 8 | 0.14105 | the judge's job only, 0.14105 USD; the eval had caps, not an estimate (1.90, 0.20, 0.45 USD) | `resultados/eval_aws.md` |
| 9 | 0.52000 | about 0.52 USD nominal, 0.89 USD upper bound | `resultados/seguridad/estimacion.md` |

The written estimates add up to 1.67105 USD (5 of 7 activities); the week's gross is 8.928936 USD. Most of the gap is the fixed part: each estimate priced one session, while the stack stayed up between sessions, across several days. Activities 5 and 6 left no written figure.
