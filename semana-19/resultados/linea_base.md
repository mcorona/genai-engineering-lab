# Week 19, activity 1: baseline of the account, the services and the prices

Measured on 2026-11-12 with `linea_base/verificar.py` (operator identity, read-only) and `infra/inventario.py`. Raw results: `resultados/linea_base_mac.json` and `resultados/inventario_mac.json`. Account IDs, ARNs and home paths are removed from both files.

Marks: **M** measured by a run (date recorded), **D** documented (official link), **N** not verified (the reason is given).

Cost of the activity: **one** Cost Explorer call ($0.01 per call, authorized by Manuel), no model invoked, no resource created.

## 1. Findings that change the plan

| # | Finding | Mark | Source and date | Effect on the plan |
|---|---|---|---|---|
| H1 | **Claude Haiku 5.5 has a quota of 0** tokens per minute (cross-region and global). Sonnet 5.5 and Opus 5.5 also have 0. | M | Service Quotas `bedrock`, 2026-11-12 | The model of activities 5 to 8 cannot be Haiku 5.5 until there is quota. |
| H2 | **Haiku 4.5 has quota**: 5,000,000 tokens per minute cross-region (and global), 50 requests per minute cross-region. | M | Service Quotas `bedrock`, 2026-11-12 | **Proposed model for week 19: Haiku 4.5 through the `us.` inference profile**, the one that had quota in week 12. Manuel's decision. |
| H3 | Account plan: **PAID, ACTIVE** (not Free Tier). | M | Free Tier API `get_account_plan_state`, 2026-11-12 | The allowed services and the cost run against credits or normal billing. |
| H4 | Spend this month (2026-11-01 to 11-12): **-0.0000000012 USD**, that is $0 net (credits). | M | Cost Explorer `get_cost_and_usage`, 1 call, 2026-11-12 | Real-cost baseline: $0 so far. |
| H5 | Credits: **US$142 of available introductory balance, with no expiry**. The API does not report them. | D (Billing screen, given by Manuel, 2026-11-13) | Billing screenshot: Manuel | Quote against credits: 142 USD with no deadline. |
| H6 | AgentCore Gateway, Runtime, Policy and Bedrock Agents **answer 200 in the region**. | M | `list_gateways`, `list_agent_runtimes`, `list_policy_engines`, `list_agents`, 2026-11-12 | The capabilities exist in `us-east-1`. |
| H7 | **AgentCore CDK L2**: `@aws-cdk/aws-bedrock-agentcore-alpha` exists at 2.276.0-alpha.0 (alpha, not stable). | M | npm registry, 2026-11-12 | Activity 2 decides between the alpha L2, L1 or Terraform. |
| H8 | **Terraform**: provider `hashicorp/aws` 6.73.0 published. Whether `aws_bedrockagentcore_*` and `aws_bedrock_guardrail` exist was not checked. | M (provider) / N (resources) | Terraform Registry, 2026-11-11 | Checked in activity 2 with the provider documentation. |
| H9 | Titan Text Embeddings V2: 300,000 tokens per minute and 600 requests per minute on demand. | M | Service Quotas `bedrock`, 2026-11-12 | The KB embedding is covered by quota. |
| H10 | The Haiku 4.5 and Haiku 5.5 models **are not in the AmazonBedrock Price List**. | D | https://aws.amazon.com/bedrock/pricing/ | The per-token price of the chosen model is confirmed on that page before activity 2. |

## 2. Capability matrix (Bedrock us-east-1)

| Capability | Status | Detail | Source | Date | Mark |
|---|---|---|---|---|---|
| Accessible Claude models (listed) | Available | 16 Anthropic models, including `claude-haiku-4-5-20251001-v1:0` and `claude-haiku-5-5` | `list_foundation_models` | 2026-11-12 | M |
| Accessible embeddings | Available | `amazon.titan-embed-text-v2:0`, Cohere and Nova | `list_foundation_models` | 2026-11-12 | M |
| Access enabled per model (`get-foundation-model-availability`) | Not verified | The list shows the model, not the actual access | | | N |
| Inference profiles | Available | `us.` and `global.` for Haiku 4.5, Haiku 5.5, Sonnet 5.5 and Titan | `list_inference_profiles` | 2026-11-12 | M |
| Haiku 5.5 quota, tokens per minute (cross-region / global) | **0** / **0** | See H1 | Service Quotas | 2026-11-12 | M |
| Haiku 5.5 quota, requests per minute | Not found in the quota list | Search with no match | Service Quotas | 2026-11-12 | N |
| Haiku 4.5 quota, tokens per minute (cross-region / global) | 5,000,000 / 5,000,000 | See H2 | Service Quotas | 2026-11-12 | M |
| Haiku 4.5 quota, requests per minute (cross-region / global) | 50 / 50 | See H2 | Service Quotas | 2026-11-12 | M |
| Titan Text Embeddings V2 quota | 300,000 tokens/min; 600 requests/min | See H9 | Service Quotas | 2026-11-12 | M |
| Guardrails | Available | `list_guardrails` answers 200 | Bedrock | 2026-11-12 | M |
| Knowledge Bases with S3 Vectors | Available | `list_knowledge_bases` answers 200 (S3 Vectors is measured separately in the price matrix) | Bedrock Agent | 2026-11-12 | M |
| Prompt Management | Available | `list_prompts` answers 200 | Bedrock Agent | 2026-11-12 | M |
| Evaluation jobs | Available | `list_evaluation_jobs` answers 200 | Bedrock | 2026-11-12 | M |
| Bedrock Agents | Available | `list_agents` answers 200 | Bedrock Agent | 2026-11-12 | M |
| AgentCore Gateway | Available | `list_gateways` answers 200 | AgentCore control | 2026-11-12 | M |
| AgentCore Runtime | Available | `list_agent_runtimes` answers 200 | AgentCore control | 2026-11-12 | M |
| AgentCore Policy | Available | `list_policy_engines` answers 200 | AgentCore control | 2026-11-12 | M |

