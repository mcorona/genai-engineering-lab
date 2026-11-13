# Week 19, activity 1: baseline of the account, the services and the prices

Measured on 2026-11-12 with `linea_base/verificar.py` (operator identity, read-only) and `infra/inventario.py`. Raw results: `resultados/linea_base_mac.json` and `resultados/inventario_mac.json`. Account IDs, ARNs and home paths are removed from both files.

Marks: **M** measured by a run (date recorded), **D** documented (official link), **N** not verified (the reason is given).

Cost of the activity: **one** Cost Explorer call ($0.01 per call, authorized by Manuel), no model invoked, no resource created.

## 1. Hallazgos que cambian el plan

| # | Hallazgo | Marca | Fuente y fecha | Efecto en el plan |
|---|---|---|---|---|
| H1 | **Claude Haiku 5.5 tiene cuota 0** de tokens por minuto (cross-region y global). Sonnet 5.5 y Opus 5.5 también tienen 0. | M | Service Quotas `bedrock`, 2026-11-12 | El modelo de las actividades 5 a 8 no puede ser Haiku 5.5 hasta que haya cuota. |
| H2 | **Haiku 4.5 tiene cuota**: 5 000 000 tokens por minuto cross-region (y global), 50 solicitudes por minuto cross-region. | M | Service Quotas `bedrock`, 2026-11-12 | **Propuesta de modelo para la semana 19: Haiku 4.5 vía el inference profile `us.`**, que es el que tuvo cuota en la semana 12. Decisión de Manuel. |
| H3 | Plan de la cuenta: **PAID, ACTIVE** (no Free Tier). | M | Free Tier API `get_account_plan_state`, 2026-11-12 | Los servicios permitidos y el costo corren contra créditos o facturación normal. |
| H4 | Gasto del mes (2026-11-01 a 11-12): **-0.0000000012 USD**, es decir $0 neto (créditos). | M | Cost Explorer `get_cost_and_usage`, 1 llamada, 2026-11-12 | Línea base del costo real: $0 hasta hoy. |
| H5 | Créditos: **US$142 de saldo disponible de introducción, sin vencimiento**. La API no los da. | D (pantalla de Billing, dato de Manuel, 2026-11-13) | Captura de Billing: Manuel | Cotizar contra créditos: 142 USD sin fecha límite. |
| H6 | AgentCore Gateway, Runtime, Policy y Bedrock Agents **responden 200 en la región**. | M | `list_gateways`, `list_agent_runtimes`, `list_policy_engines`, `list_agents` 2026-11-12 | Las capacidades existen en `us-east-1`. |
| H7 | **CDK L2 de AgentCore**: existe `@aws-cdk/aws-bedrock-agentcore-alpha` en 2.276.0-alpha.0 (alpha, no estable). | M | npm registry, 2026-11-12 | La actividad 2 decide entre el L2 alpha, L1 o Terraform. |
| H8 | **Terraform**: provider `hashicorp/aws` 6.73.0 publicado. No se verificó si existen `aws_bedrockagentcore_*` ni `aws_bedrock_guardrail`. | M (provider) / N (recursos) | Terraform Registry, 2026-11-11 | Se verifica en la actividad 2 con la documentación del provider. |
| H9 | Titan Text Embeddings V2: 300 000 tokens por minuto y 600 solicitudes por minuto on-demand. | M | Service Quotas `bedrock`, 2026-11-12 | El embedding de la KB queda cubierto por cuota. |
| H10 | Modelo de Haiku 4.5 y de Haiku 5.5 **no aparecen en la Price List** de AmazonBedrock. | D | https://aws.amazon.com/bedrock/pricing/ | El precio por token del modelo elegido se confirma en esa página antes de la actividad 2. |

## 2. Matriz de capacidades (Bedrock us-east-1)

