# Activity 1: verified prices, fixed costs and the week's estimate

Prices come from each provider's official price catalog, queried on 2026-10-28 with `infra/precios.py`:
- **AWS:** Price List API, region us-east-1.
- **Google Cloud:** Cloud Billing Catalog API.

The filtered catalog is in [`precios_catalogo_2026-10-28.csv`](precios_catalogo_2026-10-28.csv) (452 rows; source, service, SKU or usage type, unit and USD price). Prices are list prices in USD, before taxes and credits.

## AWS (us-east-1)

| Item | Price | Catalog id |
|---|---|---|
| **Bedrock Knowledge Bases (vector store on S3 Vectors)** | No charge for the KB or for `Retrieve` itself; you pay for embeddings, the vector store and the model in `RetrieveAndGenerate` | (no KB SKU for this mode) |
| S3 Vectors storage | $0.06 per GB-month | `Vectors-TimedStorage-ByteHrs` |
| S3 Vectors upload | $0.20 per GB | `Vectors-Put-Bytes` |
| S3 Vectors query API | $0.055 per 1,000 requests (tier 1) | `Vectors-Request-Tier1` |
| S3 Vectors query data processed | $0.0000039 per GB (tier 1); returned bytes $0.01 per GB | `Vectors-Query-ProcessedBytes-Tier1`, `Vectors-Query-Returned-Bytes` |
| S3 Standard (document bucket) | $0.023 per GB-month; $0.005 per 1,000 PUT; $0.0004 per 1,000 GET | `TimedStorage-ByteHrs`, `Requests-Tier1/2` |
| Titan Text Embeddings V2 | $0.02 per 1M input tokens | `USE1-TitanEmbeddingV2-Text-input-tokens` |
| Cohere Embed Multilingual v3 | $0.10 per 1M input tokens | Marketplace `USE1_InputTokenCount` (Embed Multilingual) |
| Cohere Rerank 3.5 (optional) | $0.002 per search unit | Marketplace `USE1_search_units` |
| **Claude Haiku 4.5** (model for `RetrieveAndGenerate`) | $1.10 input / $5.50 output per 1M tokens (regional, `us.` profile); $1.00 / $5.00 (global profile) | Marketplace `USE1_InputTokenCount` / `USE1_OutputTokenCount` (Claude Haiku 4.5) |
| Claude Haiku 5.5 (not usable yet: account quota is 0) | $0.11 / $0.55 regional; $0.10 / $0.50 global | Marketplace `USE1_input_tokens_standard` (Claude Haiku 5.5) |
| Bedrock Data Automation parsing (optional, for PDF and images) | $0.01 per page; $0.003 per image (standard output) | `USE1-DataAutomation-Standard-*` |

Not used: the AgentCore knowledge base (consumption-based) lists $0.001 per query and $5.00 per GB-month (`AmazonBedrockAgentCore`). It is a different product from Bedrock Knowledge Bases on S3 Vectors. OpenSearch Serverless is not used either, because it charges for minimum capacity per hour even without queries.

## Google Cloud (Vertex AI Search, now "Agent Search" in AI Applications)

| Item | Price | Catalog SKU |
|---|---|---|
| Search API, Standard | first 10,000 requests per month free, then $1.50 per 1,000 | `BADA-EE26-7BDA` |
| Search API, Enterprise | first 10,000 requests per month free, then $4.00 per 1,000 | `93D6-7280-CF05` |
| LLM add-on (generative answers) | $4.00 per 1,000 | `151B-D7A2-B5B5` |
| Data index | first 10 GiB-month free, then $5.00 per GiB-month | `BC7D-6A97-90F8` |
| Layout parser (parsing and chunking) | $0.01 per page | `5F3F-A230-7FDA` |
| OCR | $0.0015 per page | `8E95-B0FA-9047` |
| Ranking API (optional) | $0.001 per request | `EE89-3EE8-2541` |
| Cloud Storage, Standard, US multi-region | $0.026 per GiB-month | Cloud Storage catalog |
| **Configurable pricing (subscription): do not use** | query units $6 per QPM-month, with a minimum of 1,000 QPM and 50 GB | `7FD8-6D78-0DD5`, `713D-043A-F4CA` |

The pricing page (checked on 2026-10-27) confirms the same figures: 10,000 queries per month at no cost, 10 GiB of index free, and 1,000 free OCR pages per month.

## Fixed monthly cost

| Option | Fixed monthly cost for this corpus | Why |
|---|---|---|
| In-house pipeline (pgvector local + bge-m3) | $0 in the cloud | Runs on the Mac |
| Bedrock KB + S3 Vectors | **≈ $0.00** | Under 1 MB of vectors and documents: S3 Vectors and S3 Standard round to fractions of a cent per month. No minimum capacity |
| Vertex AI Search (pay as you go) | **$0** | Index inside the free 10 GiB; no subscription |

The fixed cost of all three options is effectively zero for a 30-document corpus. The difference between them is the cost per query and the cost of ingestion. Activity 7 measures both.

## Week 12 estimate (to authorize before each run)

Corpus: 30 documents, about 50 pages for parsing. Suites from week 11: 130 retrieval queries and 150 generation questions per configuration.

| Item | Estimate |
|---|---|
| Bedrock: ingestion embeddings (two ingestion modes, re-ingestions) | < $0.01 |
| Bedrock: S3 Vectors storage, uploads and queries | < $0.05 |
| Bedrock: `RetrieveAndGenerate` with Haiku 4.5, 150 questions per run, ≈ 2,000 input and 200 output tokens each | ≈ $0.50 per run; 2 runs ≈ $1.00 |
| Bedrock Data Automation parsing (optional, about 10 PDF and image pages) | < $0.15 |
| Vertex AI Search: queries (under 10,000 in the month) | $0 |
| Vertex AI Search: layout parser and OCR, two ingestions of about 50 pages | ≈ $1.00 |
| Anthropic API (common Haiku 5.5 generator and judge, about 6 configurations at ≈ $0.16 each) | ≈ $1.00 |
| **Total for the week** | **≈ $3 to $4** |

This is below both budgets.

## Budgets and cost controls

| Cloud | Budget | Alerts |
|---|---|---|
| AWS (account <AWS_ACCOUNT_ID>) | `semana12`: $10 per month, account-wide | Email at 50, 90 and 100% actual, and 100% forecasted |
| AWS (existing) | `My Zero-Spend Budget` and `aip-lab-cero` at $1 | Fire on the first cent |
| Google Cloud (`ejemplo1-9xub`) | `semana12`: 200 MXN, about $10 USD; scoped to the project only. The billing account bills in MXN | Email to billing admins at 50, 90 and 100% actual, and 100% forecasted |

- The AWS budget is account-wide because a tag-based filter needs the cost allocation tag to be activated, and that takes 24 hours. Every week 12 resource is still tagged `proyecto=semana12` and named with the `semana12` prefix.
- **Deletion is ready before anything billable exists.** `infra/aws_borrar.sh` and `infra/gcp_borrar.sh` simulate by default and delete with `--confirmar`. Both were run in simulation and found exactly the resources created in this activity. Activity 10 runs them for real and then checks the bill.
