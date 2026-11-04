# GenAI Engineering Lab

**English** · [Español](README.es.md)

[![Client plugin (week 16)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-16.yml/badge.svg)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-16.yml)
[![Agent reliability (week 17)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-17.yml/badge.svg)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-17.yml)
[![Agent frameworks (week 15)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-15.yml/badge.svg)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-15.yml)
[![MCP server (week 14)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-14.yml/badge.svg)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-14.yml)
[![Agent eval (week 13)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-13.yml/badge.svg)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/eval-semana-13.yml)
[![Regression evals](https://github.com/mcorona/genai-engineering-lab/actions/workflows/evals-semana-06.yml/badge.svg)](https://github.com/mcorona/genai-engineering-lab/actions/workflows/evals-semana-06.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Measured, reproducible GenAI engineering on legacy business systems:** RAG, text-to-SQL, agents and MCP over an inventory system that has cryptic table names and decades-old business rules. It is bilingual (Spanish and English), and every claim is backed by an eval in CI.

Most GenAI demos show that something *can* work. This lab measures *how well* it works, *what it costs* and *how it fails*, under the constraints a real company has:
- Read-only access to a legacy database.
- Users with different roles and tenants.
- Untrusted documents and data.
- A budget.

Author: **Manuel Corona**, independent AI architect and consultant. The lab spans 30 years of software and information systems work, from industry and as a university professor, with a PhD in information technologies.

## How the work is done

| Principle | In practice |
|---|---|
| Gold sets frozen before any experiment | Every comparison uses the same frozen set (with hashes), so a change in the score comes from the change being tested |
| Verification by execution, not by eye | SQL is run and result sets are compared. Agent tasks are checked against the database. LLM judges are validated on known failures before they are used |
| Evals gate every pull request | GitHub Actions runs the evals on each PR. Thresholds come from a fixed calibration rule, and their false-alarm rate is measured ([example](semana-13/resultados/ci_calibracion.md)) |
| Security is a hard requirement, tested in CI | Zero unapproved writes, zero leaks across roles and tenants, and zero obeyed injected instructions. Any failure breaks the PR |
| Cost and latency next to quality | Every result reports cost per query (USD) and p50 latency, with prices taken from the official pricing pages |
| Negative results are reported | Techniques that did not beat the baseline (hybrid search, HyDE, query rewriting, contextual retrieval, fine-tuning) are documented and **not adopted** |
| Every number links to its evidence | Results files under `resultados/`, plus the PR that verified each claim |

## Key results

| Capability | Result | Evidence |
|---|---|---|
| **Agent vs workflow** (84 tasks, k = 3) | Claude Agent SDK agent: pass@1 **0.889**. Fixed-routing workflow: **0.504** (+0.385, 95% CI [0.282, 0.496]). The agent wins on business rules, compound tasks and ambiguous requests. The workflow ties on direct questions at a fraction of the cost ($0.0004 vs $0.0018 per task) | [`semana-13`](semana-13/README.md) |
| **Agent security** | **140/140** runs: unchanged table fingerprints, proposals kept in `PENDING_APPROVAL`, 0 leaks, 0 injected instructions obeyed | [`semana-13/resultados/seguridad.md`](semana-13/resultados/seguridad.md) |
| **Text-to-SQL on a legacy schema** | With the data dictionary: execution accuracy **0.977 ES / 1.000 EN** (same as on the original schema), **$0.00033 per question** (Haiku). Without it: 0.884 / 0.953 | [`semana-10`](semana-10/README.md) |
| **Integrated assistant** (SQL + documents) | Accuracy 0.961 ES / 0.980 EN with citations, vs 0.294 SQL-only and 0.608 documents-only. $0.00083 per question, p50 5.3 s. 0 writes, leak 0 in 128 cases, 0/48 injected instructions obeyed | [`semana-10`](semana-10/README.md) |
| **Retrieval** | Reranking raises nDCG@10 from 0.904 to **0.982** (ES) and from 0.885 to **0.974** (EN). Hybrid BM25 + vector search does not help and is not adopted | [`semana-08`](semana-08/README.md) |
| **Multi-tenant RAG** | Tenant and role filters inside the query on pgvector, Qdrant and OpenSearch: **leak 0**, checked in CI | [`semana-09`](semana-09/README.md) |
| **RAG evaluation** | Separate retrieval and generation suites. RAGAS metrics are validated on known failures before use. $0.28 per CI run | [`semana-11`](semana-11/README.md) |
| **Managed RAG** (AWS and Google Cloud) | Bedrock Knowledge Bases and Vertex AI Search compared with the own pipeline on the same gold set. Cost from $0.00027 to $0.0012 per query, leak 0 in 672 queries, keyless CI through OIDC federation, all resources deleted afterwards | [`semana-12`](semana-12/README.md) |
| **Remote MCP server with OAuth** | MCP 2026-07-28 over Streamable HTTP; Keycloak as authorization server (PKCE, RFC 8707 audience); least privilege in three layers (scopes, filtered catalogs, a PostgreSQL role per profile). 13/13 threats covered. Tool poisoning: **38/38** with client defenses (without them, shadowing captured 100% of queries). Agent over HTTP + OAuth: same success and cost as in-process, +7 ms per tool call, 0/8 leaks for roles without the scope | [`semana-14`](semana-14/README.md) |
| **Same agent in four frameworks** | LangGraph and Strands score **0.900 / 0.900** on 40 tasks with identical failures and **38/38** poisoning cases each, through an MCP gateway; OpenAI Agents SDK and Google ADK 0.950 on 20. The framework does not change quality; it changes cost (ADK +53% from full MCP results), protocols, observability and hosting. Multi-agent over A2A (Keycloak audience per agent) ties the single agent at 1.7× cost and 3× latency. On Bedrock AgentCore: same 1.000, cold start 5.7 s. A [client decision matrix](semana-15/resultados/matriz_decision.md) links every score to its evidence | [`semana-15`](semana-15/README.md) |
| **Client plugin with its own eval** | [`legacy-schema-audit`](semana-16/legacy-schema-audit/README.md) 1.0.0, installable from this repo's marketplace: a read-only audit of a legacy schema (dictionary, ER diagram, risks with SQL evidence, executive summary). With Sonnet: PK/FK/PII 1.00 and **12 of 13** seeded risks for ~$1; behavior suite **Δ +0.57** over no plugin; security **14/14** (injection, data changes, credentials, hook bypass, tool poisoning). Browser agent and computer use spikes on a legacy screen: 10/10 fields. CI runs a mini eval with calibrated thresholds on every PR (~$0.11) | [`semana-16`](semana-16/README.md) |
| **Agent reliability in production** | One task is one OpenTelemetry GenAI trace (agent, model, MCP client and server, SQL) in a self-hosted Langfuse, through a Collector that redacts by **allowlist** (0 of 9 canaries with content capture off and on). Budgets per task, session and tenant-day (**0 caps crossed** in 84 paid tasks); input, tool and output guardrails (**0 obeyed** in 38 attacks, false positives measured on 84 tasks); human approval of purchase orders with an approver level from Keycloak (**0 orders without approval**); trajectory eval read from the spans (91.7 %) with scores in Langfuse; a dashboard as code and a runbook. CI runs a mini eval with calibrated thresholds on every PR (~$0.08) | [`semana-17`](semana-17/README.md) |

## LegacyBridge: the reference system

LegacyBridge is the case study that runs through the lab. A company keeps its inventory, sales and purchasing in a legacy PostgreSQL schema:
- **Cryptic names:** tables such as `artmst` and `exidet` and columns such as `art_ptr`.
- **Business rules** that live in documents, not in the database.
- **Users** with different roles (warehouse, sales, purchasing) and tenants.

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

## Repository map

Folders are named `semana-NN` (week NN). Each week has its own `README.md` with method, results, cost and decisions.

| Area | Weeks | What you will find |
|---|---|---|
| LLM fundamentals | [1](semana-01/README.md) · [2](semana-02/README.md) · [3](semana-03/README.md) · [4](semana-04/README.md) | Mini-GPT in MLX; token cost and sampling variability by language; a documented *don't fine-tune* decision (LoRA vs prompt); local quantized inference vs API (the API is about 13× faster at p50) |
| Prompts and evals | [5](semana-05/README.md) · [6](semana-06/README.md) · [7](semana-07/README.md) | Versioned prompt library; regression evals as a required PR check; bilingual NLQ measured by execution |
| RAG and data | [8](semana-08/README.md) · [9](semana-09/README.md) · [10](semana-10/README.md) · [11](semana-11/README.md) · [12](semana-12/README.md) | Chunking, embeddings and vector DBs; advanced RAG and multi-tenancy; legacy schema, PDFs, OCR and images; RAG evaluation; managed RAG on AWS and Google Cloud |
| Agents and MCP | [13](semana-13/README.md) · [14](semana-14/README.md) · [15](semana-15/README.md) · [16](semana-16/README.md) · [17](semana-17/README.md) | Agentic patterns and the Claude Agent SDK; remote MCP server with OAuth, least privilege and tool-poisoning tests; the same agent in LangGraph, Strands, OpenAI Agents SDK and Google ADK, multi-agent with A2A, Bedrock AgentCore, and a client decision matrix; a Claude Code plugin for clients with its own eval, browser and computer use spikes; reliability in production: tracing, budgets, guardrails, human approval, trajectory eval and a trace dashboard |

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

uv run python -m pytest -q semana-13/tests semana-14/tests        # tools, guard, permissions, MCP server
uv run python semana-14/linea_base/verificar_sdk.py               # MCP SDK baseline against the spec
```

Evals that call a model need `ANTHROPIC_API_KEY`. Each one prints its estimated cost, and most CI runs cost between $0.10 and $0.30.

## Status

| Phase | Weeks | Status |
|---|---|---|
| 1. LLM fundamentals | 1–4 | Complete |
| 2. Prompts, evals and NLQ | 5–7 | Complete |
| 3. RAG and data | 8–12 | Complete, with all 11 exit criteria verified |
| 4. Agents, MCP and orchestration | 13–18 | In progress: weeks 13 to 17 complete (exit criteria 13, 14, 15, 16 and 17 verified) |

The detailed exit criteria for each phase, with the PR that verified each one, are kept in [README.es.md](README.es.md).

## Security and credentials

- No credentials live in the repository. Cloud access uses CLI sessions and OIDC federation, and API keys exist only as GitHub secrets.
- To report a vulnerability, see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE). All data is synthetic (seed 42), and no customer data is used.
