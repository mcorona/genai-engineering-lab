# Unit 19: AWS reference architecture for LegacyBridge, deployed with IaC

**Status: in progress.** Exit criterion 19 is not verified yet. This unit deploys LegacyBridge in an AWS account with infrastructure as code, under the controls a client would require: least-privilege IAM, KMS encryption at rest, private networking through VPC endpoints, a Bedrock Guardrail, versioned prompts, the golden mini eval against the deployed endpoint, measured cost per query and a verified teardown.

## Progress

| Activity | Result | Evidence |
|---|---|---|
| 1. Baseline | The account, the services and their prices, measured read-only before any resource is created | [`resultados/linea_base.md`](resultados/linea_base.md) |
| 2. Reference architecture and IaC decision | A diagram with its trust boundaries, an IaC spike in CDK and Terraform with measurements, six ADRs, `cdk-nag` at zero findings, and a cost model | [`resultados/arquitectura.md`](resultados/arquitectura.md), [`arquitectura/adr/`](arquitectura/adr/), [`resultados/cotizacion.md`](resultados/cotizacion.md) |
| 3. Foundation stack | KMS, a VPC with no internet gateway or NAT, VPC endpoints, IAM with a permissions boundary, and spend controls; deployed, torn down and checked with an inventory | [`resultados/base.md`](resultados/base.md) |
| 4. Data layer | RDS PostgreSQL with the legacy schema and a Bedrock Knowledge Base over the data dictionary (in progress) | [`resultados/costo_actividad4.md`](resultados/costo_actividad4.md) |
| 5 to 10 | Bedrock (Guardrail, Prompt Management), compute and the approval workflow, AgentCore Gateway, evaluation against the deployed endpoint, the security review, and CI | Pending |

Every activity that creates AWS resources starts with a cost estimate, and nothing is deployed without the author's explicit approval. The tests in [`tests/`](tests/) run without AWS: `uv sync --group semana19`, then `uv run python -m pytest -q semana-19/tests`.

## Plan

The full plan, with every activity, its decisions and its cost, is in [`Fas5Sema19.md`](Fas5Sema19.md).
