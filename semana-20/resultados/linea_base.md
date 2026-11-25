# Week 20, activity 1: baseline, regression gate, prices and limits

Date: 2026-11-23. Cost: $0. The only AWS calls were free and read-only: the Price List, Service Quotas, `bedrock:ListPromptRouters` and STS.

- Source marks, as in week 19:
  - **M**, measured: read from an AWS API, with its SKU or quota code;
  - **D**, documented: read in the official docs, with the link;
  - **N**, not found.
- Files:
  - [`precios.json`](precios.json), written by [`linea_base/precios.py`](../linea_base/precios.py) `--si`;
  - [`linea_base_verificacion.json`](linea_base_verificacion.json), written by [`linea_base/verificar.py`](../linea_base/verificar.py).

## 1. The week 19 hand-off, checked

`verificar.py` re-runs the hand-off list of `preparar/verificar_entorno.py`. All five items exist:
- `modelo.invocar`;
- the quote model;
- `MODELO_ID` in `ia/config.py`;
- the span exporter;
- `etiquetas()` on every stack.

The baseline file parses, with every field week 20 reads. The `prod` window is still to schedule: week 19 never deployed `prod`.

## 2. The baseline, recomputed

Every figure of the plan's table matches the file (`contra_el_plan.ok`, [linea_base_verificacion.json](linea_base_verificacion.json)). The table is computed over **all 22 rows**, including the 2 warm-up rows, so three of its labels needed a fix:

