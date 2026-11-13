# Phase 5 · Week 19: AWS reference architecture for LegacyBridge, deployed with IaC

Repo: `mcorona/genai-engineering-lab`. Folder: `semana-19/`. Each activity closes with a PR, green checks and a merge
before moving on to the next. Documentation goes in separate PRs. Week 18 is the CCAR-P exam review (no code), so this
plan builds on weeks 10 to 17.

- **Topic:** the AWS reference architecture for a GenAI agent:
  - **Amazon Bedrock:** models and inference profiles, Guardrails, Knowledge Bases, Agents and AgentCore, Prompt
    Management, and model evaluation;
  - **compute and integration:** Lambda, Step Functions and API Gateway;
  - **security:** IAM, VPC endpoints (PrivateLink) and KMS;
  - **infrastructure as code:** CDK or Terraform, chosen in activity 2 with criteria, not by habit.
- **Practice:** **deploy LegacyBridge with IaC in Manuel's AWS account, keeping it inside the free tier and credits**.
  - The week 13 agent and its tools run behind an authenticated HTTPS API.
  - The week 17 human-in-the-loop approval becomes a Step Functions workflow.
  - The week 17 guardrails become a Bedrock Guardrail plus the deterministic layer.
  - The legacy schema lives in a private database that is reachable only from inside the VPC.
  - The whole thing comes up and goes down with one command each, and an inventory proves nothing is left.
- **Criterion 19 (root README):** LegacyBridge deployed on AWS from IaC, with:
  - a reference architecture diagram;
  - least-privilege IAM;
  - KMS encryption at rest;
  - private networking through VPC endpoints;
  - a Bedrock Guardrail and versioned prompts;
  - the golden mini eval passing against the deployed endpoint;
  - measured cost per query;
  - a verified teardown.
- **Why it matters for clients:** a client asks "can this run in **our** AWS account, under **our** controls?". The
  answer is a repo they can review: IaC that passes their security scanners, a diagram that matches the code, a cost
  model with measured numbers, and a teardown they can trust. It is also the core of the AIP-C01 exam (domains D1 to D3)
  and of the Phase 5 deliverable: "LegacyBridge in production with architecture diagram, public IaC, security and cost
  reports".

## Phase 5 · LLMOps and multicloud production (weeks 19–24)

**Goal of the phase:** take LegacyBridge from demo to production **in the client's cloud**, with IaC, security,
monitoring and controlled costs. The phase closes with the **AWS Certified Generative AI Developer – Professional
(AIP-C01)** exam.

| Week | Topic | Practice | What week 19 must leave ready for it |
|---|---|---|---|
| **19** | AWS reference architecture: Bedrock (models, Guardrails, Knowledge Bases, Agents/AgentCore, Prompt Management, model evaluation), Lambda, Step Functions, API Gateway, IAM, VPC endpoints, KMS; IaC with CDK or Terraform | Deploy LegacyBridge with IaC in the AWS account (free tier) | This plan |
| 20 | Costs and performance: prompt caching, batch, model routing (Cascada), provisioned throughput, CloudWatch and X-Ray | Cost-per-query dashboard and budget alarm | `proyecto` and `componente` tags activated as cost allocation tags. The span schema already emitted as structured logs, so X-Ray and CloudWatch only add exporters. The model call behind **one interface** (`modelo.invocar`), so a router or Cascada can replace it without touching the agent. The per-task token and cost record of activity 8 as the baseline the week 20 optimizations are measured against. The cost model (activity 2) with a measured error |
| 21 | Security: OWASP Top 10 for LLM, direct and indirect prompt injection, exfiltration, PII, red teaming with garak or PyRIT | LegacyBridge red teaming report with findings and mitigations | The deployed API as a red-team target (one command up, one down). The threat model and trust boundaries (activity 9). The Guardrail and deterministic layer measured separately, so week 21 can attribute each block. The poisoning cases already inside the data and the KB |
| 22 | Equivalents in Azure (Microsoft Foundry) and Google (Vertex AI / Gemini) | AWS ↔ Azure ↔ GCP service matrix + minimal deployment in a second cloud | **Ports and adapters:** the agent and its tools depend on 4 small interfaces (model, guardrail, prompt store, retrieval), with AWS adapters only in week 19. The IaC is split per layer (foundation, data, AI, compute), so each layer maps to a row of the matrix. The week 12 Vertex AI Search work is the head start for GCP |
| 23–24 | AIP-C01 prep by domain: D1 FM integration and data 31%, D2 implementation 26%, D3 security and governance 20%, D4 efficiency 12%, D5 testing and troubleshooting 11% | Labs per domain + 3 full practice exams at ≥ 85% before booking | Every activity of week 19 is tagged with its AIP-C01 domain (see each activity), and `resultados/aip_c01.md` keeps a running list: concept → where the lab shows it → evidence. Weeks 23–24 turn it into labs |

