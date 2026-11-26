# GenAI Engineering Lab

**GenAI on legacy business systems, deployed in the client's own cloud, with every claim measured.**

For companies whose inventory, sales or billing still live in an old database with cryptic names. The lab puts natural-language questions, agents and audits on top of that database: read-only, with costs and failure rates known before go-live.

Services: an AI Opportunity & Risk Assessment, agent and MCP architecture, and deployment on AWS ([Work with me](#work-with-me)).

[![Regression evals](https://github.com/mcorona/genai-engineering-lab/actions/workflows/evals-semana-06.yml/badge.svg?event=pull_request)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/evals-semana-06.yml) [![Agent eval (week 13)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-13.yml/badge.svg?event=pull_request)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-13.yml) [![MCP server (week 14)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-14.yml/badge.svg?event=pull_request)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-14.yml) [![Agent frameworks (week 15)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-15.yml/badge.svg?event=pull_request)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-15.yml) [![Client plugin (week 16)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-16.yml/badge.svg?event=pull_request)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-16.yml) [![Agent reliability (week 17)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-17.yml/badge.svg?event=pull_request)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-17.yml) [![AWS deployment (week 19)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-19.yml/badge.svg?event=pull_request)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-19.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Results at a glance

| What a client gets | Measured result | Evidence |
|---|---|---|
| An agent instead of a fixed workflow | pass@1 **0.889** vs. 0.504 for the workflow, on 84 tasks | [patrones.md](semana-13/resultados/patrones.md) |
| Agent security | **140/140** runs passed over 70 attack and permission cases: database unchanged, 0 leaks, 0 injected instructions obeyed | [seguridad.md](semana-13/resultados/seguridad.md) |
| Text-to-SQL on a legacy schema | **0.977** ES / **1.000** EN execution accuracy at **$0.00033** per question | [sql_legado.md](semana-10/resultados/sql_legado.md) |
| Deployment on AWS with its cost per query | **$0.030913** per query for the model and $0.037562 per hour for the running stack, from the AWS bill | [costo_real.md](semana-19/resultados/costo_real.md) |
| A schema-audit plugin as a product | **12 of 13** seeded risks found, Δ **+0.57** over the same model without the plugin | [plugin.md](semana-16/resultados/plugin.md), [eval_plugin.md](semana-16/resultados/eval_plugin.md) |

The full table, with every capability, is under [Detailed results](#detailed-results).

## Work with me

| Service | What it covers | Price |
|---|---|---|
| **AI Opportunity & Risk Assessment: Snapshot** | A read-only audit of a small legacy schema (up to ~10 objects): data dictionary, ER diagram, risk report and summary, with one validation session | USD 1,500, fixed fee |
| **AI Opportunity & Risk Assessment: Assessment** | The same audit on up to ~50 objects, with all 7 deliverables, including the map of AI opportunities | USD 3,500, fixed fee |
| **Agent and MCP architecture** | Design and review of agents, MCP servers, permissions, budgets and evals for your systems | USD 150–200 per hour |
| **Deployment on AWS** | The reference architecture of [week 19](semana-19/README.md) in your account, from IaC, with cost per query and teardown | USD 150–200 per hour |

- Scope and deliverables of the assessment: [semana-16/oferta.md](semana-16/oferta.md).
- **Product:** [`legacy-schema-audit`](semana-16/legacy-schema-audit/README.md), a Claude Code plugin that audits a legacy schema read-only. It is the technical basis of the assessment.
- **Certifications:** Claude Certified Architect – Foundations; AWS Certified AI Practitioner.
- **Contact:** [LinkedIn](https://www.linkedin.com/in/manuel-corona-70527aa).

## About the lab

**Measured, reproducible GenAI engineering on legacy business systems.** The lab builds RAG, text-to-SQL, agents and MCP servers over an inventory system with cryptic table names and decades-old business rules, in Spanish and English, and backs every claim with an eval that runs in CI.

Most GenAI demos show that something *can* work. This lab measures *how well* it works, *what it costs* and *how it fails*, under the constraints of a real company:

- read-only access to a legacy database;
- users with different roles and tenants;
- untrusted documents and data;
- a budget.

**Author:** Manuel Corona, independent AI architect and consultant. PhD in information technologies, with 30+ years in software and information systems across industry and university teaching.

## How the work is done

| Principle | In practice |
|---|---|
| Gold sets are frozen before any experiment | Every comparison uses the same frozen set (with hashes), so a change in the score comes from the change being tested |
| Verification by execution, not by eye | SQL is executed and result sets are compared. Agent tasks are checked against the database. LLM judges are validated on known failures before they are used |
| Evals gate pull requests | GitHub Actions runs the evals on each PR that touches a component. Thresholds come from a fixed calibration rule, and their false-alarm rate is measured ([example](semana-13/resultados/ci_calibracion.md)) |
| Security is a hard requirement, tested in CI | Zero unapproved writes, zero leaks across roles and tenants, and zero obeyed injected instructions. Any failure breaks the PR |
| Cost and latency sit next to quality | Results that call a model report cost per query (USD) and latency, with prices taken from the official pricing pages |
| Negative results are reported | Techniques that did not beat the baseline (hybrid search, HyDE, query rewriting, contextual retrieval, fine-tuning) are documented and **not adopted** |
| Every number links to its evidence | Results files live under `resultados/`, and each exit criterion names the PR that verified it |

## Detailed results

| Capability | Result | Evidence |
|---|---|---|
| **Agent vs. workflow** (84 tasks, k = 3) | Claude Agent SDK agent: pass@1 **0.889**. Fixed-routing workflow: **0.504** (+0.385, 95% CI [0.282, 0.496]). The agent wins on business rules, compound tasks and ambiguous requests. The workflow ties on direct questions at a fraction of the cost ($0.0004 vs. $0.0018 per task) | [`semana-13`](semana-13/README.md) |
| **Agent security** | **140/140** runs: unchanged table fingerprints, proposals kept in `PENDING_APPROVAL`, 0 leaks, 0 injected instructions obeyed | [`semana-13/resultados/seguridad.md`](semana-13/resultados/seguridad.md) |
| **Text-to-SQL on a legacy schema** | With the data dictionary: execution accuracy **0.977 ES / 1.000 EN** (the same as on the original schema) at **$0.00033 per question** (Haiku). Without it: 0.884 / 0.953 | [`semana-10`](semana-10/README.md) |
| **Integrated assistant** (SQL + documents) | Accuracy 0.961 ES / 0.980 EN with citations, vs. 0.294 SQL-only and 0.608 documents-only. $0.00083 per question, p50 5.3 s. 0 writes, 0 leaks in 128 cases, 0/48 injected instructions obeyed | [`semana-10`](semana-10/README.md) |
| **Retrieval** | Reranking raises nDCG@10 from 0.904 to **0.982** (ES) and from 0.885 to **0.974** (EN). Hybrid BM25 + vector search does not help and is not adopted | [`semana-08`](semana-08/README.md) |
| **Multi-tenant RAG** | Tenant and role filters inside the query on pgvector, Qdrant and OpenSearch: **0 leaks**, checked in CI | [`semana-09`](semana-09/README.md) |
| **RAG evaluation** | Separate retrieval and generation suites. RAGAS metrics are validated on known failures before use. $0.28 per CI run | [`semana-11`](semana-11/README.md) |
| **Managed RAG** (AWS and Google Cloud) | Bedrock Knowledge Bases and Vertex AI Search compared with the in-house pipeline on the same gold set. Cost from $0.00027 to $0.0012 per query, 0 leaks in 672 queries, keyless CI through OIDC federation, all resources deleted afterwards | [`semana-12`](semana-12/README.md) |
| **Remote MCP server with OAuth** | MCP 2026-07-28 over Streamable HTTP, with Keycloak as the authorization server (PKCE, RFC 8707 audience) and least privilege in three layers (scopes, filtered catalogs, one PostgreSQL role per profile). 13/13 threats covered. Tool poisoning: **38/38** cases blocked with client-side defenses (without them, tool shadowing captured 100% of queries). The agent over HTTP + OAuth has the same success rate and cost as in-process, +7 ms per tool call, and 0/8 leaks for roles without the scope | [`semana-14`](semana-14/README.md) |
| **Same agent in four frameworks** | LangGraph and Strands score **0.900 / 0.900** on 40 tasks with identical failures and pass **38/38** poisoning cases each through an MCP gateway; OpenAI Agents SDK and Google ADK score 0.950 on 20. The framework does not change quality; it changes cost (ADK +53% from forwarding full MCP results), protocols, observability and hosting. Multi-agent over A2A (a Keycloak audience per agent) ties the single agent at 1.7× the cost and 3× the latency. On Bedrock AgentCore: the same 1.000, with a 5.7 s cold start. A [client decision matrix](semana-15/resultados/matriz_decision.md) links every score to its evidence | [`semana-15`](semana-15/README.md) |
| **Client plugin with its own eval** | [`legacy-schema-audit`](semana-16/legacy-schema-audit/README.md) 1.0.0, installable from this repository's plugin marketplace: a read-only audit of a legacy schema (data dictionary, ER diagram, risks with SQL evidence, executive summary). With Sonnet: PK/FK/PII 1.00 and **12 of 13** seeded risks for about $1; behavior suite **Δ +0.57** over no plugin; security **14/14** (prompt injection, data changes, credentials, hook bypass, tool poisoning). Browser-agent and computer-use spikes on a legacy screen: 10/10 fields. CI runs a mini eval with calibrated thresholds on every PR (about $0.11) | [`semana-16`](semana-16/README.md) |
| **Agent reliability in production** | One task is one OpenTelemetry GenAI trace (agent, model, MCP client and server, SQL) in a self-hosted Langfuse, through a Collector that redacts by **allowlist** (0 of 9 canaries leaked, with content capture both off and on). Budgets per task, session and tenant-day (**0 caps crossed** in 84 paid tasks); input, tool and output guardrails (**0 obeyed** in 38 attacks, with false positives measured on 84 tasks); human approval of purchase orders with the approver level taken from Keycloak (**0 orders without approval**); a trajectory eval read from the spans (91.7%) with scores in Langfuse; a dashboard as code and a runbook. CI runs a mini eval with calibrated thresholds on every PR (about $0.08) | [`semana-17`](semana-17/README.md) |
| **Deployed on AWS from IaC** | LegacyBridge on Bedrock (Haiku 4.5, a Guardrail, versioned prompts), Lambda, Step Functions, API Gateway with Cognito JWT, and the tools and RDS in a VPC with no internet path, from CDK. **0** unsuppressed cdk-nag and checkov findings, and every IAM-policy finding classified with its reason. Measured cost: **$0.030913 per query** for the model and $0.037562 per hour for the running stack. The teardown is verified. The eval against the deployed endpoint did its job: it caught a regression when the model changed from Haiku 5.5 (local) to Haiku 4.5 (on AWS), **9/20**. The diagnosis found a per-task token budget calibrated for the other model; with that fixed, the corrected run reached **16/20**. It is still a regression under week 10's rule, and week 20 works on the remaining failures | [`semana-19`](semana-19/README.md), [`costo_real.md`](semana-19/resultados/costo_real.md), [`eval_aws.md`](semana-19/resultados/eval_aws.md), [`linea_base.md`](semana-20/resultados/linea_base.md) |

## LegacyBridge: the reference system

LegacyBridge is the case study that runs through the lab. A company keeps its inventory, sales and purchasing in a legacy PostgreSQL schema:

- **cryptic names:** tables such as `artmst` and `exidet`, and columns such as `art_ptr`;
- **business rules** that live in documents, not in the database;
- **users** with different roles (warehouse, sales, purchasing) and tenants.

The goal is to let people ask questions in natural language and get answers backed by evidence, without ever writing to the system or leaking data across roles.

```mermaid
flowchart LR
  U[User<br/>ES / EN] --> A[Agent<br/>own loop or Claude Agent SDK]
  A -->|MCP 2026-07-28<br/>OAuth 2.1 bearer| M[MCP server<br/>tools · resources · prompts]
  K[Authorization server<br/>Keycloak] -. JWT: iss, aud, scope .-> M
  M -->|read-only role per scope<br/>guard: SELECT only| DB[(Legacy PostgreSQL<br/>schema legado)]
  A --> R[Document RAG<br/>rules, policies, scans]
  R --> V[(pgvector / Qdrant / OpenSearch<br/>tenant + role filters)]
```

On AWS (week 19), the same system runs in the client's account:

![LegacyBridge on AWS](semana-19/arquitectura/diagrama_simple.svg)

The detailed architecture, checked against the deployed stacks in CI, is in [semana-19](semana-19/README.md#detailed-architecture).

The pieces were built and measured one at a time:

1. Text-to-SQL ([week 7](semana-07/README.md), [week 10](semana-10/README.md)).
2. Document RAG ([weeks 8 to 12](semana-08/README.md)).
3. Agent and MCP ([week 13](semana-13/README.md), [week 14](semana-14/README.md)).
4. Frameworks, a client plugin and production reliability ([weeks 15 to 17](semana-15/README.md)).
5. **LegacyBridge v1** ([week 18](semana-18/README.md)): one bring-up script and one command, `python -m legacybridge`, with a simple mode and a multi-agent mode that share the same budgets, guardrails and approvals.

## Repository map

Each folder `semana-NN` is week NN of the lab's study program (*semana* is Spanish for "week"). A week is a unit of work, not a calendar week: weeks are completed at the author's own pace, so commit dates do not line up with them. Every week has its own `README.md` with method, results, cost and decisions.

| Area | Weeks | What you will find |
|---|---|---|
| LLM fundamentals | [1](semana-01/README.md) · [2](semana-02/README.md) · [3](semana-03/README.md) · [4](semana-04/README.md) | A mini-GPT in MLX; token cost and sampling variability by language; a documented decision *not* to fine-tune (LoRA vs. prompting); local quantized inference vs. an API (the API is about 13× faster at p50) |
| Prompts and evals | [5](semana-05/README.md) · [6](semana-06/README.md) · [7](semana-07/README.md) | A versioned prompt library; regression evals as a required PR check; bilingual natural-language querying (NLQ) measured by execution |
| RAG and data | [8](semana-08/README.md) · [9](semana-09/README.md) · [10](semana-10/README.md) · [11](semana-11/README.md) · [12](semana-12/README.md) | Chunking, embeddings and vector databases; advanced and multi-tenant RAG; a legacy schema, PDFs, OCR and images; RAG evaluation; managed RAG on AWS and Google Cloud |
| Agents and MCP | [13](semana-13/README.md) · [14](semana-14/README.md) · [15](semana-15/README.md) · [16](semana-16/README.md) · [17](semana-17/README.md) · [18](semana-18/README.md) | Agentic patterns and the Claude Agent SDK; a remote MCP server with OAuth, least privilege and tool-poisoning tests; the same agent in LangGraph, Strands, OpenAI Agents SDK and Google ADK, multi-agent over A2A, Bedrock AgentCore and a client decision matrix; a Claude Code plugin for clients with its own eval; production reliability (tracing, budgets, guardrails, human approval, trajectory eval, a trace dashboard); LegacyBridge v1 |
| LLMOps and multicloud production | [19](semana-19/README.md) · [20](semana-20/Fas5Sema20.md) | The AWS reference architecture for LegacyBridge, deployed with infrastructure as code, evaluated against the deployed endpoint, reviewed for security and torn down; costs and performance on AWS (in progress) |

### Weeks at a glance

| Week | Folder | Topic |
|---|---|---|
| 1 | [`semana-01/`](semana-01/README.md) | A mini-GPT in MLX, from a bigram model to a transformer block |
| 2 | [`semana-02/`](semana-02/README.md) | Tokens and response variability, in Spanish and English |
| 3 | [`semana-03/`](semana-03/README.md) | Adaptation: to fine-tune or not to fine-tune |
| 4 | [`semana-04/`](semana-04/README.md) | Inference: quantization, latency and cost |
| 5 | [`semana-05/`](semana-05/README.md) | Multi-model prompting and a versioned prompt library |
| 6 | [`semana-06/`](semana-06/README.md) | Evals and regression testing in GitHub Actions |
| 7 | [`semana-07/`](semana-07/README.md) | Bilingual natural-language querying (NLQ) over an inventory database |
| 8 | [`semana-08/`](semana-08/README.md) | Retrieval: chunking, embeddings, vector databases, BM25 and reranking, cited answers |
| 9 | [`semana-09/`](semana-09/README.md) | Advanced RAG: query rewriting, HyDE, contextual retrieval, GraphRAG, permissions, multi-tenant |
| 10 | [`semana-10/`](semana-10/README.md) | Structured data and documents: text-to-SQL on a legacy schema, PDF tables, OCR, images |
| 11 | [`semana-11/`](semana-11/README.md) | RAG evaluation: recall@k, faithfulness and answer relevance with RAGAS, cost per query |
| 12 | [`semana-12/`](semana-12/README.md) | Managed RAG: Bedrock Knowledge Bases and Vertex AI Search |
| 13 | [`semana-13/`](semana-13/README.md) | Agentic patterns (workflows vs. agents) and the Claude Agent SDK |
| 14 | [`semana-14/`](semana-14/README.md) | A remote MCP server with OAuth, least privilege and tool-poisoning tests |
| 15 | [`semana-15/`](semana-15/README.md) | The same agent in four frameworks, multi-agent with A2A, and a decision matrix |
| 16 | [`semana-16/`](semana-16/README.md) | A reusable Claude Code plugin for clients, with its own eval |
| 17 | [`semana-17/`](semana-17/README.md) | Agent reliability in production |
| 18 | [`semana-18/`](semana-18/README.md) | LegacyBridge v1 and the close of Phase 4 |
| 19 | [`semana-19/`](semana-19/README.md) | LegacyBridge on AWS, from infrastructure as code |
| 20 | [`semana-20/`](semana-20/Fas5Sema20.md) | Costs and performance for LegacyBridge on AWS (in progress) |

### Folder and file names

Code identifiers, folder names and some runtime messages are in Spanish, because they are part of the measured system: the agent's tools return those messages to the model, and the recorded runs and frozen gold sets depend on them. The documentation is in English. The Spanish evaluation data (the document corpus, the Spanish gold sets and prompts) is intentional, since the lab measures every capability in both languages.

| Name | Meaning | Name | Meaning |
|---|---|---|---|
| `semana-NN` | week NN | `resultados/` | results and evidence |
| `golden/` | frozen gold sets | `linea_base/` | baseline checks |
| `herramientas/` | agent tools | `seguridad/` | security tests |
| `servidor/`, `cliente/` | server, client | `legado` | the legacy schema |
| `agente/` | agent | `corridas/` | runs |
| `aprobaciones/` | approvals | `presupuestos/` | budgets |
| `observabilidad/` | observability | `tablero/` | dashboard |
| `costos/` | costs | `arquitectura/` | architecture |
| `fuentes/`, `corpus/` | source documents | `pizarra/` | whiteboard design |

Every other Spanish term a reader meets (file names, JSON keys, command-line flags, AWS stack names, status values such as `respondida` or `PENDING_APPROVAL`, and the legacy tables) is in the [glossary](docs/glossary.md).

## Quickstart

These steps run the agent tools, the MCP server and their tests against a synthetic legacy database. They need no API key and cost $0.

```bash
# requirements: uv, Python 3.13, Docker and the psql client
uv sync
docker run -d --name genai-lab-db -p 5432:5432 \
  -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=dev-only -e POSTGRES_DB=inventory pgvector/pgvector:pg16
export PG_ADMIN_DSN=postgresql://admin:dev-only@localhost:5432/inventory
export PG_DSN=postgresql://copilot_ro:ci-ro@localhost:5432/inventory

uv run python semana-07/ci/preparar_base.py                       # schema, read-only role, synthetic data (seed 42)
psql "$PG_ADMIN_DSN" -f semana-10/legado/legado.sql               # legacy views with cryptic names
psql "$PG_ADMIN_DSN" -f semana-13/seguridad/artnot.sql            # free-text notes (injection tests)

uv run python -m pytest -q semana-13/tests                        # tools, SQL guard, permissions
uv run python -m pytest -q semana-14/tests                        # MCP server (Keycloak tests skip unless it is running)
uv run python semana-14/linea_base/verificar_sdk.py               # MCP SDK baseline against the spec
```

Run each week's test suite separately: each suite has its own `conftest.py`. Evals that call a model need `ANTHROPIC_API_KEY`. Each one prints its estimated cost, and most CI runs cost between $0.10 and $0.30.

## Status

| Phase | Weeks | Status |
|---|---|---|
| 1. LLM fundamentals | 1–4 | Complete |
| 2. Prompts, evals and NLQ | 5–7 | Complete |
| 3. RAG and data | 8–12 | Complete, with all 11 exit criteria verified |
| 4. Agents, MCP and orchestration | 13–18 | In progress: weeks 13 to 17 complete (exit criteria 13 to 17 verified). Week 18: the LegacyBridge v1 scope, bring-up script and command are merged |
| 5. LLMOps and multicloud production | 19–24 | In progress: week 19 complete. Criterion 19 is met except for the mini eval (regression: 9/20, 16/20 after week 20's correction) and KMS at rest (partial: 17 of 29 resources on the project key). Week 20 in progress; weeks 21 to 24 pending |

The exit criteria of every phase, each with the PR that verified it, are listed in [docs/exit-criteria.md](docs/exit-criteria.md).

### Phase 5: LLMOps and multicloud production

LegacyBridge goes from demo to production in the client's cloud, with IaC, security, monitoring and controlled costs. The phase closes with the AWS Certified Generative AI Developer – Professional (AIP-C01) exam.

| Criterion | Week | Status |
|---|---|---|
| 19. LegacyBridge deployed on AWS from IaC: a reference architecture diagram, least-privilege IAM, KMS encryption at rest, private networking through VPC endpoints, a Bedrock Guardrail and versioned prompts, the golden mini eval passing against the deployed endpoint, measured cost per query, and a verified teardown | 19 | **Met except two parts:** the mini eval (regression, 9/20) and KMS at rest (partial). See the parts below and [semana-19/README.md](semana-19/README.md) |
| 20. A cost-per-query dashboard and a budget alarm, with prompt caching, batch inference and model routing measured against the week 19 baseline | 20 | **In progress.** Merged: the corrected baseline, 16/20, accepted as the baseline although it does not pass ([linea_base.md](semana-20/resultados/linea_base.md)), and the cost attribution by component: application inference profiles, cost tags and per-query metrics ([atribucion.md](semana-20/resultados/atribucion.md), its live run pending). Caching, routing, batch, the dashboard and the alarm are next |
| 21. A red-teaming report for the deployed API, with findings and mitigations (OWASP Top 10 for LLM Applications) | 21 | Pending |
| 22. An AWS ↔ Azure ↔ GCP service matrix and a minimal deployment in a second cloud | 22 | Pending |

Criterion 19, part by part:

- [x] **Reference architecture diagram:** [diagrama.svg](semana-19/arquitectura/diagrama.svg), checked against the synth both ways in CI ([test_diagrama_vs_stack.py](semana-19/tests/test_diagrama_vs_stack.py), #318).
- [x] **Least-privilege IAM:**
  - a permissions boundary on every role the stacks create ([base.md](semana-19/resultados/base.md));
  - IAM Access Analyzer ValidatePolicy on 100 policy documents (50 per profile): a deployment disproved its 4 errors, and no security error or warning remains ([validate_policy.json](semana-19/resultados/seguridad/validate_policy.json));
  - Parliament in CI, with 0 unclassified findings ([parliament.json](semana-19/resultados/seguridad/parliament.json)).
- [ ] **KMS encryption at rest, partial:** 17 of 29 resources are on the project key. The other 12 are encrypted, but with AWS-owned or AWS-managed keys, SSE-S3 or CloudWatch Logs' default encryption. They are findings H10 (11 resources) and H14 (the bootstrap's assets bucket), both open ([verificacion.json](semana-19/resultados/seguridad/verificacion.json), check `cifrado`).
- [x] **Private networking through VPC endpoints:** the network and endpoints checks pass; RDS has no public IP ([verificacion.json](semana-19/resultados/seguridad/verificacion.json); [ADR 0005](semana-19/arquitectura/adr/0005-interface-endpoints.md)).
- [x] **Bedrock Guardrail and versioned prompts:** the Guardrail ran live at its pinned version 3 on 24 inputs ([apply_guardrail.json](semana-19/resultados/apply_guardrail.json), compared with the deterministic guardrails in [comparacion_determinista.json](semana-19/resultados/comparacion_determinista.json)). The ES and EN prompts were deployed with their prompt versions (`AWS::Bedrock::PromptVersion` in [verificacion.json](semana-19/resultados/seguridad/verificacion.json)).
- [ ] **Golden mini eval passing against the deployed endpoint: regression, 9/20.**
  - Wilson 95% [0.258, 0.658], against week 17's local 20/20.
  - Diagnosis: the per-task token budget, the missing prompt cache, and cases c02 and c06-en. The 20/20 baseline ran on Haiku 5.5; the endpoint runs Haiku 4.5.
  - The fixes go to week 20 ([eval_aws.md](semana-19/resultados/eval_aws.md)). Week 20's corrected run, with the per-task budget fixed, reached 16/20 (Wilson 95% [0.584, 0.919]), still a regression ([linea_base.md](semana-20/resultados/linea_base.md)).
- [x] **Measured cost per query:** 0.030913 USD for the model alone, and 0.037562 USD per hour of stack, from the bill ([costo_real.md](semana-19/resultados/costo_real.md)).
- [x] **Verified teardown:** `"quedan": "nada"` (nothing remains). Still present: the read-only role and 3 KMS keys scheduled for deletion, with their dates ([inventario_final.json](semana-19/resultados/inventario_final.json)).

Two cross-cutting criteria apply to every week:

- **Cost:** the error of the monthly quotation against the real cost is measured and must stay within ±20%.
  - Week 19: within ±20% on the model cost (−0.1%) and the hourly cost (−10.3%).
  - Outside the range on the upper bound (+24.6%). That bound also includes the Bedrock judge's job, which Cost Explorer cannot split by query ([cotizacion.md](semana-19/resultados/cotizacion.md), [costo_real.md](semana-19/resultados/costo_real.md)).
  - The week cost 8.928936 USD gross, 0.00 USD net with credits ([costo_semana.json](semana-19/resultados/costo_semana.json)).
- **Security:** no unsuppressed scanner finding, and no public resource except the API.
  - Week 19: **met, with open findings.**
  - gitleaks: 0 unclassified findings. checkov: 0 failed (38 skipped with a reason). cdk-nag: 0 unsuppressed (55 suppressed with a reason). Only the API is public, and every route has the JWT authorizer ([seguridad.md](semana-19/resultados/seguridad.md), [verificacion.json](semana-19/resultados/seguridad/verificacion.json)).
  - Open: H1, H2, H4 and H10 for week 20; H3, H5, H8, the H13 residual case, and H7, H12 and H14 for week 21. H6 and H11 are accepted for the lab ([threat_model.md](semana-19/seguridad/threat_model.md)).

**AIP-C01:** the target is the week of May 3, 2027. The exam is booked only after 3 practice exams score at least 85%. The concepts the lab shows, by exam domain, and the gaps are in [semana-19/resultados/aip_c01.md](semana-19/resultados/aip_c01.md).

## Security and credentials

- No credentials live in the repository. Cloud access uses CLI sessions and OIDC federation, and API keys exist only as GitHub secrets.
- To report a vulnerability, see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE). All data is synthetic (seed 42), and no customer data is used.
