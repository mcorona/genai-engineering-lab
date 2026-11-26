# Phase 5 · Week 20: Costs and performance for LegacyBridge on AWS

> Spanish names (folders, files, JSON keys, flags, stack names, status values) are explained in the [glossary](../docs/glossary.md). The documentation is in English. Spanish data and recorded results stay as they are: the README in each data or results folder describes them in English.

Repo: `mcorona/genai-engineering-lab`. Folder: `semana-20/`. Each activity closes with a PR, green checks and a merge
before moving on to the next. Documentation goes in separate PRs.

- **Topic:** cost and performance engineering for a deployed GenAI agent:
  - **prompt caching** on Bedrock (cache points, TTL, what can be cached in an agent loop);
  - **batch inference** (where a tool-using agent can and cannot use it);
  - **model routing**: an own router behind `modelo.invocar` that follows Cascada's escalation idea, Bedrock
    Intelligent Prompt Routing, and Cascada itself as an offline reference;
  - **provisioned throughput** and capacity (priced and compared, not bought);
  - **observability for cost and latency**: CloudWatch metrics and dashboards, X-Ray traces from the week 17 span
    schema, CloudWatch generative AI observability.
- **Practice:** **a cost-per-query dashboard and a budget alarm** for LegacyBridge. Every optimization is measured
  against the week 19 baseline, on the same tasks, with the week 10 regression rule.
- **Criterion 20 (root README):** a cost-per-query dashboard and a budget alarm, with prompt caching, batch inference
  and model routing measured against the week 19 baseline. Every saving claimed in the README comes from a measured
  run, with success held by the week 10 rule.
- **Why it matters for clients:** after "can it run in our account?" comes "what will it cost at our volume, and how
  do we keep it from growing?". The answer is three things:
  - a dashboard that shows the cost of each query;
  - an alarm that fires before the bill does;
  - measured savings, each with its effect on quality.

  It is also AIP-C01 D4 (efficiency, 12%) and part of D2 and D5. It feeds the ±20% quote, which is the Phase 5 exit
  criterion.

## Phase 5 context (weeks 19–24)

| Week | Topic | What week 20 takes from the week before | What week 20 must leave for the weeks after |
|---|---|---|---|
| 19 | AWS reference architecture, LegacyBridge deployed with IaC | The baseline per task (`semana-19/resultados/eval_aws_detalle.jsonl`), the quote model v2 (`costos/modelo.py`), the `proyecto` tag (on the base and datos stacks only; the preparation puts it on every stack), the `modelo.invocar` interface (added in the preparation over the week 19 Converse adapter), the span schema in CloudWatch Logs, the `lab` and `prod` profiles, and the open findings H1 (throttling) and H4 (async timeout) | — |
| **20** | **Costs and performance** | — | This plan |
| 21 | Security, red teaming (garak or PyRIT, OWASP Top 10 for LLM) | — | The router and the cache as new attack surface, listed in the threat model (a cheaper model may obey injected text more easily; a cache must not be shared across users). The X-Ray traces, so the red team can follow an attack through the agent, the gateway and the tools. Throttling (H1) already in place |
| 22 | Azure and GCP equivalents, a second cloud | — | The cost and observability matrix rows (caching, batch, routing, provisioned capacity, dashboards, tracing), each with its AWS mechanism and its measured effect |
| 23–24 | AIP-C01 prep | — | D4 concepts with lab evidence in `resultados/aip_c01.md` |

- **The ±20% quote.** Week 19 measured −10.3% per hour and −0.1% (model) or +24.6% (upper bound) per query, with
  model v2. Week 20 changes the cost structure (cache, routing, batch), so model v3 must predict the optimized run
  before the run. `resultados/cotizacion.md` gets the rows for v3 with their error.

## What is measured as the baseline (from week 19, per task)

These figures come from `semana-19/resultados/eval_aws_detalle.jsonl` (activity 8, run 3, 2026-11-19). Activity 1
re-reads them and checks them before anything uses them:

| Figure | Value |
|---|---|
| Rows with a cost (2 warm-up rows and the 20 main tasks) | 19 of 22 (17 of the 20 main tasks) |
| Model cost per task, median and maximum | 0.03708 and 0.06301 USD |
| Input tokens per task, median | 26,266 |
| Output tokens per task, median | 1,348 |
| Cache read and write tokens | 0 and 0 (no cache point is sent today) |
| Steps per task, median and maximum | 6 and 8 |
| End-to-end latency, median and maximum | 23.6 and 49.95 s (the maximum is the cold warm-up) |
| Success (week 13 verifier) | 9 of 20, a regression against 20/20 local by the week 10 rule |