## 3. Prices (Price List API, us-east-1)

Each row carries its catalog ID (usagetype). Marks: M from the Price List; D when the item is not in the catalog (official link); N when not verified. "Free tier or credits" is documented, not measured, in every row.

| Item | Price USD | Unit | Catalog ID | Mark | Free tier or credits |
|---|---|---|---|---|---|
| Lambda arm64, requests | — | per request | — | D https://aws.amazon.com/lambda/pricing/ (the standard ARM request is not in the catalog) | N (Lambda free tier not verified in this activity) |
| Lambda arm64, GB-second (tier 3, the lowest rate) | 0.0000106667 | GB-s | `Lambda-GB-Second-ARM` | M | N (Lambda free tier not verified in this activity) |
| Step Functions Standard, transitions | — | per transition | — | D https://aws.amazon.com/step-functions/pricing/ (no service code in the Price List) | N (Step Functions free tier not verified in this activity) |
| API Gateway HTTP API, requests (over 300 M) | 0.0000009000 | per request | `USE1-ApiGatewayHttpRequest` | M | N (API Gateway free tier not verified in this activity) |
| Cognito, MAU (Essentials tier, tier 1) | 0.0150 | MAU | `USE1-CognitoEssentialsMAU` | M | N (MAU free tier not verified in this activity) |
| RDS PostgreSQL db.t4g.micro, Single-AZ | 0.0160 | hour | `InstanceUsage:db.t4g.micro` | M | N (RDS free tier not verified in this activity) |
| RDS gp3, PostgreSQL storage | 0.1150 | GB-month | `RDS:GP3-Storage` | M | N (RDS free tier not verified in this activity) |
| Aurora Serverless v2, PostgreSQL ACU-hour | 0.1200 | ACU-hour | `Aurora:ServerlessV2Usage` | M | — |
| Aurora Serverless v2, scaling to 0 ACU | — | | — | D https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.html | — |
| Interface VPC endpoint, per AZ-hour | — | hour | — | D https://aws.amazon.com/privatelink/pricing/ (not under AmazonVPC in the Price List) | — |
| Interface VPC endpoint, per GB | — | GB | — | D https://aws.amazon.com/privatelink/pricing/ | — |
| Public IPv4 in use | 0.0050 | hour | `USE1-PublicIPv4:InUseAddress` | M | — |
| KMS, customer managed key | 1.0000 | key-month | `us-east-1-KMS-Keys` | M | N (KMS free tier not verified in this activity) |
| KMS, key pending deletion | — | | — | D https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys.html (charge to be confirmed in the docs) | — |
| CloudWatch Logs, ingestion (Standard class) | 0.5000 | GB | `DataProcessing-Bytes` | M | N (CloudWatch free tier not verified in this activity) |
| CloudWatch Logs, storage | 0.0300 | GB-month | `TimedStorage-ByteHrs` | M | N (CloudWatch free tier not verified in this activity) |
| S3 Vectors, storage | 0.0600 | GB-month | `Vectors-TimedStorage-ByteHrs` | M | N (S3 free tier not verified in this activity) |
| Chosen Claude model (Haiku 4.5) | — | per 1K tokens | — | D https://aws.amazon.com/bedrock/pricing/ (not in the AmazonBedrock Price List) | Credits |
| Titan Text Embeddings V2, input tokens | 0.0000200000 | per 1K tokens | `USE1-TitanEmbeddingV2-Text-input-tokens` | M | Credits |
| AgentCore Gateway, invocations | 0.0000050000 | per invocation | `USE1-Gateway:Consumption-based:API-Invocations` | M | — |
| AgentCore Runtime, c5.large instance | 0.0102 | hour | `Runtime:Instance-based:c5.large:Management-Hours` | M | — |
| AgentCore Policy, price | — | | — | N (no match in the search; the API answers 200) | — |