| Capacidad | Estado | Dato | Fuente | Fecha | Marca |
|---|---|---|---|---|---|
| Modelos Claude accesibles (listados) | Disponible | 16 modelos Anthropic, incluidos `claude-haiku-4-5-20251001-v1:0` y `claude-haiku-5-5` | `list_foundation_models` | 2026-11-12 | M |
| Embeddings accesibles | Disponible | `amazon.titan-embed-text-v2:0`, Cohere y Nova | `list_foundation_models` | 2026-11-12 | M |
| Acceso habilitado por modelo (`get-foundation-model-availability`) | No verificado | La lista muestra el modelo, pero no el acceso concreto | | | N |
| Inference profiles | Disponible | `us.` y `global.` para Haiku 4.5, Haiku 5.5, Sonnet 5.5 y Titan | `list_inference_profiles` | 2026-11-12 | M |
| Cuota Haiku 5.5, tokens por minuto (cross-region / global) | **0** / **0** | Ver H1 | Service Quotas | 2026-11-12 | M |
| Cuota Haiku 5.5, solicitudes por minuto | No encontrada en la lista de cuotas | Búsqueda sin coincidencia | Service Quotas | 2026-11-12 | N |
| Cuota Haiku 4.5, tokens por minuto (cross-region / global) | 5 000 000 / 5 000 000 | Ver H2 | Service Quotas | 2026-11-12 | M |
| Cuota Haiku 4.5, solicitudes por minuto (cross-region / global) | 50 / 50 | Ver H2 | Service Quotas | 2026-11-12 | M |
| Cuota Titan Text Embeddings V2 | 300 000 tokens/min; 600 solicitudes/min | Ver H9 | Service Quotas | 2026-11-12 | M |
| Guardrails | Disponible | `list_guardrails` responde 200 | Bedrock | 2026-11-12 | M |
| Knowledge Bases con S3 Vectors | Disponible | `list_knowledge_bases` responde 200 (S3 Vectors se mide por separado en la matriz de precios) | Bedrock Agent | 2026-11-12 | M |
| Prompt Management | Disponible | `list_prompts` responde 200 | Bedrock Agent | 2026-11-12 | M |
| Evaluation jobs | Disponible | `list_evaluation_jobs` responde 200 | Bedrock | 2026-11-12 | M |
| Bedrock Agents | Disponible | `list_agents` responde 200 | Bedrock Agent | 2026-11-12 | M |
| AgentCore Gateway | Disponible | `list_gateways` responde 200 | AgentCore control | 2026-11-12 | M |
| AgentCore Runtime | Disponible | `list_agent_runtimes` responde 200 | AgentCore control | 2026-11-12 | M |
| AgentCore Policy | Disponible | `list_policy_engines` responde 200 | AgentCore control | 2026-11-12 | M |

## 3. Precios (Price List API, us-east-1)

Each row carries its catalog ID (usagetype) and its SKU. Marks: M from the Price List; D when the item is not in the catalog (official link); N when not verified. "Free tier o créditos" is documented, not measured, in every row.

| Artículo | Precio USD | Unidad | Id de catálogo | Marca | Free tier o créditos |
|---|---|---|---|---|---|
| Lambda arm64, solicitudes | — | por solicitud | — | D https://aws.amazon.com/lambda/pricing/ (la solicitud ARM estándar no aparece en el catálogo) | N (free tier de Lambda no verificado en esta actividad) |
| Lambda arm64, GB-segundo (nivel 3, tarifa más baja) | 0.0000106667 | GB-s | `Lambda-GB-Second-ARM` | M | N (free tier de Lambda no verificado en esta actividad) |
| Step Functions Standard, transiciones | — | por transición | — | D https://aws.amazon.com/step-functions/pricing/ (sin código en la Price List) | N (free tier de Step Functions no verificado en esta actividad) |
| API Gateway HTTP API, solicitudes (más de 300 M) | 0.0000009000 | por solicitud | `USE1-ApiGatewayHttpRequest` | M | N (free tier de API Gateway no verificado en esta actividad) |
| Cognito, MAU (tier Essentials, tier 1) | 0.0150 | MAU | `USE1-CognitoEssentialsMAU` | M | N (free tier de MAU no verificado en esta actividad) |
| RDS PostgreSQL db.t4g.micro, Single-AZ | 0.0160 | hora | `InstanceUsage:db.t4g.micro` | M | N (free tier de RDS no verificado en esta actividad) |
| RDS gp3, almacenamiento PostgreSQL | 0.1150 | GB-mes | `RDS:GP3-Storage` | M | N (free tier de RDS no verificado en esta actividad) |
| Aurora Serverless v2, ACU-hora PostgreSQL | 0.1200 | ACU-hora | `Aurora:ServerlessV2Usage` | M | — |
| Aurora Serverless v2, escala a 0 ACU | — | | — | D https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.html | — |
| Endpoint de VPC de interfaz, por AZ-hora | — | hora | — | D https://aws.amazon.com/privatelink/pricing/ (no está en AmazonVPC de la Price List) | — |
| Endpoint de VPC de interfaz, por GB | — | GB | — | D https://aws.amazon.com/privatelink/pricing/ | — |
| IPv4 pública en uso | 0.0050 | hora | `USE1-PublicIPv4:InUseAddress` | M | — |
| KMS, llave administrada por el cliente | 1.0000 | llave-mes | `us-east-1-KMS-Keys` | M | N (free tier de KMS no verificado en esta actividad) |
| KMS, llave pendiente de borrado | — | | — | D https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys.html (cobro por confirmar en la doc) | — |
| CloudWatch Logs, ingesta (clase Standard) | 0.5000 | GB | `DataProcessing-Bytes` | M | N (free tier de CloudWatch no verificado en esta actividad) |
| CloudWatch Logs, almacenamiento | 0.0300 | GB-mes | `TimedStorage-ByteHrs` | M | N (free tier de CloudWatch no verificado en esta actividad) |
| S3 Vectors, almacenamiento | 0.0600 | GB-mes | `Vectors-TimedStorage-ByteHrs` | M | N (free tier de S3 no verificado en esta actividad) |
| Modelo Claude elegido (Haiku 4.5) | — | por 1K tokens | — | D https://aws.amazon.com/bedrock/pricing/ (no está en la Price List de AmazonBedrock) | Créditos |
| Titan Text Embeddings V2, tokens de entrada | 0.0000200000 | por 1K tokens | `USE1-TitanEmbeddingV2-Text-input-tokens` | M | Créditos |
| AgentCore Gateway, invocaciones | 0.0000050000 | por invocación | `USE1-Gateway:Consumption-based:API-Invocations` | M | — |
| AgentCore Runtime, instancia c5.large | 0.0102 | hora | `Runtime:Instance-based:c5.large:Management-Hours` | M | — |
| AgentCore Policy, precio | — | | — | N (sin coincidencia en la búsqueda; el API responde 200) | — |

