# GenAI Engineering Lab

[![Regression evals](https://github.com/mcorona/genai-engineering-lab/actions/workflows/evals-semana-06.yml/badge.svg?event=pull_request)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/evals-semana-06.yml)
[![Agent eval (week 13)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-13.yml/badge.svg?event=pull_request)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-13.yml)
[![MCP server (week 14)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-14.yml/badge.svg?event=pull_request)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-14.yml)
[![Agent frameworks (week 15)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-15.yml/badge.svg?event=pull_request)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-15.yml)
[![Client plugin (week 16)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-16.yml/badge.svg?event=pull_request)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-16.yml)
[![Agent reliability (week 17)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-17.yml/badge.svg?event=pull_request)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-17.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

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

## Key results

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
| LLMOps and multicloud production | [19](semana-19/Fas5Sema19.md) | The AWS reference architecture for LegacyBridge, deployed with infrastructure as code (in progress) |

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

Each week's test suite runs on its own, because the suites use separate `conftest.py` files. Evals that call a model need `ANTHROPIC_API_KEY`; each one prints its estimated cost, and most CI runs cost between $0.10 and $0.30.

## Status

| Phase | Weeks | Status |
|---|---|---|
| 1. LLM fundamentals | 1–4 | Complete |
| 2. Prompts, evals and NLQ | 5–7 | Complete |
| 3. RAG and data | 8–12 | Complete, with all 11 exit criteria verified |
| 4. Agents, MCP and orchestration | 13–18 | In progress: weeks 13 to 17 complete (exit criteria 13 to 17 verified); week 18 has the LegacyBridge v1 scope, bring-up and command merged |
| 5. LLMOps and multicloud production | 19–24 | In progress: week 19 has the account baseline, the IaC decision (six ADRs) and the foundation stack merged; no exit criterion verified yet |

The exit criteria of every phase, each with the PR that verified it, are listed in [docs/exit-criteria.md](docs/exit-criteria.md).

### Phase 5: LLMOps and multicloud production

LegacyBridge goes from demo to production in the client's cloud, with IaC, security, monitoring and controlled costs. The phase closes with the AWS Certified Generative AI Developer – Professional (AIP-C01) exam.

| Criterion | Week | Status |
|---|---|---|
| 19. LegacyBridge deployed on AWS from IaC: a reference architecture diagram, least-privilege IAM, KMS encryption at rest, private networking through VPC endpoints, a Bedrock Guardrail and versioned prompts, the golden mini eval passing against the deployed endpoint, measured cost per query, and a verified teardown | 19 | Pending (in progress) |
| 20. A cost-per-query dashboard and a budget alarm, with prompt caching, batch inference and model routing measured against the week 19 baseline | 20 | Pending |
| 21. A red-teaming report for the deployed API, with findings and mitigations (OWASP Top 10 for LLM Applications) | 21 | Pending |
| 22. An AWS ↔ Azure ↔ GCP service matrix and a minimal deployment in a second cloud | 22 | Pending |

Two cross-cutting criteria apply to every week:

- **Cost:** the error of the monthly quote against the real cost is measured and must stay within ±20%. Pending: the first measurement comes with the week 19 deployment.
- **Security:** no unsuppressed scanner finding, and no public resource except the API. Pending: the first check comes with the week 19 IaC.

## Security and credentials

- No credentials live in the repository. Cloud access uses CLI sessions and OIDC federation, and API keys exist only as GitHub secrets.
- To report a vulnerability, see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE). All data is synthetic (seed 42), and no customer data is used.