**Price List result:** 14 M, 7 D, 1 N (of 22 items).

## 4. Tools (installed against latest published)

| Tool | Installed | Latest published | Date checked | Mark |
|---|---|---|---|---|
| AWS CLI | 2.37.4 | to be compared with the latest | 2026-11-12 | M (installed) |
| Node | v24.19.0 | v26.13.1 (LTS published 2026-11-10) | 2026-11-12 | M |
| npm | 11.17.0 | pending | 2026-11-12 | M (installed) |
| uv | 0.13.1 | pending | 2026-11-12 | M (installed) |
| CDK CLI (`aws-cdk`) | not installed | 2.1148.1 (npm) | 2026-11-12 | M |
| `aws-cdk-lib` | 2.276.0 published; not yet pinned in the repo's group | 2.276.0 (npm and PyPI) | 2026-11-12 | M |
| `constructs` | 10.8.1 | 10.8.1 (npm and PyPI) | 2026-11-12 | M |
| `cdk-nag` | 3.0.2 | 3.0.2 (npm and PyPI) | 2026-11-12 | M |
| Terraform CLI | not installed | — | | N |
| Terraform AWS provider | — | 6.73.0 (2026-11-11) | 2026-11-12 | M |
| checkov | not installed | 3.4.4 (2026-11-11) | 2026-11-12 | M |

The published versions were read from the registries (npm, PyPI, Terraform Registry, GitHub releases, nodejs.org). None was taken from a third-party listing.

## 5. Repository

| Rule | Status | Mark |
|---|---|---|
| `semana-19/**` in the paths of the `regresion` check | Verified in PR 144 (merged) | M |

## 6. Inventory (must report 0)

Result: **`"total": 0`, `"quedan": "nada"`**, with no unmeasured category. 22 categories checked (CloudFormation, IAM, KMS, VPC, endpoints, Lambda, Step Functions, HTTP and REST APIs, Cognito, RDS, S3, S3 Vectors, KB, Guardrails, Prompts, AgentCore, log groups and the Tagging API).

Note: the operator identity is the same as the admin's (`manuel-admin`). See section 7.

## 7. Open findings

- **Operator and admin are the same IAM identity.** `semana19-operador` resolves to the `manuel-admin` user. The plan asks for them to be separate. This stays a recorded exception until a read-only role is created.
- **Access keys in the `default` profile:** the plan forbids keys; the profile has them. Manuel decides.
- **Credits:** not measured (D, pending the Billing screen).
- **Services allowed by the `PAID` plan:** N, not measured.
- **The Python `aws-cdk-lib` pin** is set in activity 2 (candidate 2.275.0 in `versiones.json`; the latest is 2.276.0).

## 8. Closing the pending items (2026-11-13)

Free, read-only queries made after the main measurement. Each row says what the earlier N was and what resolves it.