**Resultado de la Price List:** 14 M, 7 D, 1 N (de 22 artículos).

## 4. Herramientas (instalada frente a última publicada)

| Herramienta | Instalada | Última publicada | Fecha de consulta | Marca |
|---|---|---|---|---|
| AWS CLI | 2.37.4 | pendiente de comparar con la última | 2026-11-12 | M (instalada) |
| Node | v24.19.0 | v26.13.1 (LTS publicada 2026-11-10) | 2026-11-12 | M |
| npm | 11.17.0 | pendiente | 2026-11-12 | M (instalada) |
| uv | 0.13.1 | pendiente | 2026-11-12 | M (instalada) |
| CDK CLI (`aws-cdk`) | no instalada | 2.1148.1 (npm) | 2026-11-12 | M |
| `aws-cdk-lib` | 2.276.0 publicada; en el grupo del repo aún no se fija | 2.276.0 (npm y PyPI) | 2026-11-12 | M |
| `constructs` | 10.8.1 | 10.8.1 (npm y PyPI) | 2026-11-12 | M |
| `cdk-nag` | 3.0.2 | 3.0.2 (npm y PyPI) | 2026-11-12 | M |
| Terraform CLI | no instalada | — | | N |
| Provider AWS de Terraform | — | 6.73.0 (2026-11-11) | 2026-11-12 | M |
| checkov | no instalada | 3.4.4 (2026-11-11) | 2026-11-12 | M |

Las versiones publicadas se consultaron a los registros (npm, PyPI, Terraform Registry, GitHub releases, nodejs.org). Ninguna se tomó de un listado de terceros.

## 5. Repo

| Regla | Estado | Marca |
|---|---|---|
| `semana-19/**` en las rutas del check `regresion` | Verificado en el PR 144 (mergeado) | M |

## 6. Inventario (debe reportar 0)

Resultado: **`"total": 0`, `"quedan": "nada"`**, sin categorías no medidas. 22 categorías consultadas (CloudFormation, IAM, KMS, VPC, endpoints, Lambda, Step Functions, APIs HTTP y REST, Cognito, RDS, S3, S3 Vectors, KB, Guardrails, Prompts, AgentCore, log groups y Tagging API).

Nota: la identidad del operador es la misma que la del admin (`manuel-admin`). Ver la sección 7.

## 7. Hallazgos abiertos

- **Operador y admin son la misma identidad IAM.** `semana19-operador` resuelve al usuario `manuel-admin`. El plan pide separarlos. Esto queda como excepción registrada hasta que se cree un rol de solo lectura.
- **Llaves de acceso en el perfil `default`:** el plan prohíbe llaves; el perfil las tiene. Lo decide Manuel.
- **Créditos:** no medidos (D, pendiente de la pantalla de Billing).
- **Servicios permitidos por el plan `PAID`:** N, no medido.
- **La llamada a `aws-cdk-lib` en Python** se fija en la actividad 2 (candidata 2.275.0 en `versiones.json`; la última es 2.276.0).
