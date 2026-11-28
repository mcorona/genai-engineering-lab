# ADR 0015: the in-house router, Nova Lite first, escalating to Haiku 4.5 and Sonnet 4.6 for the rest of the task

Week 20, activity 4, R1. This is the design, fixed before any R1 run. The live run's result and the final decision are
added at the end of the activity. Glossary: [in-house router](../../../docs/glossary.md).

**Marks:**
- **D** is AWS documentation read on 2026-11-27, with its link.
- **M** is a Price List row with its SKU (`semana-20/resultados/precios.json`, read 2026-11-23, us-east-1).
- **Q** is Service Quotas and `get-foundation-model-availability`, read 2026-11-27 with the read-only operator.
- **R** is a run in this repository.

## Context

- **What R0 established (R, `semana-20/resultados/ruteo.md` §1).**
  - Haiku 4.5 alone scores 16/20 locally; week 17's Haiku 5.5 scored 20/20.
  - The model's failures are c02 (it abstains or asks where an answer is expected) and c06 (c06-en answers in Spanish,
    `linea_base.md`).
  - r05 is the port's failure, out of the router's reach.
  - R1's verdict is against the cache run (17/20, median 0.022060 USD per task), and R1 is also reported against
    week 17.
- **What the router can see.** It sits behind `modelo.invocar`, so it sees only two things.
  - **Each request body.** That is the loop's whole history: the task, the model's turns, and every tool result with
    its `is_error` and the deterministic layer's error type.
  - **Each raw Converse response**, before translation.
  - It does not see the gold answer, the verifier, the week 13 loop's counters, or the output guardrail, which runs
    after the loop.
- **The cache run's shape (R, `cache_detalle.jsonl`, 20 tasks).**
  - Steps: 18 of the 20 tasks take 2 to 6. One takes 10 and r05-en takes 12.
  - Tokens per task, counting input, output and cache: 6,180 to 117,571. Only 2 tasks pass 50,000.
  - The largest prefix of any call is 13,727 tokens.

### The candidates

The three are ordered from cheapest to strongest. Each is called through its `us.` cross-Region profile, whose
destination Regions are us-east-1, us-east-2 and us-west-2, the same as Haiku 4.5 today (D, model cards). The data
stays in the same US geography.

