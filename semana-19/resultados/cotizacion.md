# Week 19, activity 2: predicted vs real cost

Predicted by `semana-19/costos/modelo.py` (`precios.json`, token percentiles from week 13). The **real** column is empty: activity 8 fills it from Cost Explorer after the runs. The error column is empty for the same reason.

## Parameters used

- Queries per day: 100; stack up 8 h per day; tokens at p95 of week 13 (input 52712, output 3978).
- Haiku 4.5, `us.` profile, regional prices (confirmed by the user). Haiku 5.5 has quota 0 and is not used.
- Lambda: 512 MB and 3 s per query (declared assumption). Titan V2: 50 tokens per query. CloudWatch: 20 KB of logs per query. Cognito: 10 MAU. 1 GB of endpoint traffic per month.
- Credits: US$142, no expiry (H5, data from Manuel's Billing screen, marked D). Free tier is not applied (not measured).
- Profiles: lab = 1 AZ, Single-AZ database, 0 public IPv4, 2 endpoints, 2 KMS keys; prod = 3 AZ, Multi-AZ database (N), 2 public IPv4, 2 endpoints, 3 KMS keys.

## Predicted per hour and per query

| Profile | Item | Predicted (USD) | Real (USD) | Error % | Marks |
|---|---|---|---|---|---|
| lab | per hour of stack (measured lines) | 0.021890 | | | partial: endpoint lines N |
| lab | per query (measured lines) | 0.07989142 | | | M (Haiku 4.5, 2026-10-28 price; re-query pending login) |
| prod | per hour of stack (measured lines) | 0.033260 | | | partial: endpoint lines N |
| prod | per query (measured lines) | 0.07989142 | | | M (Haiku 4.5, 2026-10-28 price; re-query pending login) |

## Predicted per month (100 queries/day, 8 h/day)

| Profile | Predicted total (USD) | Real (USD) | Error % | Net with credits (USD) | Not measured (N, outside total) |
|---|---|---|---|---|---|
| lab | 245.1180 | | | 103.1180 | Endpoints de interfaz de VPC (endpoints x AZ-hora); Lambda, solicitudes |
| prod | 247.9667 | | | 105.9667 | RDS Multi-AZ, instancia adicional; Endpoints de interfaz de VPC (endpoints x AZ-hora); Lambda, solicitudes |

## Per-item detail

### lab

| Item | Frequency | Mark | Amount | USD |
|---|---|---|---|---|
| KMS, llaves administradas (prorrateado) | por hora | M | 0.00273973 llave-hora | 0.002740 |
| RDS db.t4g.micro, instancia | por hora | M | 1 instancia-hora | 0.016000 |
| RDS gp3, 20 GB (prorrateado) | por hora | M | 0.0273973 GB-hora | 0.003151 |
| IPv4 pública en uso | por hora | M | 0 dirección-hora | 0.000000 |
| Endpoints de interfaz de VPC (endpoints x AZ-hora) | por hora | N | 2 endpoint-AZ-hora | N |
| Cognito, MAU | por mes | M | 10 MAU | 0.150000 |
| CloudWatch Logs, almacenamiento | por mes | M | 1 GB-mes | 0.030000 |
| Endpoints de VPC, datos procesados | por mes | D | 1 GB | 0.010000 |
| Step Functions, transiciones por aprobación | por mes | D | 0 transiciones | 0.000000 |
| Haiku 4.5 (us.), tokens de entrada | por consulta | M | 0.0527117 M tokens | 0.057983 |
| Haiku 4.5 (us.), tokens de salida | por consulta | M | 0.0039783 M tokens | 0.021881 |
| Lambda, GB-segundo | por consulta | M | 1.5 GB-s | 0.000016 |
| Lambda, solicitudes | por consulta | N | 1 solicitud | N |
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
| Endpoints de interfaz de VPC (endpoints x AZ-hora) | por hora | N | 6 endpoint-AZ-hora | N |
| Cognito, MAU | por mes | M | 10 MAU | 0.150000 |
| CloudWatch Logs, almacenamiento | por mes | M | 5 GB-mes | 0.150000 |
| Endpoints de VPC, datos procesados | por mes | D | 1 GB | 0.010000 |
| Step Functions, transiciones por aprobación | por mes | D | 0 transiciones | 0.000000 |
| Haiku 4.5 (us.), tokens de entrada | por consulta | M | 0.0527117 M tokens | 0.057983 |
| Haiku 4.5 (us.), tokens de salida | por consulta | M | 0.0039783 M tokens | 0.021881 |
| Lambda, GB-segundo | por consulta | M | 1.5 GB-s | 0.000016 |
| Lambda, solicitudes | por consulta | N | 1 solicitud | N |
| API Gateway HTTP API, solicitudes | por consulta | M | 1 solicitud | 0.000001 |
| Titan V2, embedding de la consulta | por consulta | M | 0.05 K tokens | 0.000001 |
| CloudWatch Logs, ingesta | por consulta | M | 2e-05 GB | 0.000010 |
| AgentCore Gateway, invocaciones | por consulta | M | 0 invocaciones | 0.000000 |