- **Phase deliverable:**
  - LegacyBridge **in production** with an architecture diagram;
  - public IaC;
  - a security report (week 21);
  - a cost report (week 20).
- **Phase exit criterion:** pass AIP-C01 (target: week of 3 May 2027) **and be able to quote a client's monthly
  infrastructure within ±20%**.
- **What "production" means in this phase.** Two IaC profiles from the same code:
  - **`lab`:** one AZ for endpoints, no deletion protection, short retention, smallest classes. It is **deployed**
    and torn down every session (weeks 19–21).
  - **`prod`:** 2 AZs, deletion protection, backups, longer retention, alarms, WAF in front of a REST API, and
    provisioned options documented. In week 19 it is **synthesized, scanned and priced, not deployed**.

  The phase deliverable uses a short, authorized `prod` window (for the demo and its evidence), scheduled in week 20
  or 21 once the cost dashboard and alarms exist.
- **The ±20% quote starts here.**
  - Activity 2's cost model predicts the cost per hour and per query.
  - Activity 8 measures the real cost.
  - `resultados/cotizacion.md` records predicted vs real and the error.
  - Every later week of the phase adds a row, so by week 24 the error is measured, not claimed.
  - The model also takes client parameters (queries per day, tokens per query, hours up, AZs), so it can produce a
    monthly quote for the `prod` profile.
- **Phase-level criteria (root README):** one verifiable criterion per week (19 to 22), plus two cross-cutting ones:
  - **cost:** the quote error, measured;
  - **security:** no unsuppressed scanner finding and no public resource except the API, checked every week.

  The same pattern as the Phase 4 criteria.

## What is reused from weeks 10 to 17

- **AWS practice (weeks 12 and 15):**
  - region `us-east-1`;
  - an admin profile for creating things and an operator profile for running them (`aws login`), with no access keys;
  - per-week prefixes and a `proyecto` tag on every resource;
  - a budget with email alerts;
  - dry run by default;
  - inventory before and after, with `"quedan": "nada"` as the teardown proof;
  - prices from the Price List API (`semana-12/infra/precios.py`);
  - real cost from Cost Explorer (`semana-12/infra/costo_real.py`);
  - the GitHub OIDC pattern for CI without keys (`semana-12/infra/aws_ci_oidc.sh`).
- **Measured facts that shape this week:**
  - Bedrock Knowledge Bases on **S3 Vectors** (no hourly minimum, unlike OpenSearch Serverless);
  - Claude Haiku 5.5 had **quota 0** on this account on 2026-10-28, while Haiku 4.5 worked through the `us.` profile;
  - AgentCore Runtime: cold start of 5.7–5.9 s, about 35 s to `READY`, and the AgentCore CLI leaves a CDK bootstrap
    behind (week 15 used boto3 to avoid that).
- **The agent and its evaluation:**
  - the week 13 loop agent and its tools (`describir_esquema`, `ejecutar_sql` read-only, `proponer_orden_compra`
    writing `PENDING_APPROVAL`);
  - the 84 golden tasks with execution-based verification and the 10-per-language CI subset;
  - the read-only guard (sqlglot parsing, `comun.check_read_only`).
- **Week 17 reliability, to port and not rewrite:**
  - the budgets;
  - the deterministic guardrail layer;
  - the approval state machine (request → approve, reject or expire) with a distinct approver role;
  - the trajectory graders;
  - the locked OpenTelemetry GenAI span schema (week 20 sends it to CloudWatch and X-Ray).
- **Week 14 security model:**
  - a user token with scopes;
  - a database role per profile;
  - the poisoning cases.

## Default decisions

- **One region, one AZ for paid endpoints.** Everything goes in `us-east-1`. The subnets span 2 AZs where a service
  requires it (RDS subnet group), but interface endpoints are created in **one AZ** only, because they are billed per
  AZ-hour. This is a lab trade-off and is written down as such; production would use 2 or 3 AZs.
- **No NAT gateway.** Lambdas inside the VPC reach AWS services through VPC endpoints:
  - **gateway endpoints** for S3 (and DynamoDB if it is used), which are free;
  - **interface endpoints** only for what the code actually calls: `bedrock-runtime`, and `states` if a Lambda inside
    the VPC calls Step Functions.

  Each interface endpoint has to justify its hourly cost in the ADR. Anything that does not need the database runs
  **outside** the VPC.