| | Nova Lite | Haiku 4.5 (today's model) | Sonnet 4.6 |
|---|---|---|---|
| Profile | `us.amazon.nova-lite-v1:0` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | `us.anthropic.claude-sonnet-4-6` |
| Access, lifecycle (Q, D) | AUTHORIZED, AVAILABLE, Active | AUTHORIZED, AVAILABLE, Active | AUTHORIZED, AVAILABLE, Active |
| Cross-Region quota, RPM / TPM (Q) | 400 (L-89F8391A) / 8,000,000 (L-7C42E72A) | 50 (L-CCA5DF70) / 5,000,000 (L-58BE175A) | 50 (L-00FF3314) / 6,000,000 (L-15B8E632) |
| USD per 1M tokens, input / output (M) | 0.06 (QRGWJ3P8FT28EYX2) / 0.24 (CBZ6A6U7XK8WJ3KA) | 1.10 (JQDUC8Q4K8C6GSGH) / 5.50 (X629GDA2GXAP6R54) | 3.30 (KPFGPZJ8VWMREGAV) / 16.50 (GMB9AQ5DYNAGYZEC) |
| Cache read / write, 5 min (M) | 0.015 (FYTFBAWEJFBAVTWK) / 0 (NF8UDYEDB4HXGNAZ) | 0.11 (VJXPZKPF7EDCFXN3) / 1.375 (CDG7WESKYQ9N9KDN) | 0.33 (2459RQS6BSFATF92) / 4.125 (UZUVWF3P26ENQTZ8) |
| Converse; client-side tools; Guardrails (D, model cards) | yes; yes; yes (text only) | yes; yes; yes | yes; yes; yes |
| Spanish (D) | one of the 15 optimized languages ([what-is-nova](https://docs.aws.amazon.com/nova/latest/userguide/what-is-nova.html)) | listed as a supported model ([multilingual-support](https://platform.claude.com/docs/en/build-with-claude/multilingual-support)) | listed, same page |

**Why these three.**
- **Nova Lite rather than Nova Micro.** The price gap is small. Priced over the cache run's tokens (568,869 input and
  36,943 output for the 20 tasks), Lite costs 0.0007 USD more than Micro for the median task and 0.0032 USD more for
  the largest (r05-en). No document ranks the two on tool use, so the larger tier is the conservative pick, and the
  run measures it. Nova Micro is text-only with a 128K context; Nova Lite has 300K (D).
- **Sonnet 4.6 rather than Sonnet 4.5.** Sonnet 4.5 is LEGACY and Sonnet 4.6 is ACTIVE (Q), at the same price (M:
  Sonnet 4.5 SSK4DT4JBRUQJYP5 and 3YN5KGC2HJU9VC5A are 3.30 and 16.50 too).
  - Its model card says it is offered through "inference profiles with limited model selection". This is a lifecycle
    note, not a blocker.
  - Sonnet 4.6 and Haiku 4.5 are billed through AWS Marketplace, Nova through Bedrock (D, Sonnet 4.6 model card). All
    of them go to the AWS account, and none uses an Anthropic API key.
- **Bedrock's Intelligent Prompt Routing is R2, not this ADR.** Activity 1 found it only for Nova Lite and Nova Pro in
  this account (`precios.json`, `enrutadores`). Sonnet 4.6's model card lists it as not supported.

### What Converse needs per candidate (D)

| Point | Finding | Source | What R1 does |
|---|---|---|---|
| `toolConfig` | Supported by all three. Nova reads only `type`, `properties` and `required` at the top level of a tool's schema. `$schema`, `description`, `title` and `additionalProperties` there are "common unsupported fields" and can make Nova ignore the tool. | [Nova tool troubleshooting](https://docs.aws.amazon.com/nova/latest/userguide/prompting-tool-troubleshooting.html) | All 6 of the agent's tools carry a top-level `additionalProperties`, and `responder` also carries `$defs` and `title` (R, read from the definitions). For Nova only, the adapter inlines the `$defs` references and keeps only those three top-level keys. Claude's request does not change. |
| Decoding for tools | "Amazon Nova models have more success calling tools when using greedy decoding": `temperature` 0 and `topK` 1 in `additionalModelRequestFields`. | same page | Nova only. |
| Nova's reasoning text | Nova answers a tool call with `<thinking>` text beside the `toolUse`. | [Nova tool invocation](https://docs.aws.amazon.com/nova/latest/userguide/tool-use-invocation.html) | The loop already ignores text when a tool is asked for. The adapter keeps it as a text block. |
| `toolResult.status` | "only supported by Amazon Nova and Anthropic Claude 3 and 4 models" | [ToolResultBlock](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolResultBlock.html) | Kept for all three. |
| `guardrailConfig` | Guardrails supported by all three (Nova Lite: text only, and the agent sends only text). | model cards | The same pinned guardrail id and version on every call, whichever model serves it. |
| System prompt | The same week 13 `SISTEMA`, the pinned Prompt Management English version, for all three ("Write the answer in the language of the task"). | ADR 0014, `test_ia_peticion.py` | No prompt per model, so the pinned version stays one version. |
| Max output | Nova Lite 10K, Haiku 4.5 per week 19, Sonnet 4.6 64K. The loop asks for at most 4,000 and the budget can lower it. | model cards | Unchanged. |

The synth for lab and prod is part of the code step (step 3). It checks that the stack passes every candidate's
profile ARN, the guardrail version and `RUTEO` to the Lambda.

## Alternatives

| Option | Why not |
|---|---|
| Start on Haiku 4.5 and escalate only to Sonnet 4.6 | It saves nothing: every call costs at least today's. It would close the model's gap (c02, c06) at a higher cost. That is a different question from the one R1 asks: can a cheaper start keep the success? |
| Start on Nova Micro | Its price gap to Nova Lite is small (above), and no document ranks the two on tool use. Lite is the larger tier. |
| Sonnet 4.5 as the strong model | LEGACY (Q), at the same price as Sonnet 4.6. |
| Escalate one call and then come back down (per step) | The next model writes its cache again at every switch (§3), and the history keeps the cheap model's failure. The rest of the task is cheaper to reason about, and its cost is bounded by `max_escalamientos`. |
| Escalate on any tool error only after the loop's 3 consecutive errors | The loop already lets the model retry. Waiting three errors on the cheap model spends three steps of the 12. |
| Bedrock Intelligent Prompt Routing | Only Nova Lite and Nova Pro in this account (activity 1), optimized for English, and it routes each prompt alone, without the task's history. It is R2, measured apart if Manuel agrees. |
| A model and route dimension on the 8 EMF metrics | 24 to 48 custom metrics, over the 10 free (§7). |

## Decision

### 1. Policy

- **Start:** Nova Lite, the first of `RUTEO_CANDIDATOS`.
- **Scope of an escalation: the rest of the task.** The next model serves every later call of the task. The router
  never goes back down. Going back would mean another model writes the cache again (§3), and the history would keep
  the failure the cheap model just showed.
- **One step at a time:** Nova Lite to Haiku 4.5, then Haiku 4.5 to Sonnet 4.6. **At most 2 escalations per task**
  (`max_escalamientos`). After that, signals are recorded and ignored.
- **The state is per task.** It resets when a request carries one message, the first call of a task. So the same
  `api` can serve several tasks, as the eval harness does.

### 2. The signals (`RUTEO_REGLAS`)

Request signals are read from the body of the next call, before it is sent. That call already goes to the next model.

| Signal | What is read | Why |
|---|---|---|
| `error_herramienta` | The last message holds a `tool_result` with `is_error`, of a type other than the deterministic layer's | The cheap model sent a call the tool rejected |
| `resultado_vacio` | A successful `tool_result` with no rows (`filas` empty) | It often means a wrong filter or table |
| `bloqueo_capa` | A `tool_result` whose error type is the deterministic layer's (`guardrail`, `herramienta_desconocida`) | The model asked for something outside its scope. The layer still applies to the next model. |
| `respuesta_invalida` | A `tool_result` of type `respuesta_invalida`: the loop rejected the `responder` input as unparseable | The cheap model cannot produce the answer's schema |
| `presion_pasos` | 7 or more model turns in the history (the loop's limit is 12) | 18 of the 20 cache-run tasks finish in 6 or fewer |
| `presion_tokens` | 50,000 or more tokens seen so far in the task (input, output and cache, from the responses the router passed on) | Half of the deployed task ceiling (100,000). 2 of the 20 cache-run tasks pass it. |

Response signals are read from the raw Converse response. The same request is sent again to the next model, and the
loop receives only the stronger model's answer. The cheap answer is discarded, but its cost is counted (§4).

| Signal | What is read | Why |
|---|---|---|
| `respuesta_vacia` | No content blocks, or text without any `toolUse`, with `stopReason` `end_turn` | Without escalation, the loop spends a step on a reminder, or stops with `sin_responder` |
| `abstencion` | A `responder` call with `estado` `abstenida` or `requiere_aclaracion` | c02: Haiku 4.5 abstains or asks where Haiku 5.5 answered. The router cannot know whether the abstention is right, so it asks a stronger model. A01 and n01 pay that confirmation. |
| `idioma` | The `respuesta` of a `responder` call is in a language other than the task's | c06-en answered in Spanish. The task's language is taken from the task text before the eval's English output-key block, so the boilerplate does not count. |

**What is never a signal:**
- **`stopReason` `guardrail_intervened`.** The Bedrock guardrail's decision is final. Escalating would ask another
  model to get past a security control.
- **`max_tokens`.** The budget sets it. A stronger model under the same cap would hit it again, at a higher price.
- **The output guardrail and the verifier.** They run after the loop.

**What the router cannot catch: a confident wrong answer.** The cheap model can answer with the right schema and the
wrong SQL. In production nothing checks that before the user sees it. In the eval it is the silently-wrong rate, and
the live run reports it for each model that answered. This is the main risk of starting cheap. Under week 10's rule,
a router that saves money and loses success is rejected.

### 3. The cache (ADR 0014) per model

| Model | Minimum per point (D) | TTL (D) | Points allowed in (D) | `CACHE_PROMPT` when caching is on |
|---|---|---|---|---|
| Nova Lite | 1K; at most 20K tokens cached | 5 minutes only. The `ttl` field must be omitted, or the call can fail with `ValidationException`. | `system` and `messages` | `historial+sistema`. Writes cost 0 (M), so a point never costs more than no point. The fixed prefix, about 2,700–2,900 tokens (ADR 0014), passes 1K. The largest prefix in the cache run (13,727 tokens) is under the 20K cap. |
| Haiku 4.5 | 4,096 | 5 min, 1 h | `system`, `messages`, `tools` | `historial`, as in ADR 0014. A `sistema` point caches nothing at 4,096. |
| Sonnet 4.6 | 1,024 | 5 min, 1 h | `system`, `messages`, `tools` | `historial+sistema`. The fixed prefix passes 1,024. |

Source: [prompt-caching](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html) and the model cards.

- **TTL.** `CACHE_TTL` stays 5 minutes. With a Nova candidate, `1h` is a configuration error (fail closed), never a
  `ttl` field sent to Nova.
- **The `sistema` point and the security boundary.** On Nova and Sonnet the `sistema` point goes on every call,
  including the first. It covers only the tools and the system prompt: the same for every user, with nothing of the
  user (ADR 0014's boundary test). The history points still never go on the first call.
- **The cost of rewriting the prefix at an escalation.** A cache entry is per model. The first call on the new model
  finds nothing of this task's history, so it writes the whole prefix I_k: 1.25 × input on Claude, and 0 on Nova.
  Worked on s06-es's measured prefixes (R, cache run: 2,952 / 4,268 / 4,548 / 4,733 / 5,133 tokens):
  - Escalating to Sonnet 4.6 at call 4 writes 4,733 tokens at 4.125, which is 0.0195236 USD for the prompt.
    - Sending them uncached would cost 0.0156189, so the write adds 0.0039047.
    - Staying on Haiku 4.5 with the cache, the same call would read 4,548 at 0.11 and write 185 at 1.375, 0.0007547.
    - So the escalation's prompt costs 0.0187689 USD more than staying.
  - Escalating to Haiku 4.5 at call 3 writes 4,548 tokens at 1.375 (0.0062535), against 0.0050028 uncached.
  - Later calls on the new model read again, as in ADR 0014.
  - The prediction (step 4) prices every escalation this way.

### 4. The budget counts each call at its own model's price

- **`PRESUPUESTO_TAREA` stays one limit per task.** The deployed ceiling is 0.12 USD and 100,000 tokens.
- **The loop's own `costo_usd` cannot be used with `RUTEO=r1`.** It prices every token at Haiku 4.5. Each call is
  priced with the Price List price of the model that served it (the table above), cache tokens included. The span
  cost and the EMF cost are the sum of the calls.
- **Before each call, the remaining budget sets `max_tokens` at the next model's prices.** So an escalated call is
  capped by Sonnet's output price, not Haiku's.
- **A response signal's second call is also asked of the budget first.** If it does not fit, the cheap answer stands
  and the route records `sin_presupuesto`.
- **The tokens part counts raw tokens, whatever the model.** Cache tokens are weighted as in ADR 0014.

**Worked by hand** (s06-es's prefixes and outputs from the cache run, without cache, the same token counts on every
model; real tokenizers differ):

| Call | Model | Input | Output | USD |
|---|---|---|---|---|
| 1 | Nova Lite | 2,952 | 149 | 2,952 × 0.06 / 1e6 + 149 × 0.24 / 1e6 = 0.0002129 |
| 2 | Nova Lite | 4,268 | 180 | 0.0002993. Its tool call fails, so `error_herramienta` escalates. |
| 3 | Haiku 4.5 | 4,548 | 107 | 0.0055913 |
| 4 | Haiku 4.5 | 4,733 | 275 | 0.0067188. `responder` with `abstenida`, so `abstencion` escalates. |
| 4 (again) | Sonnet 4.6 | 4,733 | 275 | 4,733 × 3.30 / 1e6 + 275 × 16.50 / 1e6 = 0.0201564 |
| 5 | Sonnet 4.6 | 5,133 | 492 | 0.0250569 |
| **Task** | | 26,367 | 1,478 | **0.0580356 USD and 27,845 tokens** |

- The router's task makes 6 paid calls: call 4 is sent twice.
- The 5 calls of the same task on Haiku 4.5 alone cost 0.0304139 USD for 22,837 tokens.
- Pricing the routed calls at Haiku's price, the loop's way, would give 0.0371327 USD. That is 36% less than the true
  0.0580356, and it is the error this rule removes.
- A test checks this case.

### 5. Configuration

The values in `ia/config.py`, repeated in `agente/construccion.py` because `ia/` is not in the Lambda package. A test
checks that the two are equal.
- **`RUTEO = "off"`** by default. The modes are `off` and `r1`.
  - With `off`, the request is activity 3's byte for byte (`tests/snapshots/converse_semana19.json`), and the
    profiles, the IAM statements and the metrics are today's.
- **`RUTEO_CANDIDATOS`:** the three profile ids above, cheapest first. Haiku 4.5 is `MODELO_ID` itself, so its id
  still lives only in `config.py`.
- **`RUTEO_REGLAS`:** the 9 signals, the scope `resto_de_la_tarea`, `max_escalamientos` 2, `pasos_presion` 7 and
  `tokens_presion` 50,000.
- **`CACHE_POR_MODELO`:** §3's table. It applies when `RUTEO=r1` and `CACHE_PROMPT` is not `off`. With
  `CACHE_PROMPT=off` no model gets a point.
- **The live run:** `desplegar.sh` with `RUTEO=r1` and `CACHE_PROMPT=historial`, at synth time, as activity 3 did.

### 6. Profiles and IAM

- **One application inference profile per candidate.** Each is a copy of its `us.` system profile.
  - The names are `semana19-agente` (Haiku 4.5, today's), `semana19-agente-nova-lite` and
    `semana19-agente-sonnet-4-6`.
  - Each is tagged `proyecto` and `componente=agente`, like activity 2's.
  - No new tag key, so no tag activation is needed. Cost Explorer already separates the models by usage type, and
    Sonnet and Haiku come as separate Marketplace products.
- **The agent role, with `RUTEO=r1`,** allows `bedrock:InvokeModel` on exactly the three application profile ARNs and
  their three foundation models. The foundation models are allowed in any Region, as today's
  `ModeloDeHaikuPorConverse`, because the `us.` profiles route to several Regions. The permissions boundary
  (`ModeloDelAgenteDelLimite`) gets the same foundation models.
- **With `RUTEO=off`,** the role is today's.
- **Tests:**
  - the role names only the candidates and nothing else (no `global.` profile, no other family);
  - with `off`, the statement is today's;
  - with a candidate removed from the configuration, its ARN leaves the policy.
- **cdk-nag stays at zero findings,** with no suppression added for R1. The existing `ModeloDeHaikuPorConverse` IAM5
  reason covers the foundation-model wildcard, and its text is updated to name the candidates.

### 7. Telemetry

- **Chat spans.** Each `chat` span gets three things:
  - `gen_ai.request.model` and `gen_ai.response.model`, the model that served the call. Converse does not return the
    model, so it is the id the router called.
  - The route: `lab.route.initial`, the task's first model; `lab.route.escalated`, true from the first escalation on;
    and `lab.route.reason`, the signal that caused this call's escalation, or nothing.
  - The discarded answer of a response signal, which is a span of its own, so every paid call has one.
- **The agent span** gets the task's escalation count and the strongest model it reached.
- **EMF stays at 10 custom metrics, CloudWatch's free tier** (`linea_base.md` §4.7).
  - A model dimension on activity 2's 8 per-query metrics would make 8 × 3 = 24 metrics. A route dimension would
    double that again.
  - So 6 of the 8 metrics lose their dimensions and become 6 metrics: the four token metrics, `Pasos` and
    `LatenciaMs`.
  - `CostoUSD` and `Respondida` keep the dimension `Ruta`, which is `fija` or `r1`, the deployment's `RUTEO`. That is
    2 × 2 = 4 metrics.
  - The total is **10**, and `metricas_posibles()` holds it in a test.
  - The share of calls per model, and the escalations and their reasons, come from the spans, which are already log
    lines, not from metrics.
- **The language dimension stays out** (activity 2's open item). It would take `CostoUSD` and `Respondida` to 8
  metrics and the total to 14. The router's language signal is computed from the text and is not a dimension.

## Consequences

- `agente/modelo.py` gets the router, behind `invocar`. The week 13 loop, the deterministic layer, the guardrails and
  `PRESUPUESTO_TAREA` do not change shape. With `RUTEO=off` nothing changes.
- `agente/converse_adaptador.py` gets the Nova request: the tool schema reduced to its three top-level keys and greedy
  decoding. The Claude request does not change, and a snapshot test checks it.
- `agente/presupuesto.py` prices each call by its model, and the loop's single-model cost is no longer the span's.
- **A loop step can be two paid calls.** That happens when a response signal sends the same request again. The loop's
  12-step limit counts steps; the spans count calls.
- **The comparison that decides R1 (step 5):**
  - success and the silently-wrong rate, against the cache run (17/20) and also against week 17 (20/20);
  - the share of calls per model, the escalations and their reasons;
  - the cost median, the p95 and the total;
  - latency p50 and p95;
  - tasks cut by the budget;
  - week 10's verdict.
  - It is rejected if it saves money and loses success.

## Costs

- **Design and offline code:** $0.
- **Profiles:** an application inference profile costs nothing by itself; only its calls are billed (activity 2).
- **The live run** is estimated in the prediction (step 4), before any run. It needs Manuel's OK and runs under a hard
  cap in USD and tokens.