The input-to-output ratio is about 20 to 1, and nothing is cached. The system prompt and the tool definitions are
re-sent on every step of a 6-step loop, so prompt caching is the first lever to measure. **The regression comes
first, though.** Any saving measured on a baseline at 9/20 says little, so activity 1 checks what week 19 activity 10
decided about the regression. If the regression is still open, fixing it is the first deliverable of the week.

## Default decisions

- **Same account, region, profiles and teardown discipline as week 19.**
  - `us-east-1`, `lab` deployed and `prod` only synthesized and quoted;
  - `desplegar.sh` and `destruir.sh` with dry run by default;
  - the read-only inventory must report `"quedan": "nada"` after every session;
  - every paid run is estimated with the quote model, authorized by Manuel, and capped in code;
  - Cost Explorer calls (0.01 USD each) are authorized one by one.
- **One evaluation set for every comparison.**
  - The 10 + 10 CI golden tasks through the public API, with real Cognito tokens.
  - Success comes from the week 13 execution verifier, trajectory from the week 17 graders, and the regression
    verdict from the week 10 rule, against the corrected week 19 baseline.
  - Each optimization is measured alone first, then all of them together (activity 9), so each saving is
    attributed.
  - The "silently wrong" rate is reported for each variant: answers the agent gives with confidence that the verifier
    rejects (the SWAR idea from Manuel's Cascada benchmark). It matters most for routing, where a cheaper model can be
    wrong without failing loudly.
- **Optimizations go behind the week 19 interfaces.**
  - Caching and routing live in `modelo.invocar` (and the Converse adapter), with one config value each in
    `ia/config.py`. The agent loop does not change.
  - Turning an optimization off is a config change, and a test proves it.
- **Cost attribution by component.**
  - Bedrock **application inference profiles** wrap the `us.` profile, one per component: agent, judge, batch
    enrichment.
  - Each profile carries the `proyecto` and `componente` tags, so Cost Explorer can split model cost by component.
    Activity 1 verifies that this works with a cross-region system profile.
  - `componente` is added to every stack's tags and activated as a cost allocation tag.
- **Metrics come from the spans.**
  - The agent already emits the week 17 span schema to CloudWatch Logs.
  - Cost, tokens (including cache read and write), latency, steps, model and route per query become CloudWatch metrics
    through the Embedded Metric Format (EMF) in the same log lines, with no extra API calls from the Lambda.
  - The dashboard reads those metrics.
  - Custom metrics, alarms and dashboards have their own price and free tier. Activity 1 verifies them, and the design
    keeps the metric count small, with a written list of dimensions.
- **Tracing.**
  - X-Ray receives the same spans through OpenTelemetry (ADOT layer or OTLP with SigV4; activity 7 decides), with
    the trace id carried from the API through the agent, the gateway, the tools and Step Functions.
  - CloudWatch generative AI observability is evaluated on the same traces; it is used if it adds something the
    dashboard does not.
- **Routing, three variants, one interface:**
  - **(R1) own router** behind `modelo.invocar`, following Cascada's escalation idea. The cheapest model that has
    quota tries first, and the call escalates to a stronger one on signals the loop already has: a tool error, an
    empty or unparsable answer, a deterministic-layer block, step budget pressure, or the language. The candidate
    models and the escalation rules are fixed **before** the run, from activity 1's quotas and prices.
  - **(R2) Bedrock Intelligent Prompt Routing**, if activity 1 finds a router whose models include the ones
    LegacyBridge can use. If not, it is documented and not built.
  - **(R3) Cascada itself, as an offline reference on Manuel's Mac**, on the same 20 tasks against the lab
    PostgreSQL, with local models and the free tiers. It costs $0 in AWS. It shows what a cascade with local models
    would save, and why the deployed product still routes inside AWS: data residency, the client's account, latency.
- **Batch inference is not for the agent loop.** A tool loop needs each answer before its next step, and batch
  returns hours later. Batch is measured where LegacyBridge has single-shot work:
  - **enrichment of the data dictionary**: a description per column of the `legado` views, for the Knowledge Base
    and the week 16 audit;
  - **the LLM judge**: re-running the week 19 judge prompts.

  Batch has a minimum number of records per job (activity 1 verifies it), and the plan sizes the job to it.
- **Provisioned throughput is priced, not bought.** Activity 6 compares on-demand, cross-region, latency-optimized
  (if available for the model) and provisioned throughput at client volumes with the quote tool, and writes the
  break-even. Nothing is purchased. A commitment is an irreversible spend and needs Manuel's explicit approval, which
  this plan does not ask for.
- **The budget alarm has three layers:**
  - the AWS Budget `semana19` with the deny action from week 19, recreated with the control stack (the week 19 teardown
    removed it);
  - a CloudWatch alarm on the EMF cost-per-query metric (a query that costs more than its budget) and on the hourly
    spend rate, with an SNS email;
  - Cost Anomaly Detection: week 19 left the monitor out of its stack, so activity 1 checks whether one is on.

  The alarm is tested by firing it with a synthetic metric, not by spending.
- **API throttling (H1) is part of capacity.** Rate and burst per route come from the model quota (50 requests per
  minute cross-region for Haiku 4.5, measured in week 19) and from the steps per query. Activity 6 sets them and
  tests them.

## Preparation (before activity 1)

| Item | Where |
|---|---|
| This plan committed as `semana-20/Fas5Sema20.md` (this file is the source, without the "Para Claude CLI" section) | PR "Week 20: plan and preparation" |
| A `semana20` dependency group, locked (boto3, moto, pytest, the OTel packages already pinned in week 17, and the ADOT or exporter pieces chosen in activity 7) | `pyproject.toml`, `uv.lock`, `semana-20/preparar/versiones.json` |
| A readiness check ($0): the week 19 stacks synthesize, the profiles sign in, the week 19 baseline file is present and parses, the cost allocation tags' status | `semana-20/preparar/verificar_entorno.py` |
| **Model access and quota for the routing candidates (can take days):** list the candidates' on-demand quotas. Manuel requests any increase in Service Quotas and accepts model access in the console | Manuel, console |
| `componente` tag added to every week 19 stack, and activated as a cost allocation tag. It only applies from activation on and takes up to 24 h, so it goes before any paid run | `semana-19/infra/cdk/app.py`, Billing console (Manuel) |
| `semana-20/**` in the paths of the required `regresion` check | `.github/workflows/evals-semana-06.yml` |
| `eval-semana-20` workflow without AWS ($0): tests, synth and nag of the new constructs, no skipped tests | `.github/workflows/eval-semana-20.yml` |

## Dependencies and parallel work

```
1 baseline + regression gate ──► 2 cost attribution (app inference profiles, tags, EMF)
                                        │
            ┌───────────────────────────┼───────────────────────────┬──────────────────────┐
            ▼                           ▼                           ▼                      ▼
      3 prompt caching           4 model routing (R1, R2, R3)   5 batch inference    6 capacity: throttling,
            │                           │                           │                provisioned throughput
            └───────────────┬───────────┘                           │                      │
                            ▼                                       │                      │
              7 X-Ray and GenAI observability ──► 8 dashboard and alarms                   │
                            └───────────────────────────────┬───────────────────────────────┘
                                                            ▼
                                   9 optimized run, quote v3 ──► 10 CI, README, criterion 20
```

| Can start right after activity 1 | Part | Needs |
|---|---|---|
| 3 | Cache points in the Converse adapter, the cacheable prefix measured offline (tokens of system prompt + tools against the model's minimum per cache point) | Week 19 Converse adapter |
| 4 | The router (R1) with its rules and offline tests; Cascada (R3) on the Mac, $0 in AWS | Week 19 `modelo.invocar`, Manuel's Cascada |
| 5 | The batch input file (one record per column of the `legado` views) and its schema tests | Week 16 audit, the KB dictionary |
| 6 | The capacity and provisioned-throughput math with the quote tool, and the throttling values | Activity 1 prices and quotas |

What must wait: anything that compares live runs (2 first), the dashboard (7), the combined run (3 to 6), and the
README (last).

## Activities

### 1. Baseline and regression gate
- **The week 19 hand-off, checked:**
  - read the week 19 README hand-off list and confirm each item exists: the baseline file and its schema, the tags,
    the model interface, the span schema in the logs, and the `prod` window still to schedule;
  - recompute the baseline table above from `eval_aws_detalle.jsonl`, and fail if a figure differs.
- **The regression gate:**
  - read what week 19 activity 10 decided about the 9/20 result;
  - if a corrected run exists and passes the week 10 rule, it becomes the baseline;
  - if not, diagnose from the saved spans ($0) and fix the cause in a PR, then re-run only the 20 tasks, estimated
    and capped, until the rule passes or Manuel decides otherwise;
  - week 20 compares against a passing baseline, or states plainly that it does not.
- **Prices and limits** (Price List with catalog ids, or the official docs with link and date; M, D or N as in week
  19):
  - Haiku 4.5 cache write and cache read prices, the minimum tokens per cache point, the TTL options (5 minutes and 1
    hour), and how many cache points a request may carry;
  - batch inference: the discount, the models supported, the minimum and maximum records per job, the input and output
    format, and the expected turnaround;
  - Intelligent Prompt Routing: the routers available in `us-east-1`, their models, whether one includes a model
    LegacyBridge can use, and its price;
  - the routing candidates: per-token prices and on-demand quotas (tokens and requests per minute) of the cheaper and
    stronger models with access;
  - provisioned throughput: model units, the no-commitment and commitment prices for the candidate models, and
    latency-optimized inference if it exists for them;
  - application inference profiles: creation from a cross-region system profile, tagging, and how they show up in
    Cost Explorer;
  - CloudWatch: custom metrics, EMF, dashboards, alarms, Logs Insights, Transaction Search and X-Ray traces, each with
    its free tier;
  - CloudWatch generative AI observability: what it needs (ADOT, Transaction Search) and its price.
- **Deliverable:** `resultados/linea_base.md` (matrix and prices with catalog ids), `linea_base/verificar.py` ($0
  checks) and the regression status.
- **AIP-C01:** D4, D5.
- **Time:** ~1.5 h, plus the regression fix if it is open. **Cost:** $0, plus the re-run if needed (estimated and
  authorized first).

### 2. Cost attribution: application inference profiles, tags and metrics from the spans
- **Application inference profiles**, one per component (`agente`, `juez`, `enriquecimiento`), created from the IaC
  over the `us.` Haiku 4.5 profile, tagged `proyecto` and `componente`.
  - `MODELO_ID` in `ia/config.py` becomes the agent's application profile ARN.
  - The IAM policy of week 19 activity 5 is updated to that ARN, and still denies any other model.
- **EMF metrics** from the agent Lambda's span log lines:
  - per query: cost, input, output, cache read and cache write tokens, steps, latency, success state, model and route;
  - a namespace `LegacyBridge`, and dimensions limited to a written list (route, model, language), so the metric count
    stays known.
  - A test counts the metrics the code can emit.
- **The cost of a query, three ways**, on one small authorized run of a few tasks:
  1. from the spans (tokens × price);
  2. from the EMF metric;
  3. from Cost Explorer by `componente` the next day.

  Any disagreement is explained.
- **Deliverable:** `resultados/atribucion.md`, the updated IAM policy and its tests.
- **AIP-C01:** D4.
- **Time:** ~2 h. **Cost:** cents (a few tasks plus the stack hours), estimated and authorized first.

### 3. Prompt caching
- **Offline ($0):** measure the cacheable prefix of each step: system prompt, tool definitions, and the stable start of
  the conversation.
  - Count its tokens against the model's minimum per cache point.
  - Decide where the cache points go (after the system prompt and the tools; whether a rolling point on the
    conversation pays off), and which TTL (5 minutes or 1 hour) fits a 6-step loop and the gap between queries.
  - Predict the saving with the quote model before running.
- **Code:** cache points in the Converse adapter behind one config value (`CACHE_PROMPT = off | sistema | sistema+herramientas | ...`).
  - The tokens read and written from the cache are already recorded (week 19 activity 8).
  - Tests: the request carries the cache points only when the flag is on, and the Guardrail and the prompt version are
    unchanged.
- **Security note for week 21:** the cache is per account and per prefix. The prefix must not contain anything
  specific to the user (tenant, `sub`, the question). A test checks that the cached prefix is the same for two
  different users.
- **Live:** the 20 tasks with the cache on. Compare with the baseline:
  - cost per task;
  - cache hit tokens per step;
  - first-step and later-step latency;
  - success by the week 10 rule.
- **Deliverable:** `resultados/cache.md`, quote v3 for caching (predicted vs real).
- **AIP-C01:** D4.
- **Time:** ~2 h. **Cost:** under a dollar (20 tasks, cheaper than the baseline if caching works), estimated and
  capped.

### 4. Model routing
- **(R1) own router:**
  - the candidates and the escalation rules are fixed in `ia/config.py` and in an ADR before the run;
  - the router lives behind `modelo.invocar`, and the loop, the budgets and the guardrails stay the same;
  - each escalation is a span attribute (`gen_ai.request.model` and a `ruta` attribute) and an EMF dimension;
  - offline tests: each rule escalates on its signal and only then, the budget counts the stronger model's tokens,
    and a router off is identical to week 19.
- **(R2) Intelligent Prompt Routing:** only if activity 1 found a router with usable models. Same 20 tasks, through
  the router ARN.
- **(R3) Cascada offline:**
  - the same 20 tasks on Manuel's Mac, the agent pointed at Cascada's LiteLLM proxy, the lab PostgreSQL;
  - $0 in AWS, with the free tiers (OmniRoute or the local models);
  - report success, silently-wrong rate, tier reached and latency.

  It is a reference, not a deployed path. The report says why: data residency, the client's account, the network path
  from Lambda.
- **(R0) local Haiku 4.5 baseline** (week 19 hand-off, item 6; Manuel's decision of 2026-11-23):
  - the same 20 tasks with week 17's local harness, run with Haiku 4.5 instead of Haiku 5.5;
  - it separates the model's effect from the port's: week 17's 20/20 was Haiku 5.5 run locally, and week 20's
    baseline (16/20) is Haiku 4.5 on AWS;
  - it is run before R1, from the Mac, estimated and capped (about 1 USD of model, like week 20's corrected run), and
    its four failures are compared with the deployed run's (c02 and r05 in both languages).
- **Live (R1, and R2 if it applies):** the 20 tasks. Report, per variant:
  - success;
  - silently-wrong rate;
  - share of calls per model;
  - cost per task;
  - latency;
  - the regression verdict.

  A router that saves money and loses success under the week 10 rule is rejected, and the report says so.
- **Deliverable:** `resultados/ruteo.md` with the three-way table and the decision, plus an ADR.
- **AIP-C01:** D4, D1.
- **Time:** ~3 h. **Cost:** about a dollar (20 tasks × 1 or 2 variants), estimated and capped. R3 is $0 in AWS.

### 5. Batch inference
- **Job:**
  - a description per column of the `legado` views, for the data dictionary, from the week 16 audit's facts and the
    column samples (synthetic, seed 42), as one record per column;
  - sized to the batch minimum from activity 1; if the views have fewer columns than the minimum, the record count
    and its padding are documented;
  - the input and output are in the encrypted bucket (week 19 key), and the job runs under a role limited to that
    bucket and the enrichment profile.
- **Comparison:**
  - the same records on demand (a sample if the minimum makes the full on-demand run wasteful), and the batch job;
  - cost per record, total cost, turnaround time, failures and retries;
  - quality, checked against the facts the audit already holds (a deterministic check where possible, the week 19
    judge on a sample where not).
- **Where batch fits in LegacyBridge** (enrichment, offline evals, nightly reports) and where it does not (the
  interactive loop): one table.
- **Deliverable:** `resultados/batch.md`, the enriched dictionary as a reviewed artifact (not loaded into the KB
  without Manuel's OK).
- **AIP-C01:** D4, D1.
- **Time:** ~2 h. **Cost:** cents to a dollar, depending on the batch minimum, estimated and capped.

### 6. Capacity: throttling, quotas and provisioned throughput
- **Throttling (H1):** rate and burst per route on the HTTP API stage, derived from the model quota and the steps per
  query, with the math in the ADR. Tests: synth carries the values, and a live burst over the limit gets 429 without
  reaching the agent (a few requests, $0 in model tokens).
- **Week 19 findings H2 and H10** (decided for week 20):
  - H2: ADR 0008 decided that the agent calls the Knowledge Base, and no code calls `Retrieve` today;
  - H10: the resources not on the project key (KMS at rest, partial in criterion 19).

  Each is fixed and re-checked with `verificar_desplegado.py`, or carried to week 21 with its reason.
- **Async timeout (H4):** a question whose agent times out or crashes reaches a terminal state (not `pendiente` until
  the TTL). Tested offline and live with a forced timeout.
- **Provisioned throughput, priced:** with the quote tool, the monthly cost of on-demand, cross-region on-demand,
  latency-optimized (if it exists for the model) and provisioned throughput (with and without commitment), at three
  client volumes (queries per day from the quote model's client parameters). It ends with the break-even volume, and
  the recommendation per volume. Nothing is bought.
- **Deliverable:** `resultados/capacidad.md`, the throttling ADR and its tests.
- **AIP-C01:** D4, D2.
- **Time:** ~2 h. **Cost:** cents (the stack up for the throttling and timeout tests).

### 7. Traces: X-Ray and CloudWatch generative AI observability
- **Decision (ADR):** how the week 17 spans reach X-Ray: the ADOT Lambda layer, or the OTLP exporter with SigV4 to the
  X-Ray endpoint, with Transaction Search on. It covers cold start cost, package size, price per trace and the effort
  to keep the schema.
- **One trace per query:**
  - the trace id carried from the API Gateway request through the asynchronous invocation (ADR 0007), the agent loop,
    the gateway (path b), the tools Lambda and Step Functions;
  - a test with a stubbed exporter checks parentage across the async hop, which is where week 17 found context lost.
- **CloudWatch generative AI observability:** turn it on for the lab, and read the same queries there. Record what it
  shows that the dashboard does not, and what it costs. Keep it only if it adds something.
- **Content capture stays off** (week 17 rule): no prompt or answer text in traces. A test checks it.
- **Deliverable:** `resultados/trazas.md`, with one example trace redacted (as an image and as JSON).
- **AIP-C01:** D5, D4.
- **Time:** ~2 h. **Cost:** cents (traces within the free tier, verified), estimated first.

### 8. The cost-per-query dashboard and the budget alarm
- **Dashboard (IaC, in the persistent control stack if its cost is $0 at rest, otherwise in the ephemeral stack):**
  - cost per query (p50, p95, sum per hour);
  - tokens per query split into input, output, cache read and cache write;
  - cache hit ratio;
  - share of calls per model and route;
  - success rate;
  - latency p50 and p95;
  - throttled requests;
  - the budget's actual and forecast spend.

  Every widget reads an EMF metric from activity 2 or a service metric. A test checks that the widgets name metrics the
  code emits.
- **Alarms (IaC, SNS email from the environment):**
  - cost per query above its budget (the week 17 per-query budget in dollars);
  - hourly spend rate above the authorized rate;
  - a spike in throttled requests;
  - tokens per query above p95 + margin, with anomaly detection if it is within the free tier.

  The AWS Budget and its deny action stay as the last layer.
- **Tests:** every alarm is fired with a synthetic metric value (PutMetricData of one data point, costing nothing
  measurable), the email arrives, and the alarm returns to OK. No real spend is needed.
- **Deliverable:** `resultados/tablero.md` with a screenshot of the dashboard during a run, the alarm list, and the
  firing test.
- **AIP-C01:** D4, D5.
- **Time:** ~2 h. **Cost:** cents, plus the dashboard and alarm prices from activity 1 (within the free tier if
  possible).

### 9. Optimized run and quote v3
- **Combined configuration:** the cache settings from activity 3, the routing decision from activity 4, and the
  throttling from activity 6, all on.
- **Prediction first:** the quote model v3 predicts the cost per query and per hour before the run, and the prediction
  is committed before the run starts.
- **Live:** the 20 tasks. Report:
  - success, by the week 10 rule against the baseline;
  - trajectory, from the week 17 graders;
  - silently-wrong rate;
  - cost per task, and each saving attributed: cache, routing, and the rest;
  - latency p50 and p95, cold and warm;
  - the dashboard during the run.
- **Real cost:** Cost Explorer by `proyecto` and `componente` the next day (with Manuel's OK). Fill the v3 rows of
  `resultados/cotizacion.md` with the error in %. If the error exceeds ±20%, fix the model, not the number.
- **The prod quote, updated:** lab and prod monthly quotes with the optimizations, at the three client volumes of
  activity 6.
- **Deliverable:** `resultados/optimizado.md`, `resultados/optimizado_detalle.jsonl` (same schema as week 19's, plus
  route and cache fields) and the updated `cotizacion.md`.
- **AIP-C01:** D4, D5.
- **Time:** ~2.5 h. **Cost:** about a dollar or less, estimated and capped.

### 10. CI, README and criterion 20
- **`eval-semana-20` workflow (no AWS, $0):**
  - the unit tests (router rules, cache points, EMF schema, dashboard widgets against emitted metrics, alarm
    definitions, batch input schema, throttling values);
  - synth and nag of the new constructs;
  - the quote model v3 tests;
  - no skipped tests.
- **`semana-20/README.md`:**
  - the baseline, and each optimization with its measured saving and its effect on success;
  - the routing decision;
  - batch: where it fits;
  - capacity and the provisioned-throughput break-even;
  - the dashboard and the alarms;
  - traces;
  - quote v3 with its error;
  - what is lab-only.
- **Root README:** criterion 20 with links to evidence. The cost cross-cutting criterion updated with the v3 error.
  The Phase 5 table updated.
- **`resultados/aip_c01.md`:** D4 by concept, each with its lab evidence.
- **Hand-off to week 21, a short list:**
  - the router and the cache as attack surface;
  - the traces for following an attack;
  - throttling in place;
  - the open findings still carried from week 19 (H3, H5, H7, H8, H12, H14 and the H13 residual case), and H2 and
    H10 if activity 6 did not close them.
- **Teardown proof:** the final inventory and the Cost Explorer total for the week.
- **AIP-C01:** D4, D5.
- **Time:** ~1.5 h. **Cost:** $0.

## Summary

| | |
|---|---|
| Estimated total time | ~21 h, plus the week 19 regression fix if it is open |
| Estimated cost | A few dollars in total: model tokens for the measured runs (activities 2, 3, 4, 5, 9), the stack hours while up, and small CloudWatch charges. Activity 1 replaces this with measured prices. Each paid run is estimated, authorized, capped in code, and checked in Cost Explorer |
| Cloud | AWS `us-east-1`, the week 19 stacks plus small additions (profiles, metrics, dashboard, alarms, tracing), tagged `proyecto` and `componente`, ephemeral except what costs $0 at rest |
| Risks | **The baseline:** the week 19 regression (9/20) makes every comparison weak until it is fixed. **Caching:** the cacheable prefix may be under the model's minimum, and caching may not pay for a 6-step loop with the TTL chosen (measured offline first). **Routing:** a cheaper model can be silently wrong (silently-wrong rate reported), and the routing candidates may lack quota (requested in preparation). **Prompt Routing:** may have no router with usable models (documented, not built). **Batch:** the minimum record count may exceed the real need (documented padding). **CloudWatch:** custom metrics and dashboards are priced per item (dimension list fixed). **X-Ray:** context lost across the async hop (tested offline). **Cost Explorer:** lag (read the next day), and tags that apply only from activation (activated in preparation) |

## Log

- 2026-11-22: plan created, to be handed to Claude CLI. It builds on week 19 (activities 1 to 9 merged; activity 10
  in progress). The baseline table is from `semana-19/resultados/eval_aws_detalle.jsonl`.
- 2026-11-23: week 19 closed (criterion 19 met except the mini eval, 9/20, and KMS at rest, partial). Preparation PR:
  this plan committed, with five corrections against what week 19 left:
  1. `modelo.invocar` did not exist: the preparation adds it (`semana-19/agente/modelo.py`) as a thin seam over the
     Converse adapter, with no change in behavior;
  2. the `proyecto` tag was only on the base and datos stacks: every stack now carries `proyecto`, `perfil` and
     `componente`;
  3. H2 and H10, decided for week 20, are added to activity 6;
  4. the budget `semana19` was removed by the week 19 teardown, and is recreated with the control stack;
  5. Cost Anomaly Detection is checked in activity 1, not assumed on. The hand-off to week 21 adds the H13 residual
     case.
- 2026-11-23: activity 1 ($0). The baseline table matches the file, but it is computed over the 22 rows, warm-ups
  included: "19 of 20" with a cost is 19 of 22, and 17 of the 20 main tasks; the latency maximum is the cold warm-up.
  Week 20 compares against the 20 main tasks (`resultados/linea_base.md`, section 2). The regression gate is open, and
  its re-run waits for Manuel's OK. Haiku 4.5 caches only from 4,096 tokens per cache point, more than the system prompt
  and the tools (about 2,800), so activity 3 puts the cache point at the end of the history.
- 2026-11-23: Manuel approved the corrected run: no `cachePoint`, a per-task ceiling of 0.12 USD and 100,000 tokens
  (`PRESUPUESTO_TAREA=techo_semana20`, a config value), its own cap of 2.50 USD, no prompt change for c02 or c06-en
  (they go to activity 4), about 1.05 USD expected. `linea_base/corrida.py` runs it. The week 19 README said
  `desplegar.sh` deploys computo; it does not, and the README now gives the computo command.
- 2026-11-23: **corrected run: 16/20**, 0 tasks cut by the budget, 1.008147 USD of model (cap 2.50). Under week 10's
  rule it is still a regression (0.8 in each language). The four failures (c02 in both languages, r05 in both) are
  model quality. Manuel accepted the run as week 20's baseline, stated as not passing; activity 4 escalates those
  cases. The deploy needed #327 (`iam:TagRole` for ia, broken by #322's tags). Week 20 keeps the 0.12 USD and 100,000
  token ceiling as its cap until activity 9 calibrates one on repeated runs.
- 2026-11-23: the two missing prices, read at $0 from the Price List (`precios.py`, 157 rows, all of them added). Nova 2 Lite is 0.33 / 2.75 USD per 1M; its usage type is `Nova2.0Lite`. A CloudWatch dashboard is 3.00 USD per month beyond the 3 free, a global price with no region.
- 2026-11-23: one Cost Explorer call (`ListCostAllocationTags`, 0.01 USD, Manuel's OK). `proyecto` is Active; `componente` is not listed yet, so Manuel activates it once Billing shows it, before activity 2 (`resultados/etiquetas_costo.json`).

- 2026-11-23: activity 2, code ($0). The three application inference profiles are in the ia stack, tagged with their
  component. The judge's copies Nova Pro, its week 19 model, not Haiku 4.5. `MODELO_ID` stays the copied system
  profile: the profile's ARN holds the account, so the stack passes it to the Lambda (`MODELO`), and
  `USAR_PERFIL_DE_APLICACION` in `ia/config.py` is the off switch. The EMF metrics ride on the agent span's line: 8
  metrics with dimensions model and route. Language is out, because the agent never receives it. The small run
  (`atribucion/corrida.py`, 4 tasks, cap 0.40 USD, about 0.30 USD with the stacks) waits for Manuel's OK and for
  `componente` to be active (`resultados/atribucion.md`).
- 2026-11-23: two items of week 19's hand-off had no activity (Manuel's decision):
  - the local Haiku 4.5 baseline goes to activity 4, as R0;
  - the prod window stays out of week 20. Prod is still only synthesized and quoted from the model (activity 9), as
    the default decisions say, and its per-hour figure stays unmeasured. Deploying prod would be its own session, with
    its own estimate and OK.
- 2026-11-24: activity 2, the run. `componente` and `perfil` were activated in Billing. The deploy needed #335: the
  profile description had a comma, which CloudFormation's pattern rejects, and the bootstrap echo printed the account.
  The run: 4/4 tasks answered, 0.0985182 USD from the spans and the same from EMF, against the 0.40 cap. The teardown
  ended in `"quedan": "nada"`. Cost Explorer by `componente` the next day closes the activity
  (`resultados/atribucion.md` §4).
- 2026-11-24: activity 1, the last item. Manuel checked Cost Anomaly Detection in the console: a monitor is on, and
  no anomaly is flagged (`resultados/linea_base.md` §4.9). Activity 8 uses it and does not create another one.
- 2026-11-25: activity 2 closed. One Cost Explorer call (`GetCostAndUsage` for 2026-11-24, 0.01 USD, Manuel's OK):
  `componente=agente` is 0.0985182 USD, the same as the spans and EMF. The day's total for `proyecto=semana19` is
  0.1802167 USD, the rest being the stacks' hours (`resultados/atribucion.md` §4).
- 2026-11-25: activity 3, offline part ($0).
  - The fixed prefix is 2,664 tokens (2,898 at the upper bound), under Haiku 4.5's 4,096: a point on the system prompt
    or the tools caches nothing.
  - Design (ADR 0014): the point goes at the end of the history from the second call on, plus the previous call's
    position, with a 5-minute TTL, off by default (`CACHE_PROMPT`). The budget, the span cost and EMF count the
    cache tokens at their prices, and one chat span per call records them.
  - Prediction, committed before the run: 45.0% saving if every call reads (0.511 USD for the 20 tasks), 3.9% at a
    1/3 hit rate, −16.7% if none does; break-even at 0.27 (`resultados/cache.md`).
  - The run waits for Manuel's OK.
