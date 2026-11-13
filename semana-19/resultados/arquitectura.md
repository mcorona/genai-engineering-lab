# Week 19, activity 2: reference architecture and the IaC decision

## Diagram

Source: `semana-19/arquitectura/diagrama.mmd`. Export: `semana-19/arquitectura/diagrama.svg` (mermaid-cli 11.17.1). Trust boundaries (input for the threat model of activity 9): **Frontera 1** is the client (not trusted); **Frontera 2** is the VPC, which holds the tools Lambda, RDS and the endpoints. The four layers are base, datos, ia and computo.

Flow: client → API Gateway HTTP API (Cognito JWT, groups `analista` and `aprobador`) → agent Lambda (outside the VPC) → Bedrock Converse with Guardrail and Prompt Management → tools, directly or through AgentCore Gateway → tools Lambda in the VPC → RDS PostgreSQL (IAM auth, `copilot_ro`). `proponer_orden_compra` → Step Functions Standard (`waitForTaskToken`, with timeout) → approval by an `aprobador` user → write with the write role. The knowledge base of the data dictionary uses Titan Text Embeddings V2 and S3 Vectors. KMS (customer-managed key) covers everything that can be encrypted with it.

## ADR summary

| ADR | Decision | Cost basis |
|---|---|---|
| 0001 CDK vs Terraform | **CDK in Python** (default). Stable L1 constructs cover the Guardrail, the KB on S3 Vectors and the AgentCore Gateway | KMS key 1.00 USD/month (M) from the bootstrap |
| 0002 HTTP API vs REST API | Lab: HTTP API. Prod: REST API with WAF, usage plans and validation | HTTP API 0.0000009 USD/request (M); REST and WAF N |
| 0003 RDS vs Aurora vs Data API | Lab: RDS db.t4g.micro Single-AZ. Prod: RDS Multi-AZ | 0.016 USD/h (M); Aurora 0.12 USD/ACU-h (M); Data API N |
| 0004 Lambda vs AgentCore Runtime vs Bedrock Agents | Lab: Lambda outside the VPC. Prod option: AgentCore Runtime | Lambda GB-s 0.0000106667 (M); AgentCore Runtime c5.large 0.0102 USD/h (M); cold start 5.7–5.9 s (week 15) |
| 0005 Interface endpoints | Logs and Step Functions (interface), S3 (gateway) | Interface AZ-hour N; per GB 0.01 USD (D) |
| 0006 One AZ for endpoints | Lab: 1 AZ. Prod: 3 AZ | Multiplier N until the endpoint rate is measured |

## IaC spike and decision

| Measure | CDK (Python) | Terraform |
|---|---|---|
| Lines of code, base stack | 45 | 193 |
| checkov, base stack | 39 pass, 0 fail, 1 suppressed | 82 pass, 0 fail, 7 suppressed |
| checkov, Bedrock stack | 24 pass, 0 fail (L1) | 127 pass, 0 fail, 7 suppressed (base + IA) |
| cdk-nag 2.38.2 (AwsSolutions) | 13 compliant, 2 suppressed with reason, 0 non-compliant | not applicable |
| Guardrail, KB on S3 Vectors, AgentCore Gateway | L1 stable: synth OK. The L2 alpha KB does not support S3 Vectors | validate and plan OK |
| Synth or plan time | ~0.95 s synth | ~1.2 s plan (no refresh, no credentials) |
| Bootstrap account footprint | 17 resource types; KMS 1.00 USD/month (M); S3 and ECR storage N | none (local state) |

**Decision: CDK in Python** (ADR 0001). The default holds because the constructs the stack needs exist in the stable `aws-cdk-lib`. The bootstrap footprint is the cost of this choice, and the teardown of activity 9 must account for it.

## Limitations of the lab

- The lab does not deploy prod. The prod profile is synthesized and costed; its Multi-AZ database and endpoints are N.
- The lab total is complete (all its prices are M). Prod is partial: RDS Multi-AZ is N, and Step Functions transitions stay D (the Price List has no service code for them).
- Haiku 4.5 prices were re-queried on 2026-11-13 from the Price List (M).
- The Haiku token distribution comes from week 13 runs with Haiku 5.5; it is an approximation for Haiku 4.5.
- cdk-nag 3.0.2 (the candidate pin) fails on synth in this combination; the stack uses 2.38.2. Checkov covers both tools.
- The Cognito discovery URL in the Gateway is a placeholder; it is replaced in activity 3.
- AgentCore Gateway and the KB are synthesized and validated, not deployed.
