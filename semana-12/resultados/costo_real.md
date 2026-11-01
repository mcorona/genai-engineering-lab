# Week 12: real cost from the bills

Read on 2026-10-31, 48 hours after every resource was deleted (2026-10-29). Sources: AWS Cost Explorer through [`infra/costo_real.sh`](../infra/costo_real.sh) (one query, $0.01) and the billing consoles of Google Cloud, Anthropic and OpenAI.

## Summary

| Provider | Week 12 usage | Estimate ([`costos_fijos.md`](costos_fijos.md)) | Paid |
|---|---|---|---|
| AWS | **$1.5034** gross usage | ≈ $1.21 | **$0**: promotional credits covered all usage (−$1.5235 against $1.5235) |
| Google Cloud (project `GenAI Semana 12`) | **MXN 16.64** (Vertex AI Search MXN 16.58, Cloud Storage MXN 0.06), about $0.9 | ≈ $1.00 | MXN 16.64, on the October invoice |
| Anthropic API | **at most $4.94** (see below) | ≈ $1.00 | billed to the API balance |
| OpenAI | **$0.00** (October total: $0.00) | not estimated | $0 |
| **Total** | **≈ $3.3 to $7.4** | ≈ $3 to $4 | |

## AWS by service (gross, before credits)

| Service | USD |
|---|---|
| Claude Haiku 4.5 (Bedrock edition), `RetrieveAndGenerate` | 1.3986 |
| Amazon Bedrock (knowledge bases, S3 Vectors queries) | 0.0800 |
| Amazon S3 | 0.0180 |
| Cohere Embed Multilingual v3 (Bedrock edition) | 0.0068 |
| **Week 12 services** | **1.5034** |
| AWS Cost Explorer (the two cost queries, not week 12) | 0.0200 |

By day: $0.47 on Oct 28 and $1.05 on Oct 29; after the deletion, $0.0002 a day (the Cost Explorer queries). Nothing billable was left running.

Against the estimate: 24 % higher, almost all from Haiku 4.5. `RetrieveAndGenerate` sent more context per question than the 2,000 input tokens assumed.

## Anthropic: why it is a bound

The same two API keys (`myANTHROPICKey` on the Mac and `github-evals` in CI) served weeks 11, 12 and 13, and the console reports cost per UTC day. Week 12 ran from 2026-10-28 20:47 UTC (activity 1) to 2026-10-29 22:30 UTC (week 13 started at 22:31):

| UTC day | Mac key | CI key | Total |
|---|---|---|---|
| Oct 28 | $2.46 | $0.76 | $3.22 (includes the end of week 11) |
| Oct 29 | $1.59 | $0.13 | $1.72 |

So week 12 used **at most $4.94**. The activity notes in the README add up to about $5.2 for the whole week across providers, which is consistent with that bound. Lesson for the following weeks: one API key per week or per workflow, so the console separates the cost by itself. Week 14 already records the cost of every run in its harnesses.

## Also on the Google Cloud October invoice (not week 12)

The October bill is MXN 111.03. MXN 94.38 of it is the Gemini API in another project (`Gemini API`, mostly Gemini 3.8 Flash output tokens), which is not part of this lab.

## Budgets

With the bill reviewed, the two `semana12` budgets (AWS $10 a month, Google Cloud) are deleted with `aws_borrar.sh --confirmar --presupuesto` and `gcp_borrar.sh --confirmar --presupuesto`.