| Figure | Plan (22 rows) | 20 main tasks only |
|---|---|---|
| Rows with a cost | 19 (the plan said "of 20"; it is 19 of 22) | 17 of 20 (3 aborted by the script's cap) |
| Model cost per task, median and maximum (USD) | 0.03708 and 0.06301 | 0.03708 and 0.06301 |
| Input tokens, median | 26,266 | 26,972 |
| Output tokens, median | 1,348 | 1,230 |
| Cache read and write tokens | 0 and 0 | 0 and 0 |
| Steps, median and maximum | 6 and 8 | 6 and 8 |
| Latency, median and maximum (s) | 23.6 and 49.95 (the maximum is the cold warm-up) | 23.52 and 30.13 |
| Success (week 13 verifier) | 9 of 20 | 9 of 20 |

The plan's Log records the correction. Week 20 compares against the 20 main tasks.

## 3. The regression gate: accepted without passing (Manuel, 2026-11-23)

Week 19 activity 10 decided that the 9/20 regression goes to week 20. Its README lists the fixes and says each one needs a paid run. The corrected run (§3, "Result") reached 16/20, still a regression under that rule. Manuel accepted it as week 20's baseline, stated as not passing (`compuerta.estado` = `aceptada_sin_pasar`).

### The 11 failures, by cause

| Cause | Tasks | What the saved spans show |
|---|---|---|
| Per-task budget (`presupuesto_tarea`) | r02-es, c06-es, r02-en, r05-en, r12-en | Cut at 7–8 steps and 36,797–42,692 tokens; see below |
| The script's cumulative cap (`no_corrida`) | v01-en, a01-en, n01-en | The cap included the two discarded runs, and these are the last 3 tasks in the order |
| Abstains where an answer is expected | c02-es, c02-en | c02-es abstains after only `describir_esquema`, without looking up the rule. c02-en finds R-OC-APRUEBA and still abstains |
| Wrong answer | c06-en | Answers in Spanish, although the system prompt says "Write the answer in the language of the task"; key exactness 0.5 |

### Why the budget cuts tasks that week 13 finished

These figures compare the same tasks: the 3 week 13 runs per task (`semana-13/resultados/eval_haiku_low_detalle.jsonl`) against the AWS run.

- **More steps.**
  - Haiku 4.5 on Bedrock makes 1.14 tool calls per step, against Haiku 5.5's 1.5.
  - The median task takes 6 steps, against 4. The ratio per task is 1.27.
  - It issues its queries one by one. r02-en made 12 `ejecutar_sql` calls, each returning a small result, instead of combining them, although the prompt says "You may request several independent tools in the same turn".
- **The cost of each step grows.** Every step sends the whole history again, so the total tokens grow faster than the steps. On the 12 tasks the budget did not cut, total tokens are 1.07 times week 13's.
- **The budget's estimate is an upper bound.**
  - It takes characters ÷ 1.5 × 1.10 (`semana-17/presupuestos/estimacion.py`), about twice the real tokens of a first call (2.7 characters per token).
  - At 37–43k tokens spent, the 46,000-token cap can no longer reserve the next call plus the minimum output of 1,300 tokens.
- **The cap was calibrated on another model.** The 46,000 tokens are the p99 of 252 Haiku 5.5 runs. The port scaled the USD part by the price ratio (0.0063 × 11 = 0.0693 USD) and kept the token part unchanged.

### The fix (approved by Manuel on 2026-11-23)

1. **Baseline fixes with no `cachePoint`.**
   - Caching is activity 3's lever, measured alone against this baseline. If the baseline already had it, there would be nothing to measure it against.
   - A cache point on the system prompt and tools alone would not cache on Haiku 4.5 anyway (§4.1).
2. **One re-run of the 20 tasks with the per-task cap raised to a ceiling.**
   - The ceiling: 0.12 USD and 100,000 tokens per task, so no task is cut, plus a cap of 2.50 USD for the run.
   - The run gives the regression verdict and the uncut Haiku 4.5 distribution together. The new per-task cap is then set from that distribution, as week 17 did. Week 19 said it could not do this, because every run it had was cut.
   - The script's cap counts this run only, not the discarded ones, so no task is left `no_corrida`.
3. **No prompt change aimed at c02 or c06-en.**
   - Both are model-quality failures on two of the 20 tasks. A prompt tuned to them would fit the eval set, not the product.
   - They become the first escalation cases for activity 4 (routing to a stronger model on a language mismatch or a doubtful abstention).
4. **The estimate, from the quote model.**
   - `lab` fixed cost: 0.04189 USD/h (`semana-19/costos/modelo.py`, `lineas_fijas_hora`), about 0.13 USD for a 3-hour session.
   - Model: about 0.90 USD expected (20 tasks at about 0.045 USD each), with the hard cap at 2.50 USD.
   - **Expected total: about 1.05 USD**, against the weekly cap of 10 USD.
   - Then `destruir.sh --si --todo`, and the inventory at "nada".

### How it runs

The code, at $0:
- The agent's per-task budget is a config value, `PRESUPUESTO_TAREA`:
  - `semana17` (the default) keeps week 17's calibration and leaves the week 19 templates unchanged;
  - `techo_semana20` sets the ceiling;
  - an unknown value stops the agent and the synth.
  - Code: `semana-19/agente/construccion.py` and `infra/cdk/app.py`; tests: `test_agente_construccion.py` and `test_infra_presupuesto.py`.
- [`linea_base/corrida.py`](../linea_base/corrida.py) is week 19's eval with its own caps (2.50 USD and 2,200,000 tokens), counting only its own files.
  - It checks that the deployed agent runs `techo_semana20`, and sends no task otherwise.
  - Output: `corrida_corregida/` and `corrida_corregida_detalle.jsonl`.

The session, from the week 19 worktree:
1. `desplegar.sh --si` (Manuel): control, bootstrap, base, datos, ia, then the loader and the ingestion.
2. `computo` with `PRESUPUESTO_TAREA=techo_semana20`, deployed with the deploy profile.
3. `usuarios.py` and `corrida.py --si` (Manuel, admin profile).
4. `destruir.sh --si --todo`, and the inventory at "nada".

### Result (2026-11-23)

Files:
- [`corrida_corregida/crudo_eval.json`](corrida_corregida/crudo_eval.json): the raw run;
- [`corrida_corregida_detalle.jsonl`](corrida_corregida_detalle.jsonl): one line per task;
- the gate is in [`linea_base_verificacion.json`](linea_base_verificacion.json).

| | Week 19 (activity 8) | Corrected run |
|---|---|---|
| Success | 9/20 | **16/20** (Wilson 95 % [0.584, 0.919]) |
| Spanish / English | 7/10 / 2/10 | 8/10 / 8/10 |
| Cut by the per-task budget | 5 | **0** |
| Not run (the script's cap) | 3 | 0 |
| Model spend, warm-up included | — | **1.008147 USD** (expected 0.99, cap 2.50) |
| Warm latency, p50 / p95 | 23.52 / 30.13 s | 21.57 / 45.02 s (n = 20) |
| Trajectory (week 17 graders) | 7 OK of 17 | 8 OK of 20, mean score 0.912; 11 fail on `pasos` |
| Regression (week 10's rule, against week 17 local 20/20) | yes | **yes**: 0.8 in Spanish and in English, against a 0.9 threshold per language, and 0.8 in total against 0.95 |

**The four failures:**
- **c02-es and c02-en** abstain, as in week 19.
- **r05-es** abstains after 11 steps.
- **r05-en** stops on the loop's own step limit (`max_pasos` = 12), not on the budget.
- c06-en now answers correctly.

All four fail on model quality.
- A per-task ceiling would not fix them, and neither would another run.
- A prompt tuned to them would fit the eval set.
- **Manuel's decision (2026-11-23):** this run is week 20's baseline, stated as not passing. Activity 4 routes these cases to a stronger model and measures against it.

**Haiku 4.5's distribution, uncut** (the 20 main tasks):

| Figure | Value |
|---|---|
| Tokens per task: median, p90, maximum | 25,450, 74,841, 87,831 (r05-en, at the step limit) |
| The most expensive successful task | 78,674 tokens and 0.11411 USD (r02-en) |
| Cost per task: median and maximum | 0.03408 and 0.11411 USD; 0.92782 USD for the 20 |
| Steps: median and maximum | 5 and 12 |
| Input and output tokens, median | 24,099 and 1,266.5 |
| Cache read and write | 0 and 0 (no `cachePoint`, as decided) |

**The cap from here on:**
- Week 20 keeps the ceiling (`techo_semana20`, 0.12 USD and 100,000 tokens) as its operating cap. It is 5 % above the most expensive successful task.
- No new calibrated value is written yet. Week 17 took the p99 of 252 runs, and 20 tasks give no p99: their maximum would be a made-up percentile.
- Activity 9, the optimized run, calibrates it on its own repeated runs, with caching on.

One caveat: the warm-up task s02-es has incomplete spans (21 of 22 complete). It does not count toward success, and its tokens and cost are recorded.

## 4. Prices and limits

### 4.1 Prompt caching (Haiku 4.5)

| Item | Value | Source |
|---|---|---|
| Cache read, regional and global (USD per 1M tokens) | 0.11 and 0.10 (0.1× input) | M, SKUs VJXPZKPF7EDCFXN3 and V6YWAS4REFW47M5K |
| Cache write, 5-minute TTL | 1.375 and 1.25 (1.25× input) | M, CDG7WESKYQ9N9KDN and W4WDUUMEWN8ZMKYT |
| Cache write, 1-hour TTL | 2.20 and 2.00 (2× input) | M, WTCBCUF6TGQ5M3NB and 3Z3HTWANN6PKFUBJ |
| Input and output, on demand, regional | 1.10 and 5.50 | M, JQDUC8Q4K8C6GSGH and X629GDA2GXAP6R54 |
| Input and output, on demand, global | 1.00 and 5.00 | M, DY4B4Q3TRTAY8V6G and XADKFYXVGBFBJSU7 |
| Minimum tokens per cache point | **4,096** (Haiku 5.5: 512) | D, [prompt-caching](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html) |
| Cache points per request | 4 | D, same page |
| TTL | 5 minutes and 1 hour (Nova: 5 minutes only, and `ttl` must be left out) | D, same page |
| Where a cache point may go | `system`, `messages` and `tools` | D, same page |
| With cross-region profiles | Supported. A request served elsewhere writes a new entry instead of reading one | D, same page |

**The finding for activity 3:**
- The fixed prefix, the system prompt plus the tool definitions, has 7,486 characters, about 2,773 tokens (`prefijo_cacheable`). That is below Haiku 4.5's minimum of 4,096.
  - This is the week 13 catalog: 6 tools plus `responder`.
  - The deployed catalog has one tool fewer (no `validar_sql`), so its prefix is smaller still.
- So the fix week 19 named, a cache point on the system prompt and the tools, would cache nothing.
- The cache point has to go at the end of the message history. The prefix passes 4,096 tokens from about the third call on (the first is about 2,800 tokens, and each step adds the answer and the tool results), and each later step then reads the earlier ones from the cache.
- Activity 3 designs it that way, with a test of the minimum.

### 4.2 Batch inference

| Item | Value | Source |
|---|---|---|
| Discount | 50 %: Haiku 4.5 regional batch 0.55 and 2.75 (8GAKPXRDT9CSGWEC, E56Y3URFEMX4ZGDC); Nova Micro 0.0000175 and 0.00007 per 1K; Nova Pro 0.0004 and 0.0016 per 1K | M |
| Records per job | minimum 100, maximum 100,000 (Haiku 4.5, Nova Micro, Lite, 2 Lite and Pro) | M, Service Quotas (`cuotas.lote`) |
| Size | 5 GB per job for Haiku 4.5 and Nova Micro (100 GB for Nova Lite and Pro); 1 GB per file | M |
| Jobs in progress | 100 per model | M |
| Format | JSONL, `{"recordId", "modelInput"}`, with `modelInput` as the InvokeModel or Converse body. The output is one JSONL per input in S3, order not kept, plus `manifest.json.out` with record and token counts | D, [batch-inference-data](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference-data.html), [batch-inference-results](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference-results.html) |
| Turnaround | Not stated. `timeoutDurationInHours` defaults to 24 h, and can be set from 24 to 168 h | D, [batch-inference-create](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference-create.html) |
| Models | Haiku 4.5 through a cross-region profile only; Nova Micro, Lite, Pro, and 2 Lite (cross-region only) | D, [batch-inference-supported](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference-supported.html) |
| Limits that matter | Converse jobs do not support tools (`toolConfig` gives a 400). Prompt caching does not apply to batch | D, same pages |

**For activity 5:** the job needs at least 100 records.
- Data dictionary enrichment: one record per column of the `legado` views.
- The judge: the week 19 prompts, repeated.

Neither job may use tools, which fits both.

### 4.3 Intelligent Prompt Routing

- The region has three routers (`enrutadores`, M), all `default`:
  - Nova (Lite and Pro, falling back to Pro);
  - Anthropic (Claude 3 Haiku and Claude 3.5 Sonnet);
  - Meta (Llama 3.1 8B and 70B).
- **None includes Haiku 4.5**, the model LegacyBridge runs. A configured router takes two models of one family (D, [prompt-routing](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html)). The page lists only Nova and Llama models for configured routers.
- The page says routing is "only optimized for English prompts", and half the golden set is Spanish. It states no price (N).
- **For activity 4:** R2 can only be the Nova router (Lite → Pro). That swaps the agent's model family, so it is measured as such, or documented and not built. Activity 4 decides with the R1 numbers.

### 4.4 Routing candidates

| Model | Input / output (USD per 1M) | Source | Tokens and requests per minute (cross-region) | Quota codes |
|---|---|---|---|---|
| Nova Micro | 0.035 / 0.14 | M, XAR69MSGZSU6FEM9, YUSGHKDUPQRC75RK | 8,000,000 / 400 | L-DC7FF66C, L-3F110E0F |
| Nova Lite | 0.06 / 0.24 | M, QRGWJ3P8FT28EYX2, CBZ6A6U7XK8WJ3KA | 8,000,000 / 400 | L-7C42E72A, L-89F8391A |
| Nova 2 Lite | 0.33 / 2.75 | M, FY8T82UUN7VZR55K, DY69Q8C3F88CHA2Q | 8,000,000 / 200 | L-C6F5908D, L-F06F1187 |
| Nova Pro | 0.80 / 3.20 | M, 8X836UXRHN5Q5T2H, ARFVY95XGU794VBG | 2,000,000 / 50 | L-C0326783, L-ED46B8C5 |
| Haiku 4.5 (today) | 1.10 / 5.50 | M, §4.1 | 5,000,000 / 50 | L-58BE175A, L-CCA5DF70 |
| Sonnet 4.5 | 3.30 / 16.50 | M, SSK4DT4JBRUQJYP5, 3YN5KGC2HJU9VC5A | 5,000,000 / 50 | L-F4DDD3EB, L-4A6BFAB1 |
| Sonnet 4.6 | 3.30 / 16.50 | M, KPFGPZJ8VWMREGAV, GMB9AQ5DYNAGYZEC | 6,000,000 / 50 | L-15B8E632, L-00FF3314 |

Haiku 5.5 is still at 0 (week 19, `semana-19/resultados/linea_base.md` §10). The cheaper tier is Nova (Micro, Lite), and the stronger one is Sonnet.

Nova 2 Lite's usage type is `Nova2.0Lite`, so `precios.py` missed it until it matched that name too. Its output is priced 2.75 per 1M, half of Haiku 4.5's and 11 times Nova Lite's. Its rows also show:
- a global cross-region price of 0.30 / 2.50 (EPMQ24NAG4R6FPX8, PT8HC9XDED4UMEZX);
- batch and flex at 0.165 / 1.375 (5UDDRHH997B9FJ63, 9695KVZFNHZKXKKM);
- priority at 0.5775 / 4.8125 (5ATX9W7RD5XA8J66, R8KFTUX2HDGAD9J3);
- cache reads at 0.0825 (NZS2WHKW9KB4K2QH);
- provisioned throughput with no commitment, at 60.50 per model unit per hour (RAXDRDKBA5JXTZUR).

A quota alone does not prove the model can be called. Activity 4 checks each candidate with one call, estimated first.

### 4.5 Provisioned throughput and latency-optimized

- **Haiku 4.5: reserved only**, priced per TPM-hour, regional (Geo) and global:
  - 1 month: input 0.066 / 0.06, output 0.33 / 0.30 (WFDJPN3RNP3N6NWZ, YJFU5XBU67BFQMCX, NBCPQTKQRKGSQ75J, SHU8SWFE8GBAQTTK);
  - 3 months: input 0.0594 / 0.054, output 0.297 / 0.27 (X6EFEEBNCHT9594X, RMNG53S49ZTEK6HS, NNDNGXGPTYYKYS5U, P2NHPZ82T9FY9YPQ).
- No-commitment price: N (no such row for Haiku 4.5).
- **Latency-optimized:** only Nova Pro has it, at 0.001 / 0.004 per 1K (SMX6CK9YP4NWDC8W, 9ZG8UHUQKAKDXPNY). Haiku 4.5 has none (N).
- **For activity 6:** the price is per throughput-hour with a commitment. The break-even is computed against on-demand at client volumes. Nothing is bought.

### 4.6 Application inference profiles

- Created with `modelSource` set to the cross-region (system) profile, for example `us.anthropic.claude-haiku-4-5-…`, with `tags` at creation (D, [inference-profiles-create](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-create.html)).
- They are priced as the model in the calling region (D, [inference-profiles](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles.html)).
- Their tags track the cost of on-demand calls, once the tag keys are activated in Billing (D, [tagging](https://docs.aws.amazon.com/bedrock/latest/userguide/tagging.html)).
- **How they show in Cost Explorer: N.** The docs do not say. Activity 2 checks it on its first paid call, with one authorized Cost Explorer call. It also depends on Manuel activating `componente`.
- **Cost allocation tags** ([`etiquetas_costo.json`](etiquetas_costo.json), one `ListCostAllocationTags` call at 2026-11-23T23:22:26+00:00, 0.01 USD, with Manuel's OK):
  - `proyecto` has been Active since 2026-11-14.
  - `componente` is not listed yet, so it cannot be activated: Billing has not yet seen it on a tagged resource. The week 20 stacks carried it from 2026-11-23.
  - Manuel activates it once it shows, before activity 2 reads cost by component.

### 4.7 CloudWatch and X-Ray

| Item | Paid price | Free tier (D, [CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/)) | Source of the price |
|---|---|---|---|
| Custom metrics (EMF too) | 0.30 per metric-month for the first 10,000 | 10 metrics | M, KG586CTNGQ4VRZKZ |
| Standard / high-resolution alarm | 0.10 / 0.30 per alarm-month | 10 standard alarms | M, EVETVUGEN3MUTMXM, 7BK9TRWG8E43D4AJ |
| Dashboards | 3.00 per dashboard-month, beyond the free ones | 3 dashboards of up to 50 metrics; the Price List has a global 0–3 tier at 0 | M, ZXHCNVUBD6E8UPH8 (free tier), 5P8PBB6MXV325TDC, 8AWBXE5MPQY58BK4 (over 50 metrics) |
| Log ingestion | 0.50 per GB | 5 GB (ingestion, archive and Logs Insights scans together) | M, S8QGXX5R2BKKMDSJ |
| Logs Insights | 0.005 per GB scanned | in the 5 GB above | M, 466C636KV6VS3849 |
| X-Ray traces stored / accessed | 0.000005 / 0.0000005 per trace | 100,000 recorded and 1,000,000 accessed per month | M, Y6TW3M2TDT7SJYK8, 3TP6FV8W3FH2HE28 |
| Transaction Search, spans indexed | 0.00000075 per span | 3 months free, including 1M indexed spans | M, FBU5ADNKR93A95EP |
| Application Signals ingestion | 0.35 per GB for the first 10 TB | 100 GB in the same 3 months | M, 4DAN5Z24DZ67DTM2 |

- **EMF:** the metrics a log line declares are charged as custom metrics, and the line itself as log ingestion. The page states this only for Container Insights; for EMF in general it is not stated, so the design assumes both.
- **Dashboards** are priced globally, with location `Any` and no `regionCode`, so `precios.py` reads them by usage type.
- **For activity 8:** stay at 10 metrics or fewer, counted as metric name × dimension values, plus 3 dashboards or fewer. The metric list is written before the stack.

### 4.8 CloudWatch generative AI observability

- It covers Bedrock model invocations with any model, and agents: managed, self-hosted or third-party, with traces through the ADOT SDK (Strands, LangChain and LangGraph are named). It is not AgentCore only.
- The page lists no other prerequisite and no own price. It is billed as the CloudWatch and X-Ray lines above.
- D, [GenAI-observability](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/GenAI-observability.html). Activity 7 evaluates it on the same traces.

### 4.9 Cost Anomaly Detection

**Not checked through the API.** `ce:GetAnomalyMonitors` is a Cost Explorer call (0.01 USD) and needs Manuel's OK. Manuel checks it in the console, under Billing → Cost Anomaly Detection. The answer goes to activity 8's alarm design.

**Checked in the console (Manuel, 2026-11-24):** a monitor is on, and it shows the account's spend within its normal range, with no anomaly flagged. Week 19 left the monitor out of its stack, so this one lives outside the IaC.
- Activity 8 relies on it for the account-level anomaly signal. It does not create a second one; it adds only the per-query alarms (cost and tokens above p95 plus margin).
- What is not recorded: the monitor's type and its alert subscription. They were read in the console only, with no API call.

## What activity 1 leaves to the next ones

- Activity 2: application inference profiles and their tags; the first Cost Explorer check of the split.
- Activity 3: the cache point at the end of the history, with the 4,096-token minimum tested; the budget counting cache tokens.
- Activity 4: R1 between Nova (Micro and Lite) and Sonnet, around Haiku 4.5. R2 only as the Nova router, measured separately. c02 and r05 are its first escalation cases (c06-en passed in the corrected run).
- Activity 5: batch jobs of at least 100 records, without tools.
- Activity 6: provisioned throughput priced with a commitment only; no purchase.
- Activities 7 and 8: at most 10 metrics and 3 dashboards, inside the free tier.
- Every comparison is against the corrected run (§3): 16/20, a regression under week 10's rule, accepted as the baseline.
