# Week 20 results (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 20 plan](../Fas5Sema20.md)

The evidence of week 20, cost and performance of LegacyBridge on AWS. Activity 1 set the baseline: the corrected rerun
of week 19's eval, the regression gate, the Price List prices and the quotas. Activity 2 measured the cost of a query
three ways: from the agent's spans, from the EMF metrics and from Cost Explorer. Each activity has an English report
(`*.md`). Next to the reports are the raw files its scripts wrote. Week 20 has no README yet; its plan and Log are in
[Fas5Sema20.md](../Fas5Sema20.md).

**Recorded evidence:** the JSON and JSONL files are the raw outputs of the runs and of the AWS calls, kept exactly as
recorded: not edited, not translated. The scripts that wrote them are listed below. The English summary of the
results is in [linea_base.md](linea_base.md) (activity 1) and [atribucion.md](atribucion.md) (activity 2). This README
does not restate the results.

The run scripts read every `crudo*.json` file in their output folder to add up the spend against the cap, so do not
rename, move or delete them.

## Files

Script paths are relative to `semana-20/`.

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `*.md` | The English reports: [linea_base.md](linea_base.md) (activity 1: baseline, regression gate, prices and limits) and [atribucion.md](atribucion.md) (activity 2: cost attribution) | Written by hand from the raw files |
| `corrida_corregida/crudo_eval.json` | Activity 1: the raw corrected run of week 19's 20 gold-set tasks against the deployed endpoint, with the per-task budget raised to its ceiling | `linea_base/corrida.py` / `linea_base/verificar.py` |
| `corrida_corregida_detalle.jsonl` | Activity 1: one row per task of the corrected run, in the same schema as week 19's `eval_aws_detalle.jsonl` | `linea_base/corrida.py --informe` / `tests/test_atribucion_corrida.py` |
| `linea_base_verificacion.json` | Activity 1: the checks of the baseline, the regression gate and its decision, and the handoff items from week 19 | `linea_base/verificar.py` / `tests/test_linea_base.py` |
| `precios.json` | Activity 1: the Price List prices, the Service Quotas and the Bedrock prompt routers | `linea_base/precios.py` / `linea_base/verificar.py`, `atribucion/corrida.py` |
| `etiquetas_costo.json` | Activity 1: the one `ListCostAllocationTags` call, with its authorization and its result | Cost Explorer, cited in `linea_base.md` |
| `atribucion/crudo.json` | Activity 2: the raw run of four tasks through an application inference profile | `atribucion/corrida.py --si` |
| `atribucion/emf.json` | Activity 2: the sums of the `LegacyBridge` EMF metrics over the run's window | `atribucion/corrida.py --metricas` |
| `atribucion/cost_explorer.json` | Activity 2: the Cost Explorer query, grouped by the `componente` tag, and its result | `atribucion/corrida.py --cost-explorer` |

## Keys

| Key | Meaning |
|---|---|
| `fecha` | Date of the run or the call |
| `filas` | Rows: one per task |
| `resumen` | Summary of a run |
| `exito` | Success (per language and in total) |
| `gasto`, `tope` | Spend so far, and the spending cap |
| `presupuesto_del_agente` | The per-task budget the deployed agent ran with (`techo_semana20` = week 20's ceiling) |
| `idioma` | Language (`es`, `en`) |
| `estado`, `estado_esperado` | Final status, expected status |
| `latencia_s` | Latency in seconds |
| `trayectoria_ok` | The trajectory passes week 17's graders |
| `veredicto_juez` | The LLM judge's verdict |
| `compuerta` | The regression gate: successes, tasks, whether it regresses, and the decision (`aceptada_sin_pasar` = accepted as the baseline without passing) |
| `fallas` | The failed tasks, grouped by cause (for example `presupuesto_tarea` = the per-task budget, `tope_del_script` = the script's cap) |
| `traspaso` | The handoff items from week 19, each checked |
| `prefijo_cacheable` | The cacheable prompt prefix: its size against the model's minimum for prompt caching |
| `precios`, `cuotas`, `enrutadores` | Prices, quotas, prompt routers |
| `fuente` | Source |
| `llamadas`, `operacion`, `autorizacion` | Calls, the API operation, who authorized the call |
| `consulta`, `grupos` | The Cost Explorer query and its result groups |
| `CostoUSD`, `LatenciaMs`, `Pasos`, `Respondida` | EMF metrics: cost in USD, latency in milliseconds, steps, answered tasks |
| `TokensEntrada`, `TokensSalida`, `TokensCacheLectura`, `TokensCacheEscritura` | EMF metrics: input, output, cache read and cache write tokens |
| `costo_usd` | Cost in USD |
