# Week 19, activity 2: predicted vs real cost

Predicted by `semana-19/costos/modelo.py` (`precios.json`, token percentiles from week 13). The **real** column and the error column are empty: activity 8 fills them from Cost Explorer after the runs.

## Parameters used

- Queries per day: 100; stack up 8 h per day; tokens at p95 of week 13 (input 52712, output 3978).
- Haiku 4.5, `us.` profile, regional prices (M, Price List 2026-11-13). Haiku 5.5 has quota 0 and is not used.
- Lambda: 512 MB and 3 s per query (declared assumption). Titan V2: 50 tokens per query. CloudWatch: 20 KB of logs per query. Cognito: 10 MAU. 1 GB of endpoint traffic per month.
- Credits: US$142, no expiry (H5, Manuel's Billing screen, D). Free tier is not applied (not measured).
- Profiles: lab = 1 AZ, Single-AZ database, 0 public IPv4, 2 endpoints, 2 KMS keys; prod = 3 AZ, Multi-AZ database (N), 2 public IPv4, 2 endpoints, 3 KMS keys.

## Predicted per hour and per query

| Profile | Item | Predicted (USD) | Real (USD) | Error % | Marks |
|---|---|---|---|---|---|
| lab | per hour of stack | 0.041890 | | | M |
| lab | per query | 0.07989162 | | | M (Haiku 4.5, Lambda, Titan, API GW, CloudWatch) |
| prod | per hour of stack | 0.093260 | | | partial: RDS Multi-AZ N |
| prod | per query | 0.07989162 | | | M (Haiku 4.5, Lambda, Titan, API GW, CloudWatch) |

## Predicted per month (100 queries/day, 8 h/day)

| Profile | Predicted total (USD) | Real (USD) | Error % | Net with credits (USD) | Not measured (N, outside total) |
|---|---|---|---|---|---|
| lab | 249.9186 | | | 107.9186 | none |
| prod | 262.3673 | | | 120.3673 | RDS Multi-AZ, instancia adicional |

## Per-item detail

### lab

| Item | Frequency | Mark | Amount | USD |
|---|---|---|---|---|
| KMS, llaves administradas (prorrateado) | por hora | M | 0.00273973 llave-hora | 0.002740 |
| RDS db.t4g.micro, instancia | por hora | M | 1 instancia-hora | 0.016000 |
| RDS gp3, 20 GB (prorrateado) | por hora | M | 0.0273973 GB-hora | 0.003151 |
| IPv4 pública en uso | por hora | M | 0 dirección-hora | 0.000000 |
| Endpoints de interfaz de VPC (endpoints x AZ-hora) | por hora | M | 2 endpoint-AZ-hora | 0.020000 |
| Cognito, MAU | por mes | M | 10 MAU | 0.150000 |
| CloudWatch Logs, almacenamiento | por mes | M | 1 GB-mes | 0.030000 |
| Endpoints de VPC, datos procesados | por mes | M | 1 GB | 0.010000 |
| Step Functions, transiciones por aprobación | por mes | D | 0 transiciones | 0.000000 |
| Haiku 4.5 (us.), tokens de entrada | por consulta | M | 0.0527117 M tokens | 0.057983 |
| Haiku 4.5 (us.), tokens de salida | por consulta | M | 0.0039783 M tokens | 0.021881 |
| Lambda, GB-segundo | por consulta | M | 1.5 GB-s | 0.000016 |
| Lambda, solicitudes | por consulta | M | 1 solicitud | 0.000000 |
| API Gateway HTTP API, solicitudes | por consulta | M | 1 solicitud | 0.000001 |
| Titan V2, embedding de la consulta | por consulta | M | 0.05 K tokens | 0.000001 |
| CloudWatch Logs, ingesta | por consulta | M | 2e-05 GB | 0.000010 |
| AgentCore Gateway, invocaciones | por consulta | M | 0 invocaciones | 0.000000 |

### prod

| Item | Frequency | Mark | Amount | USD |
|---|---|---|---|---|
| KMS, llaves administradas (prorrateado) | por hora | M | 0.00410959 llave-hora | 0.004110 |
| RDS db.t4g.micro, instancia | por hora | M | 1 instancia-hora | 0.016000 |
| RDS gp3, 20 GB (prorrateado) | por hora | M | 0.0273973 GB-hora | 0.003151 |
| RDS Multi-AZ, instancia adicional | por hora | N | 1 instancia-hora | N |
| IPv4 pública en uso | por hora | M | 2 dirección-hora | 0.010000 |
| Endpoints de interfaz de VPC (endpoints x AZ-hora) | por hora | M | 6 endpoint-AZ-hora | 0.060000 |
| Cognito, MAU | por mes | M | 10 MAU | 0.150000 |
| CloudWatch Logs, almacenamiento | por mes | M | 5 GB-mes | 0.150000 |
| Endpoints de VPC, datos procesados | por mes | M | 1 GB | 0.010000 |
| Step Functions, transiciones por aprobación | por mes | D | 0 transiciones | 0.000000 |
| Haiku 4.5 (us.), tokens de entrada | por consulta | M | 0.0527117 M tokens | 0.057983 |
| Haiku 4.5 (us.), tokens de salida | por consulta | M | 0.0039783 M tokens | 0.021881 |
| Lambda, GB-segundo | por consulta | M | 1.5 GB-s | 0.000016 |
| Lambda, solicitudes | por consulta | M | 1 solicitud | 0.000000 |
| API Gateway HTTP API, solicitudes | por consulta | M | 1 solicitud | 0.000001 |
| Titan V2, embedding de la consulta | por consulta | M | 0.05 K tokens | 0.000001 |
| CloudWatch Logs, ingesta | por consulta | M | 2e-05 GB | 0.000010 |
| AgentCore Gateway, invocaciones | por consulta | M | 0 invocaciones | 0.000000 |