- **Database: RDS for PostgreSQL**, on the smallest free-plan-eligible class:
  - private subnets, no public access;
  - encrypted with the customer managed KMS key;
  - **IAM database authentication**, so no secret to rotate and no Secrets Manager endpoint;
  - loaded with the CI synthetic seed (42) and the `legado` schema;
  - a read-only role for the agent and a separate role for `proponer_orden_compra`.

  Aurora Serverless v2 with scale to zero and the RDS Data API are documented as alternatives in the ADR (activity 2
  measures their price; the Data API would remove the need for a VPC, which defeats the VPC endpoint part of the
  syllabus).
- **API:** API Gateway **HTTP API** with a **JWT authorizer** over an **Amazon Cognito** user pool:
  - groups `analista` and `aprobador`, mapped to the week 14 scopes;
  - throttling;
  - CORS off;
  - no API keys.

  REST API features (usage plans, WAF, request validation) are documented as the production option. Keycloak stays on
  the Mac; Cognito is the AWS-native equivalent.
- **Compute:**
  - **Lambda** (Python 3.13, arm64) for the agent loop with the Bedrock **Converse API** and tool use, and for the
    tools;
  - **Step Functions Standard** for `proponer_orden_compra` → wait for approval (`.waitForTaskToken`) → write or
    expire, with a timeout;
  - Lambda concurrency capped per function, so a loop cannot run up a bill.
- **Bedrock, all declared in the IaC:**
  - **models:** a Claude model through a cross-region inference profile (whichever has quota, checked in activity
    1), plus embeddings for the KB;
  - **Guardrails:** the week 17 rules (content filters, prompt attack, denied topics, PII masking, word filters),
    versioned, attached to every Converse call;
  - **Knowledge Bases:** the legacy data dictionary (tables, columns, meanings from the week 16 audit) on S3
    Vectors, so `describir_esquema` can answer "what does `cve_art` mean";
  - **Prompt Management:** the system prompt and the tool instructions as versioned prompts; the Lambda pins a
    version;
  - **AgentCore Gateway:** the tools Lambda exposed as MCP tools, so the same tools serve the Lambda agent and any
    MCP client. AgentCore Policy, if available in the region, enforces the scopes. **Bedrock Agents** (action groups)
    is built only as a documented comparison, not deployed;
  - **model evaluation:** one small Bedrock evaluation job (LLM as a judge) on a subset of the golden tasks, compared
    with the lab's own execution-based verifier.
- **KMS:** one customer managed key with a key policy that names the roles that may use it. It encrypts:
  - the S3 buckets, RDS, the CloudWatch log groups, Step Functions, the Lambda environment, the Bedrock Guardrail
    and the KB.

  Rotation is on. Teardown schedules the key for deletion with the minimum window (activity 1 verifies how a key
  pending deletion is billed).
- **IaC tool:** chosen in activity 2 on a spike.
  - **Default: AWS CDK in Python:**
    - the same language as the rest of the lab;
    - `cdk-nag` (AwsSolutions pack) for security checks;
    - L2 constructs for most services, and an alpha L2 for AgentCore if it is mature;
    - the AIP-C01 exam leans on CloudFormation and CDK.

    Its cost is the bootstrap stack (an S3 bucket, an ECR repository and roles). It is created with a custom
    qualifier and toolkit stack name, and removed by the teardown.
  - **Alternative: Terraform** with local state:
    - nothing is left in AWS besides the resources;
    - `checkov` or `tfsec` for scans.

    It is taken if the spike shows the CDK constructs for Bedrock or AgentCore are missing or unstable.
- **Ephemeral by default.** The stack exists only while it is used:
  - `desplegar` → eval → `destruir` in the same session;
  - nothing stays up overnight, except a stateless stack that costs $0 per hour (for example a stack with only IAM,
    KMS and budget, if the key cost is acceptable).
- **Spend controls, before anything paid:**
  - an AWS Budget for the week, with alerts at 50% and 100% actual and 100% forecast;
  - a **budget action** that attaches a deny policy to the deploy role at 100%;
  - Cost Anomaly Detection on;
  - every paid run estimated first and authorized by Manuel, with a cap;
  - the real cost read from Cost Explorer after the run (it lags up to 24 h).
- **CI never deploys.** CI runs:
  - `cdk synth` (or `terraform validate` and `plan` against a mocked provider);
  - the security scanners;
  - IAM policy validation with Access Analyzer `validate-policy` (no resources, $0);
  - the unit tests with mocked AWS (moto or botocore Stubber).

  Deploys happen from the Mac, by Manuel, with the admin profile.

