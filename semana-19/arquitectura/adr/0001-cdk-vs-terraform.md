# ADR 0001: CDK (Python) or Terraform for the LegacyBridge stack

## Context

Week 19 deploys the LegacyBridge demo with infrastructure as code. The spike (`semana-19/spike/`) writes the same minimal stack in CDK (Python, `aws-cdk-lib` 2.276.0) and Terraform (`hashicorp/aws` 6.73.0), and adds a Guardrail, a Knowledge Base on S3 Vectors and an AgentCore Gateway in both. The measurements are in `semana-19/resultados/spike_iac.json`. The default is CDK in Python, unless the spike shows that the Bedrock or AgentCore constructs are missing or unstable.

## Alternatives

- **CDK, Python.** Stable L1 constructs exist for every resource the spike needs (`CfnGuardrail`, `CfnKnowledgeBase`, `CfnVectorBucket`, `CfnIndex`, `CfnGateway`). The alpha L2 packages (`aws-cdk.aws-bedrock-alpha`, `aws-cdk.aws-bedrock-agentcore-alpha`, 2.276.0a0) exist but do not cover S3 Vectors for the Knowledge Base, and the AgentCore alpha already marks some classes as deprecated in favour of `aws-cdk-lib`.
- **Terraform.** Native resources exist and validate: `aws_bedrock_guardrail`, `aws_bedrockagent_knowledge_base` (with `S3_VECTORS`), `aws_s3vectors_vector_bucket`, `aws_s3vectors_index`, `aws_bedrockagentcore_gateway`.

### Measurements (`spike_iac.json`)

| Measure | CDK (Python) | Terraform |
|---|---|---|
| Lines of code, base stack (no comments, no blank lines) | 45 | 193 (base only) |
| checkov, base stack after fixes | 39 pass, 0 fail, 1 suppressed | 82 pass, 0 fail, 7 suppressed |
| checkov, IA stack | 24 pass, 0 fail (L1 template) | 127 pass, 0 fail, 7 suppressed (base + IA) |
| cdk-nag (AwsSolutions) | 2.38.2 with `aws-cdk-lib` 2.276.0, applied as a stack aspect: 15 rules, 13 compliant, 2 suppressed with reason, 0 non-compliant. Before the wildcard fixes: 5 IAM5 findings. cdk-nag 3.0.2 fails on synth with `aspectApplication.aspect.visit is not a function` | not applicable |
| Guardrail | L1 `CfnGuardrail` synthesizes; L2 alpha `Guardrail` synthesizes | `aws_bedrock_guardrail` validates and plans |
| Knowledge Base on S3 Vectors | L1 `CfnKnowledgeBase` + `CfnVectorBucket` + `CfnIndex` synthesizes. The L2 alpha `KnowledgeBase` accepts only `VectorStore.open_search_serverless`, so it cannot use S3 Vectors | `aws_bedrockagent_knowledge_base` + `aws_s3vectors_*` validates and plans |
| AgentCore Gateway | L1 stable `CfnGateway` synthesizes; L2 alpha `Gateway` synthesizes | `aws_bedrockagentcore_gateway` validates and plans |
| Synth or plan time | synth ~0.95 s | plan ~1.2 s (`-refresh=false`, no credentials) |
| Account footprint at bootstrap | `cdk bootstrap` creates 17 resource types (KMS key and alias, bucket, bucket policy, ECR repository, 5 roles, 2 inline policies, 1 managed policy, SSM parameter). KMS key 1.00 USD/month (M). S3 and ECR storage: N | none; local state file (not versioned) |
| Plan result, base + IA | not applicable | 24 to add, 0 to change, 0 to destroy |

## Decision

**CDK in Python**, following the default. The Bedrock and AgentCore constructs needed by the stack exist in the stable `aws-cdk-lib` (L1). The alpha L2 classes are not used in code that will deploy: the KB L2 cannot express S3 Vectors, and the AgentCore alpha already points to `aws-cdk-lib` for some classes.

The rule that would have changed the default (constructs missing or unstable) does not hold for the stable L1 constructs. cdk-nag 3.0.2 does not run in this combination; 2.38.2 does, and it is the version that the plan's scanner checks use (with checkov on the same stack). This pin deviates from the candidate 3.0.2 of `preparar/versiones.json`, and the reason is recorded here.

**Reason against it, recorded:** `cdk bootstrap` puts resources in the account (a KMS key at 1.00 USD/month, plus S3 and ECR storage) that Terraform with local state would not create. The lab must account for them in the teardown of activity 9.

## Consequences

- The IaC code is Python with pinned versions in `semana-19/spike/cdk/requirements.txt` (`aws-cdk-lib` 2.276.0, `constructs` 10.8.1, `cdk-nag` 2.38.2, both alpha packages 2.276.0a0). Scanning uses checkov 3.4.4, not cdk-nag.
- The Knowledge Base uses L1 `CfnKnowledgeBase` with S3 Vectors. If the L2 alpha gains S3 Vectors support, the decision should be reviewed.
- The bootstrap resources are declared in the teardown plan: the KMS key has a deletion window, and its billing until deletion is marked D (see `linea_base.md` §3).
- The AgentCore Gateway in the lab uses an example Cognito discovery URL (placeholder). It must be replaced when the Cognito user pool exists (activity 3).
- Terraform stays as the comparison in the spike. It is not in the lab deployment path.

## Costs (from `linea_base.md` and `spike_iac.json`)

- KMS customer-managed key: 1.00 USD per key-month (M, `us-east-1-KMS-Keys`, 2026-11-12).
- Bootstrap S3 and ECR storage: N (not measured).
- The IaC tool does not change the runtime cost of the stack; it changes the account footprint above.