| # | Item (earlier N or unverified) | Result | Mark | Source and date |
|---|---|---|---|---|
| 1 | Access per model (`get-foundation-model-availability`) | Haiku 4.5 (`anthropic.claude-haiku-4-5-20251001-v1:0`), Haiku 5.5 (`anthropic.claude-haiku-5-5`) and Titan Text Embeddings V2 (`amazon.titan-embed-text-v2:0`): agreement, region, entitlement and authorization all **AVAILABLE / AUTHORIZED** | M | Bedrock `get_foundation_model_availability`, 2026-11-13 |
| 2 | Haiku 5.5 quota in requests per minute | Still not in the Service Quotas list (the tokens one is: 0). Stays N | N | Service Quotas `list_service_quotas`, 2026-11-13 |
| 3 | AgentCore Policy price | Authorization: **0.000025 USD per invocation** (`USE1-Policy:Consumption-based:Authorization-API-Invocations`). Generation: **130 USD per 1M input tokens** (`USE1-Policy:Consumption-based:Generation-Input-Tokens`) | M | Price List `AmazonBedrockAgentCore`, 2026-11-13 |
| 4 | Terraform resources: `aws_bedrockagentcore_*` and `aws_bedrock_guardrail` | They exist in the provider: `bedrockagentcore_agent_runtime`, `bedrockagentcore_gateway`, `bedrockagentcore_evaluator` and others; `bedrock_guardrail`, `bedrock_guardrail_version` and `bedrock_guardrail_resource_policy` | M | Repository `hashicorp/terraform-provider-aws`, `website/docs/r`, 2026-11-13 |
| 5 | Installed versions against the latest published | AWS CLI: 2.37.4 installed against **2.40.2** (the repo's latest tag). uv: 0.13.1 against **0.13.8** (PyPI). npm: 11.17.0 against **12.2.2** (npm registry). Node: v24.19.0 against LTS **v26.13.1** | M | `git ls-remote` of the aws-cli repo, PyPI, npm registry and nodejs.org, 2026-11-13 |
| 6 | Free tier per row (earlier N) | Lambda, Step Functions, Cognito, KMS and CloudWatch have a permanent free tier with monthly limits. API Gateway and RDS appear in the credits plan. Specific limits: Lambda 1 M requests/month; Step Functions 4,000 transitions/month; Cognito 50,000 MAU; KMS 20,000 requests/month; CloudWatch 5 GB of ingestion/month; RDS: db.t3.micro and db.t4g.micro instances in the free credits plan | D | https://aws.amazon.com/free/serverless/, https://aws.amazon.com/free/security/, https://aws.amazon.com/rds/free/ (official sources, 2026-11-13). The limits are confirmed in the account: the free tier documentation differs between new and older accounts |
| 7 | Services the plan allows | The account is **PAID** (Free Tier API). A paid plan is not limited by the free plan's service list; the exact list is confirmed in the Free Tier console | D | Free Tier API `get_account_plan_state` (M, 2026-11-12) and https://docs.aws.amazon.com/accounts/latest/reference/bcm-lite-free-tier.html |

**What stays N after this closing:** the Haiku 5.5 requests quota (row 2). Checking it directly in the Service Quotas console is the only way to confirm it.

## 9. Update 2026-11-13: the operator's recorded exception and the quota status

Measurement repeated with the read-only profile `semana19-lectura` (a role with the managed policy `ReadOnlyAccess`, created for the operator). It replaces the `semana19-operador` profile, which had the admin's identity.

| Topic | Status | Mark | Source and date |
|---|---|---|---|
| Operator identity | The `semana19-lectura` profile assumes the read-only role; the identity is no longer `manuel-admin`. Attached policy: `ReadOnlyAccess`. | M | `sts get-caller-identity` and `iam list-attached-role-policies` (admin), 2026-11-13 |
| Baseline | Prices: 15 M, 7 D, 0 N. PAID plan and spend this month measured (the spend comes from the authorized Cost Explorer call, not repeated). | M | `linea_base/verificar.py` with `semana19-lectura`, 2026-11-13 |
| Inventory | **1 resource**: the `semana19-lectura` role. Result `"quedan": "revisar"`. | M | `infra/inventario.py` with `semana19-lectura`, 2026-11-13 |
| Haiku 5.5 quota, tokens per minute (cross-region) | Applied value: 0. Increase request to 10,500,000, status **CASE_OPENED** (ID `6670b8faf0f14f63bd40d5afe73363fcI74dzeGW`). | M | Service Quotas, 2026-11-13 |
| Haiku 5.5 quota, tokens per minute (global) | Applied value: 0. Increase request to 10,500,000, status **CASE_OPENED** (ID `f17c261db70949c18f08491b231e66f5nF5XFLwF`). | M | Service Quotas, 2026-11-13 |

**Recorded inventory exception.** The `semana19-lectura` role is the only resource left. It is kept as an inventory exception, like the `semana19` budget and the KMS key pending deletion in the later activities. Reason: it is the read-only operator the plan asks for. It has no cost. Its teardown is done when the week closes, with `destruir.sh` and the exception declared.

**What stays open:** the Haiku 5.5 quota is updated when AWS answers (APPROVED or DENIED). The access keys of the `default` profile are still pending Manuel's decision.

## 10. Closing (2026-11-23, week 19 closing review)

Free, read-only queries with `semana19-lectura`.

| Topic | Status | Mark | Source and date |
|---|---|---|---|
| Haiku 5.5 quota, tokens per minute (cross-region and global) | The four increase requests (two on 2026-11-12, two on 2026-11-14) are **CASE_CLOSED**. The applied value is still **0** in both. Week 19 ran on Haiku 4.5, as decided. | M | Service Quotas `list_requested_service_quota_change_history` and `list_service_quotas`, 2026-11-23 |
| Haiku 4.5 quota | Unchanged: 5,000,000 tokens and 50 requests per minute, cross-region and global. | M | Service Quotas `list_service_quotas`, 2026-11-23 |
| The `semana19-lectura` role | **Kept**, not torn down: week 20 uses it as its read-only operator (`semana-20/Fas5Sema20.md`). It is the declared exception of the final inventory (`resultados/inventario_final.json`). | M | `infra/inventario.py`, 2026-11-23 |
| Access keys in the `default` profile | **Still present** (a `default` section with an access key ID in `~/.aws/credentials`; only the key name was read, never the values). This is Manuel's decision, carried to week 20. | M | local file check, 2026-11-23 |