## Preparation (before activity 1)

| Item | Where |
|---|---|
| This plan committed as `semana-19/Fas5Sema19.md` (this file is the source) | PR "Semana 19: plan y preparación" |
| A `semana19` dependency group, locked: `aws-cdk-lib`, `constructs`, `cdk-nag`, `boto3`, `moto`, `pytest` (exact pins chosen in activity 1); Node LTS and the `aws-cdk` CLI pinned in `preparar/versiones.json` | `pyproject.toml`, `uv.lock`, `semana-19/preparar/versiones.json` |
| A readiness check ($0): the CLI tools and versions (aws, node, cdk, terraform if used), the `semana19` admin and operator profiles signed in, the caller identity and region, no `ANTHROPIC_API_KEY` needed, the week 13 golden tasks and seed present | `semana-19/preparar/verificar_entorno.py` |
| **Bedrock quota request (takes days):** a Service Quotas request for the chosen Claude model's on-demand tokens and requests per minute in `us-east-1`, if activity 1 confirms it is still 0. Model access (EULA) accepted by Manuel in the console | Manuel, console |
| Budget for the week (`semana19`, $5 per month, alerts to Manuel's email from the environment, not versioned) created by a script with dry run | `semana-19/infra/presupuesto.py` |
| `semana-19/**` in the paths of the required `regresion` check | `.github/workflows/evals-semana-06.yml` |
| `eval-semana-19` workflow without AWS ($0): synth, nag, policy validation, tests. Each activity adds its tests | `.github/workflows/eval-semana-19.yml` |
| Ignored: `cdk.out/`, `.terraform/`, `*.tfstate*`, `semana-19/**/.secretos.env` | `.gitignore` |

## Dependencies and parallel work

```
1 baseline ──► 2 architecture + IaC choice ──► 3 foundation (KMS, VPC, endpoints, IAM, budget)
                                                   │
                         ┌─────────────────────────┼──────────────────────────┐
                         ▼                         ▼                          ▼
                    4 data (RDS, KB)      5 Bedrock (Guardrail, prompts)   6 compute (Lambda, API, Step Functions)
                         └─────────────────────────┼──────────────────────────┘
                                                   ▼
                                    7 AgentCore Gateway (+ Bedrock Agents compared)
                                                   ▼
                                    8 eval against the deployed endpoint + Bedrock evaluation
                                                   ▼
                                    9 security and compliance review ──► 10 CI, README, criterion 19
```

| Can start right after activity 1 | Part | Needs |
|---|---|---|
| 5 | Port the week 17 guardrail rules to a Guardrail definition (as code), and the prompts to Prompt Management templates. Unit tests on synth output | Week 17 `guardrails/` and the week 13 prompts |
| 6 | The Lambda handlers (agent loop on Converse, tools, approval callback), tested locally with a stubbed Bedrock client and the lab PostgreSQL | Week 13 agent and tools, week 17 approval state machine |
| 9 | The threat model (STRIDE over the diagram) and the scanner configuration | Activity 2 diagram |

What must wait: anything deployed (3 first), the eval against the endpoint (4 to 7), and the README (last).

## Activities

### 1. Baseline: the account, the services and the prices
- Verify, with versions pinned and dates recorded, and mark each item M (measured), D (documented) or N (not
  verified):
  - **the account:**
    - the plan (free plan or paid);
    - the remaining credits and their expiry (Billing / Free Tier API);
    - which services the plan allows;
    - the current spend this month;
  - **Bedrock in `us-east-1`:**
    - which Claude models and inference profiles are accessible;
    - the on-demand quotas (tokens and requests per minute) for each;
    - Guardrails, Knowledge Bases on S3 Vectors, Prompt Management, model evaluation jobs, Bedrock Agents;
    - AgentCore Gateway, Runtime and Policy: availability and pricing units;
  - **list prices from the Price List API:**
    - Lambda, Step Functions Standard, API Gateway HTTP API, Cognito;
    - RDS for PostgreSQL (smallest class), and the price of Aurora Serverless v2 at 0 ACU;
    - interface VPC endpoints (per AZ-hour and per GB), public IPv4 per hour;
    - KMS keys (including a key pending deletion), CloudWatch Logs, S3 Vectors;
    - the chosen Claude model and the embeddings model;
    - which items have a free tier or are covered by credits;
  - **the tools:**
    - the AWS CLI and `aws login`;
    - Node LTS;
    - the CDK CLI and `aws-cdk-lib`, and whether an AgentCore and Bedrock L2 exists and how mature it is;
    - `cdk-nag`;
    - Terraform and the AWS provider version, and whether `aws_bedrockagentcore_*` and `aws_bedrock_guardrail`
      resources exist;
    - `checkov`.
- An **inventory script** (`infra/inventario.py`) that lists, by the `proyecto=semana19` tag and by name prefix:
  - stacks, roles, keys, VPC parts, endpoints, Lambdas, state machines, APIs, user pools, DB instances, buckets,
    vector buckets, KBs, guardrails, prompts, gateways and log groups.

  It runs before anything is created and must report 0.
- **Deliverable:** `resultados/linea_base.md` (matrix and prices table with catalog ids) and
  `linea_base/verificar.py` ($0 checks).
- **AIP-C01:** D1 (modelos, inference profiles, cuotas) y D3 (gobernanza: presupuesto, Free Tier, créditos)
- **Time:** ~1.5 h. **Cost:** $0 (read-only API calls).

### 2. Reference architecture and the IaC decision
- **Diagram** (Mermaid in the repo, exported to SVG): client → API Gateway (JWT, Cognito) → agent Lambda → Bedrock
  (Converse with Guardrail, prompt version) and the tools. The tools are reached either directly or through
  AgentCore Gateway → tools Lambda in the VPC → RDS (IAM auth). `proponer_orden_compra` goes to Step Functions →
  approval by an `aprobador` user → write. KB on S3 Vectors. KMS on everything at rest. VPC endpoints. CloudWatch
  Logs.
- **ADRs** (one page each, with the alternatives and the reason):
  - CDK vs Terraform;
  - HTTP API vs REST API;
  - RDS vs Aurora Serverless v2 vs Data API;
  - Lambda agent vs AgentCore Runtime vs Bedrock Agents;
  - which interface endpoints and why;
  - one AZ for endpoints in the lab.
- **The IaC spike:** the same tiny stack (KMS key + encrypted bucket + a role) written in CDK and in Terraform.
  - Measure, at $0 (synth and plan only): the lines of code, what the scanner reports, how each tool expresses the
    Guardrail and the KB (L1 vs L2 vs missing), and what the bootstrap leaves in the account.
  - Then pick one.
- **Cost model:** a script (`costos/modelo.py`) that takes the activity 1 prices and gives two figures:
  - (a) the cost per hour of the stack while it is up, item by item;
  - (b) the cost per query (model tokens from the week 13 per-task distribution, Lambda, API, Step Functions).

  The output is the estimate Manuel authorizes before activity 3.
- **Deliverable:** `arquitectura/` (diagram, ADRs), `resultados/arquitectura.md`, `costos/modelo.py` with tests.
- **AIP-C01:** D2 (IaC e implementación) y D3 (arquitectura de seguridad: IAM, KMS, endpoints privados)
- **Time:** ~2 h. **Cost:** $0.

### 3. Foundation stack: KMS, VPC, endpoints, IAM and spend controls
- **KMS:** a customer managed key, rotation on, and a key policy limited to the account root plus the named roles.
- **VPC:**
  - 2 private subnets, no internet gateway and no NAT;
  - the S3 gateway endpoint;
  - interface endpoints only per the ADR, in one AZ, with private DNS and their own security group (HTTPS from the
    Lambda SG only);
  - VPC Flow Logs to an encrypted log group with short retention.
- **IAM:**
  - one role per function, with permissions scoped to its own resources;
  - a **permission boundary** on every role the stack creates;
  - no `*` on actions or resources except where AWS requires it (documented);
  - the deploy role is the only one that can create roles, and only with the boundary attached.
- **Spend controls:**
  - the budget action (deny policy on the deploy role at 100%);
  - Cost Anomaly Detection;
  - the log retention on every group.
- `infra/desplegar.sh` and `infra/destruir.sh`:
  - dry run by default;
  - `--si` to act;
  - teardown includes the CDK bootstrap (or the Terraform state);
  - teardown schedules the KMS key for deletion and runs the inventory, which must report `"quedan": "nada"`, except
    the budget and the key pending deletion, both listed explicitly.
- **Tests:**
  - synth or plan snapshot;
  - `cdk-nag` (or `checkov`) with zero unsuppressed findings, each suppression with a written reason;
  - every role has the boundary;
  - every encryptable resource uses the key;
  - no security group allows `0.0.0.0/0` inbound.
- One real deploy and teardown, measured: the time to `CREATE_COMPLETE`, the time to delete, the inventory after,
  and the real cost from Cost Explorer the next day.
- **AIP-C01:** D3 (IAM con permission boundary, KMS, VPC sin internet, endpoints, controles de gasto) y D2 (despliegue reproducible)
- **Time:** ~2.5 h. **Cost:** cents (endpoint hours while up), estimated and authorized first.

### 4. Data: RDS with the legacy schema, and the Knowledge Base
- **RDS for PostgreSQL:**
  - smallest eligible class;
  - single AZ;
  - encrypted with the key;
  - no public access;
  - IAM authentication;
  - automated backups at the minimum;
  - deletion protection off only in the lab (documented).
- **Loading the data:** a one-shot Lambda inside the VPC (or a Step Functions task) loads the CI seed (42), the
  `legado` schema and `artnot.sql`, and creates:
  - `copilot_ro` (read-only, `default_transaction_read_only`, `search_path = legado`);
  - the order-writer role, used only by the approval step.

  No SQL runs from the Mac against a public endpoint.
- **Knowledge Base:**
  - the legacy data dictionary (from the week 16 audit and the `legado` views) as documents in an encrypted S3
    bucket;
  - S3 Vectors as the store;
  - Titan Text Embeddings V2 (the cheaper of the week 12 two, unless activity 1 says otherwise);
  - the ingestion job declared in the IaC.
- **Tests:**
  - the loader is idempotent;
  - `copilot_ro` cannot write (an `INSERT` fails);
  - the agent role cannot connect as the writer;
  - a `Retrieve` for 5 column-meaning questions returns the right document (recall@5 measured);
  - no tenant leakage on the week 12 style filter, if tenants are used.
- **AIP-C01:** D1 (Knowledge Base sobre S3 Vectors, recuperación) y D3 (RDS con autenticación IAM, rol de solo lectura)
- **Time:** ~2 h. **Cost:** cents (DB hours while up, embeddings for a few KB of text).

### 5. Bedrock: model access, Guardrail and Prompt Management as code
- **Model:**
  - the inference profile ARN chosen in activity 1, in a single config value;
  - the Lambda role may invoke **only** that profile and its underlying model ARNs.
- **Guardrail**, versioned, ported from week 17:
  - content filters;
  - prompt attack on input;
  - denied topics (for example, writes outside `proponer_orden_compra`);
  - PII: mask emails and phones and block tax IDs in outputs;
  - word filters for DSNs and keys;
  - contextual grounding where it applies.

  The deterministic week 17 layer stays in the Lambda: the Guardrail is defense in depth, not a replacement.
- **Prompt Management:** the system prompt (ES and EN) and the tool instructions as prompts with variables. The
  Lambda reads a **pinned version** at cold start and caches it. Changing the prompt is a new version and a config
  change, not a code change.
- **Tests:**
  - **offline (stubbed):** the Converse request carries the guardrail id and version and the pinned prompt version;
  - **live (small, authorized):**
    - the Guardrail's block rate on the week 13 and 14 attack cases;
    - its false positives on the 20 CI golden tasks, compared with the week 17 deterministic layer on the same
      cases (`ApplyGuardrail`, no model generation needed);
  - record the cost per `ApplyGuardrail` call from the bill.
- **AIP-C01:** D1 (Prompt Management con versiones fijadas) y D3 (Guardrails como capa de defensa en profundidad)
- **Time:** ~2 h. **Cost:** cents (`ApplyGuardrail` text units), authorized first.

### 6. Compute: the agent Lambda, the API and the approval workflow
- **Agent Lambda:**
  - the week 13 loop on the Bedrock Converse API with tool use;
  - the week 17 budgets (tokens, steps, wall time) enforced in code;
  - the OpenTelemetry span schema kept, exported to CloudWatch Logs for now (week 20 adds X-Ray);
  - reserved concurrency capped;
  - timeout below the API Gateway integration limit.
- **Tools Lambda** (inside the VPC):
  - `describir_esquema` (DB catalog plus KB);
  - `ejecutar_sql` (sqlglot read-only guard, then `copilot_ro` over IAM auth, row limit, statement timeout);
  - `proponer_orden_compra` (starts the state machine, returns the request id).
- **Step Functions Standard:**
  - writes the `PENDING_APPROVAL` request;
  - waits for the task token with a timeout (expire);
  - the approval API route, for the `aprobador` group only, sends success or failure;
  - the write step uses the writer role;
  - every transition is logged;
  - the execution history is the audit trail.
- **API Gateway HTTP API:**
  - `POST /consultas` (`analista`), `POST /aprobaciones/{id}` (`aprobador`), `GET /consultas/{id}`;
  - JWT authorizer on Cognito;
  - throttling;
  - access logs to an encrypted group.
- **Cognito:**
  - a user pool with the two groups;
  - two test users created by a script with random passwords that are never printed.

  Activity 8 uses them through the OAuth flow the pool supports. Self-sign-up is off.
- **Tests:**
  - handlers with stubbed Bedrock and moto;
  - an `analista` token cannot approve;
  - an expired approval does not write;
  - a token without the scope gets 403;
  - the read-only guard blocks the week 13 write attempts before the DB;
  - the API rejects requests without a token.
- **AIP-C01:** D2 (implementación: Lambda, Step Functions, API Gateway con autorizador JWT)
- **Time:** ~3 h. **Cost:** $0 offline. Live checks in activity 8.

### 7. AgentCore Gateway over the tools, and Bedrock Agents as a comparison
- **AgentCore Gateway:**
  - a gateway target for the tools Lambda, with its tool schemas;
  - inbound auth with the Cognito pool (JWT);
  - outbound with the gateway's IAM role;
  - AgentCore Policy (Cedar) enforcing that only `aprobador` reaches the approval tool, if Policy is available
    (activity 1).

  The agent Lambda can call tools either directly or through the gateway as an MCP client (config flag), so the two
  paths are measured on the same tasks.
- **Bedrock Agents (comparison only):** the same tools as an action group. It is created from the IaC in a separate
  stack, the 10 ES tasks are run once, and the stack is torn down. Compare:
  - success;
  - latency;
  - cost;
  - how much of the week 13 to 17 control (budgets, guard, trajectory) survives;
  - what you cannot see in the trace.
- **Deliverable:** `resultados/agentes.md`, a 3-way table: Lambda loop, Lambda through AgentCore Gateway, Bedrock
  Agents. The decision for LegacyBridge is written with its reason.
- **AIP-C01:** D1 (integración de agentes y herramientas) y D2 (AgentCore Gateway y Policy)
- **Time:** ~2.5 h. **Cost:** cents to about a dollar (model tokens of 3 × 10 tasks + gateway calls), estimated and
  authorized first.

### 8. Evaluation against the deployed endpoint, and Bedrock model evaluation
- **Mini eval through the public API:**
  - the 10 + 10 CI golden tasks;
  - real Cognito tokens;
  - the same execution-based verifier as week 13.

  Report:
  - success with a 95% CI;
  - the trajectory graders from week 17;
  - p50 and p95 latency (cold and warm Lambda separately);
  - tokens and cost per task.

  Compare with the week 13 and 17 local results on the same tasks. The regression rule is the week 10 threshold
  rule.
- **Approval end to end:** one task that proposes an order. Check that:
  - the state machine waits;
  - the `analista` cannot approve;
  - the `aprobador` approves;
  - the row is written by the writer role;
  - an expired request writes nothing.
- **Bedrock model evaluation job:**
  - a small evaluation job (LLM as a judge, built-in metrics such as correctness and faithfulness) on the saved
    answers of the 20 tasks;
  - compare its verdicts with the execution-based verifier: agreement, false passes, false fails.

  The point is to show where an LLM judge is and is not enough for SQL answers.
- **Real cost:** Cost Explorer by the `proyecto` tag (activated as a cost allocation tag in preparation), per
  service, the day after. Cost per query = real cost / queries, compared with the activity 2 model.
- **Deliverable:** `resultados/eval_aws.md`, `resultados/costo_real.md`.
- **AIP-C01:** D5 (pruebas y diagnóstico: evaluación contra el endpoint) y D4 (eficiencia: costo por consulta)
- **Time:** ~2.5 h. **Cost:** about $1 to $3 (model tokens for 20 tasks and the judge, plus the hours the stack is
  up), estimated and authorized first, with a hard cap in the eval script.

### 9. Security and compliance review
- **Threat model:** STRIDE over the diagram, one row per trust boundary, each with the control and the test that
  proves it:
  - the user and the API;
  - the API and the Lambda;
  - the Lambda and Bedrock;
  - the Lambda and RDS;
  - the gateway and the tools;
  - the approver.
- **Scans:**
  - `cdk-nag` / `checkov` with zero unsuppressed findings;
  - IAM Access Analyzer `validate-policy` on every policy document (no errors or security warnings);
  - Access Analyzer **unused access** and external access findings on the deployed account (read the findings,
    archive or fix);
  - the secret scan over the repo and over `cdk.out`.
- **Checks on the deployed stack** (script, read-only):
  - every bucket, log group, DB, state machine, guardrail and KB uses the key;
  - no resource is public except the API;
  - RDS has no public IP;
  - the Lambdas in the VPC have no route to the internet;
  - the endpoints have a policy limited to the account;
  - CloudTrail shows the Bedrock calls under the expected roles.
- **Prompt injection through data:** the week 14 poisoning cases inserted into the legacy data and the KB documents.
  The Guardrail plus the deterministic layer must block or contain them. Report the result honestly.
- **Budget action test:** in a sandbox budget, set a $0.01 threshold, confirm the deny policy attaches to a test
  role, then detach it.
- **Deliverable:** `resultados/seguridad.md`, with findings and mitigations (a preview of week 21's report).
- **AIP-C01:** D3 (seguridad y gobernanza: modelo de amenazas, escáneres, Access Analyzer)
- **Time:** ~2 h. **Cost:** cents (the stack up during the checks).

### 10. CI, README and criterion 19
- **`eval-semana-19` workflow (no AWS, $0):**
  - synth or plan;
  - nag or checkov;
  - IAM policy validation (with the GitHub OIDC role from week 12 limited to `access-analyzer:ValidatePolicy`, or
    offline with `parliament` if that is simpler);
  - the unit tests;
  - the cost model tests;
  - a test that the diagram's components match the stack's resource types.

  No skipped tests.
- **Optional manual workflow** (`workflow_dispatch`, a protected environment, OIDC): `cdk diff` against the real
  account, read-only. It never deploys.
- **`semana-19/README.md`:**
  - the diagram;
  - the ADRs;
  - how to deploy and destroy;
  - what it costs per hour and per query (measured);
  - the eval results;
  - the security review;
  - what is lab-only (one AZ, no deletion protection, HTTP API).
- **Root README:** criterion 19 checked with links to evidence; the Phase 5 status.
- **Teardown proof:** the final inventory (`"quedan": "nada"` except the listed budget and the key pending deletion)
  and the Cost Explorer total for the week.
- **AIP-C01:** D5 (pruebas en CI sin AWS) y D2 (documentación y arquitectura desplegable)
- **Time:** ~1.5 h. **Cost:** $0.

## Summary

| | |
|---|---|
| Estimated total time | ~21.5 h |
| Estimated cost | Activity 1 replaces this with measured prices. Expected: a few dollars in total, mostly model tokens in activities 7 and 8 and endpoint and DB hours while the stack is up, covered by AWS credits if the account still has them. Each paid run is estimated first, authorized by Manuel, capped in code, and checked afterwards in Cost Explorer |
| Cloud | AWS `us-east-1` only. Every resource is tagged `proyecto=semana19`, ephemeral, and removed by `destruir.sh` with an inventory as proof |
| Risks | Claude quota on Bedrock (request it in preparation; fall back to the model that has quota); interface endpoints and RDS billed by the hour (one AZ, ephemeral stack, budget action); CDK bootstrap leftovers (custom qualifier, removed in teardown); AgentCore and Bedrock L2 constructs still alpha (spike in activity 2, L1 or Terraform fallback); Guardrail false positives on SQL answers (measured against the golden tasks before it is enforced); the LLM judge disagreeing with execution-based checks (reported, not hidden); Cost Explorer lag (read the next day); the free plan not allowing a service (checked in activity 1) |

## Log

- 2026-11-03: plan created, to be handed to Claude CLI. Week 17 closed on `main` (`ce6221d`, PR #139).

---
- 2026-11-12: actividad 1 medida (`resultados/linea_base.md`). Cuenta PAID y ACTIVE; gasto del mes -0.0000000012 USD (una llamada de Cost Explorer, autorizada). Haiku 5.5 con cuota 0 de tokens; Haiku 4.5 con 5 000 000 tokens/min y 50 solicitudes/min cross-region (propuesta de modelo, pendiente de Manuel). Precios: 14 medidos, 7 documentados, 1 sin verificar. Inventario en 0 (`quedan: nada`). Pendientes: créditos (Billing), rol de operador separado del admin, llaves en el perfil `default`.
- 2026-11-12: decisiones de Manuel. (1) Modelo de las actividades 5 a 8: Haiku 4.5 con el perfil `us.` (cuota vigente); Haiku 5.5 queda pendiente de cuota. (2) Operador y admin son la misma identidad (`manuel-admin`): excepción registrada hasta crear un rol de solo lectura. (3) Corrida pagada de `sin-api` autorizada para el PR de la actividad 1.
