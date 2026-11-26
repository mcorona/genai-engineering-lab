# Week 20, activity 2: cost attribution

Status: closed. The code is merged (#333, #335) and the run is done (2026-11-24, 4/4 tasks). Spans, EMF and Cost
Explorer by `componente` agree to the last digit: 0.0985182 USD for the 4 tasks (section 4).

## 1. Application inference profiles

| Component | Profile name | Copies (system profile, `ia/config.py`) | Used in |
|---|---|---|---|
| `agente` | `semana19-agente` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | the agent Lambda, from this activity |
| `juez` | `semana19-juez` | `us.amazon.nova-pro-v1:0` | the judge (activity 9, if a model evaluation job accepts the profile) |
| `enriquecimiento` | `semana19-enriquecimiento` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | batch enrichment (activity 5, if batch accepts the profile) |

- They live in the `semana19-ia` stack (`AWS::Bedrock::ApplicationInferenceProfile`), cost nothing at rest, and are
  removed with the stack. The teardown inventory lists them (`perfiles_inferencia_aplicacion`) and checks their ids.
- Each profile is tagged `proyecto=semana19`, `perfil=<lab|prod>` and `componente=<component>`. The component tag
  overrides the stack's `componente=ia` (CDK tag priority 200, checked in the synth).
- Costs reach Cost Explorer and CUR through the profile's tags once the tags are active, as daily totals per usage
  type, never per request (D, [cost-mgmt-application-inference-profiles](https://docs.aws.amazon.com/bedrock/latest/userguide/cost-mgmt-application-inference-profiles.html), read 2026-11-23).
  Tags only count from activation onward, and can take up to 24 h to show.
- **Change from the plan:** "MODELO_ID becomes the agent's application profile ARN" cannot be done literally. The ARN
  holds the account and an id Bedrock assigns at creation, and the repo never holds the account. So `ia/config.py`
  keeps `MODELO_ID` as the copied system profile and adds the switch `USAR_PERFIL_DE_APLICACION`. The stack passes
  the agent profile's ARN to the Lambda in `MODELO`. With the switch off, `MODELO` is `MODELO_ID` and the role names
  the system profile, as in week 19. A synth test checks both values.
- **Change from the plan:** the judge's profile copies Nova Pro, not Haiku 4.5. The judge was chosen in week 19 to be
  a model other than the agent's.

## 2. IAM

| Policy | Change |
|---|---|
| Agent role, `ModeloDeHaikuPorConverse` | `bedrock:InvokeModel` on the agent's application profile (in place of the system profile) and on the Haiku 4.5 foundation model. No other statement allows a model call (synth test). |
| Boundary, `ModeloDelAgenteDelLimite` | Adds `application-inference-profile/*` in this account and Region. The id is not known before the deploy. Size still ≤ 6,144 (test). |
| Bootstrap execution policy `semana19-cfn-exec-ia` | `PerfilesDeAplicacionPorCfn`: create, delete, get and tag on `application-inference-profile/*`. `OrigenDeLosPerfilesPorCfn`: `CreateInferenceProfile` and `GetInferenceProfile` on the copied system profiles and their foundation models, which the Service Authorization Reference lists as resources of `CreateInferenceProfile`. |

- Access Analyzer `ValidatePolicy` was rerun on the 50 documents of each profile (free, read-only role). The findings
  are the same as before: 4 ERROR, all already disproved by a deploy; 12 SUGGESTION; 2 WARNING; 0 security findings
  (`semana-19/resultados/seguridad/validate_policy.json`).
- The application profile copies a cross-Region profile. The docs require the profile and the foundation model in
  each Region it routes to (D, [inference-profiles-prereq](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-prereq.html)),
  and the role's `foundation-model/<model>` in any Region covers that. The first task of the run is the live check.

## 3. Metrics from the spans (EMF)

- **Where:** on the agent span's own log line (`invoke_agent`, spans log group), as top-level EMF members next to the
  span's keys. The Lambda makes no extra call: PutLogEvents needs no header for EMF (D, [CloudWatch_Embedded_Metric_Format_Generation_PutLogEvents](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Generation_PutLogEvents.html)).
  The span's attributes are unchanged and still checked against week 17's locked shape.
- **Namespace** `LegacyBridge`. **Metrics, per query:** `CostoUSD`, `TokensEntrada`, `TokensSalida`,
  `TokensCacheLectura`, `TokensCacheEscritura`, `Pasos`, `LatenciaMs` (the agent Lambda's own time, not end to end),
  and `Respondida` (1 when the outcome is `respondida`; its average is the answered rate).
- **Dimensions (the written list, `agente/metricas.py`):** `Modelo` (`claude-haiku-4-5-20251001`) and `Ruta`
  (`fija` until activity 4's router). A value outside the list raises, so no metric appears without being counted.
- **Change from the plan: no language dimension.** The agent never receives the question's language: the API takes
  only the text, and the span's `lab.task.language` is a fixed `es`. A language dimension would file every English
  task under `es`. It comes back when the API carries the language.
- **Count:** 8 names × 1 model × 1 route = **8 custom metrics**, within CloudWatch's 10 free (`linea_base.md` 4.7). A
  test holds the count. Activity 4 adds models and routes, so it must recount (beyond 10: 0.30 USD per metric-month,
  prorated by the hour).

## 4. The small run (2026-11-24)

`semana-20/atribucion/corrida.py`, a dry run by default. Four tasks that passed in activity 1's corrected run
(`s03-es`, `s06-es`, `s03-en`, `v01-en`, 0.117 USD there), through the public API. Before sending anything it checks
that the agent runs the ceiling budget, the direct path, and an application profile in `MODELO`.

| Item | Estimate (USD) |
|---|---|
| Model, 4 tasks (cap in code: 0.40 USD, 400,000 tokens) | ≈ 0.12 |
| Stacks up about 2.5 h (control, base, datos, ia, computo; the base's endpoints and RDS at ≈ 1.1 USD/day) | ≈ 0.15 |
| CloudWatch: 8 metrics (free tier), log lines, GetMetricData of 8 metrics | < 0.01 |
| Cost Explorer the next day: one GetCostAndUsage | 0.01 |
| **Total** | **≈ 0.30** |

**Setup, as deployed:** the `componente` and `perfil` tags were activated in Billing on 2026-11-24. The stacks went
up the same day, and the agent Lambda's `MODELO` was checked to be the `semana19-agente` application profile, with
`PRESUPUESTO_TAREA=techo_semana20` and `CAMINO_HERRAMIENTAS=directo`. The three profiles carry `proyecto=semana19`,
`perfil=lab` and their own `componente`, checked with ListTagsForResource. Two fixes were needed before the deploy
went through (#335). CloudFormation's early validation rejected a comma in the profile description, and the
bootstrap step's echo printed the account. Both are now covered by tests.

**Result** ([crudo.json](atribucion/crudo.json), [emf.json](atribucion/emf.json),
[cost_explorer.json](atribucion/cost_explorer.json)):

| Task | Steps | Input tokens | Output tokens | USD (spans, recomputed) | Baseline USD (activity 1) |
|---|---|---|---|---|---|
| s03-es | 3 | 11,900 | 968 | 0.0184140 | 0.0175769 |
| s06-es | 5 | 22,323 | 1,442 | 0.0324863 | 0.0392337 |
| s03-en | 4 | 15,730 | 688 | 0.0210870 | 0.0315029 |
| v01-en | 5 | 19,429 | 938 | 0.0265309 | 0.0282931 |
| **Total** | **17** | **69,382** | **4,036** | **0.0985182** | 0.1166066 |

- 4/4 answered and verified, 2 per language. No cache tokens (caching is activity 3).
- The model spent 0.0985 USD against the 0.40 cap, below the 0.12 estimate.
- Time: the agent Lambda's own time adds up to 70.6 s (`LatenciaMs` sum: 70,624). End to end through the API it is 99.6 s (`latencia_s`).

The cost of a query three ways:

| Way | Source | USD (4 tasks) | Per task |
|---|---|---|---|
| 1. Spans | tokens of each agent span × Price List (1.10 / 5.50 per 1M, regional on-demand), recomputed | 0.0985182 | 0.0246296 |
| 2. EMF | sum of `LegacyBridge/CostoUSD` over the run's window (GetMetricData) | 0.0985182 | 0.0246296 |
| 3. Cost Explorer | `GetCostAndUsage` of 2026-11-24, `proyecto=semana19`, grouped by `componente` and usage type; the `agente` rows | 0.0985182 | 0.0246296 |

- **1 = 2, exactly.** The EMF value is the span's own `lab.run.cost_usd`, and the recomputation from tokens and
  Price List prices gives the same total. Every EMF line was accepted: the sum of `Respondida` is 4, and `Pasos`
  sums to 17, as in the spans.
- **3 = 1, exactly.** Cost Explorer has two `componente=agente` rows for the day:
  `USE1-MP:USE1_InputTokenCount-Units` at 0.0763202 USD and `USE1-MP:USE1_OutputTokenCount-Units` at 0.022198 USD.
  They are the spans' 69,382 input tokens × 1.10 and 4,036 output tokens × 5.50 per 1M. No other call went through
  the agent's profile that day, and the tag counted on the day it was activated. Queried on 2026-11-25 (one call,
  0.01 USD, Manuel's OK).
- **What the agent's tag does not cover.** The same query gives the rest of the day's cost by component. The total is
  0.1802167 USD for `proyecto=semana19`:

  | `componente` | USD (2026-11-24) | Main usage types |
  |---|---|---|
  | `agente` | 0.0985182 | model input and output tokens |
  | `base` | 0.0413889 | VPC interface endpoints (0.04), KMS keys |
  | `datos` | 0.0402394 | RDS `db.t4g.micro` and its storage (0.0187), VPC endpoint (0.02), S3 Vectors, Secrets Manager |
  | `computo` | 0.0000701 | API Gateway requests, read and write request units |
  | `ia` | 0 | |
  | no `componente` | 0 | KMS requests |

  The stacks' share (0.0817 USD) is the hours they were up that day, not a per-query cost. A query's full cost is the
  model's 0.0246 USD plus the per-hour cost of the stack, which is week 19's 0.037562 USD per hour
  ([`semana-19/resultados/costo_real.md`](../../semana-19/resultados/costo_real.md)).

**Teardown:** `destruir.sh --si --todo` ended in `"quedan": "nada"`, checked again with the read-only role. What is
left is the allowed list: the read-only role, and 5 KMS keys pending deletion between 2026-11-26 and 2026-12-01. The
teardown took 63 min, 40 of them in computo (the VPC Lambdas' network interfaces), close to 2026-11-23's times
(`semana-19/resultados/tiempos_despliegue.jsonl`).

Expected differences, written before the measurement, and what happened:
- 1 and 2 come from the same span values, so they should match to rounding, unless an EMF line is rejected
  (`AWS/Logs` EMF error metrics). They matched exactly.
- 3 is a daily total by usage type and includes any other call of the day through the profile. There was none, so it
  matched exactly too.
