# Week 7 NLQ-Inventory runs (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 7 README](../README.md)

The runs of `run_eval.py`, named by their UTC timestamp. Each run writes one detail file (one line per model and
question: the predicted SQL, whether its result matched the reference, the failure category and the token counts)
and one summary file (one entry per model and language). The later summaries also record the run's configuration
(`set`, `esquema`, `citas`, `sin_historial`). In CI, `ci/umbral.py` checks the accuracies of the latest summary
against a threshold.
The earlier runs, superseded by a fix to the evaluation or by a reworded question, are kept in `previos/`.

**Recorded evidence:** these are the raw outputs of the runs, kept exactly as recorded (not edited, not translated).
The questions are Spanish and English. The English summary of the results, with the reasons each earlier run was
superseded, is in the week README: [Results](../README.md#results-final-run-100-questions-per-language),
[Public results](../README.md#public-results-nlq-inventory-harder-set),
[Changes made during the evaluation](../README.md#changes-made-during-the-evaluation) and the second and third
iteration sections. The `costo_usd` values in the easy-set and harder-set summaries are the old costs (third-party
prices for OpenAI, no price for Gemini); the week README recomputes them with the official prices in
`../prices.json`.

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `detalle_*.jsonl` | Per-question detail of a current run | Written by `run_eval.py` |
| `resumen_*.json` | Per-model, per-language summary of a current run | Written by `run_eval.py`; read by `ci/umbral.py` |
| `previos/detalle_*.jsonl`, `previos/resumen_*.json` | The same files for the superseded runs | Written by `run_eval.py`, then moved here |

## Runs

The configuration of each run, read from its summary file. The runs whose summaries predate the configuration keys
are identified by their number of questions per language and by the week README; they used the only schema and
prompt that existed then (short schema, no citations).

| Run | Set | Schema | Citations | Previous turns |
|---|---|---|---|---|
| `20261022T051229Z` | easy | short | no | — |
| `20261022T052433Z` | harder | short | no | — |
| `20261022T053634Z` | harder | short | yes | — |
| `20261022T054450Z` | harder | full | no | — |
| `20261022T060607Z` | follow-up | short | no | with |
| `20261022T060832Z` | follow-up | short | no | without (`--sin-historial`) |
| `20261022T062215Z` | chains | short | no | with |
| `20261022T223719Z` | chains | short | no | with (after the second rewrite of `cad-14`) |
| `previos/*T044103Z`, `*T045121Z`, `*T045746Z` | easy, before the fixes to the evaluation | short | no | — |
| `previos/*T053250Z` | harder, with the first full-schema snapshot (missing the value hints) | full | no | — |
| `previos/*T053827Z`, `*T054731Z`, `*T054930Z` | follow-up, before the rewordings | short | no | with; `*T054930Z` without |
| `previos/*T061851Z` | chains, before the rewrite of `cad-14` | short | no | with |

## Keys

| Key | Meaning |
|---|---|
| `modelo` | Model, as `provider:model-id` |
| `ok` | The predicted SQL's result set matches the reference |
| `categoria` | Outcome: `correcta` (correct), `resultado_distinto` (valid SQL, different result), `error_ejecucion` (the database rejected the query), `sin_sql` (no valid SELECT in the answer) |
| `sql_predicho` | The SQL extracted from the model's answer |
| `latencia_s` | Latency of the call, in seconds |
| `tablas_citadas` | With `--citas`: the tables the model says it read (`null` without citations) |
| `tablas_referencia` | The tables of the reference SQL, taken with a regex (a proxy for the citation check) |
| `idioma` | Language: `es` or `en` |
| `correctas` | Correct answers |
| `exactitud` | Execution accuracy: correct answers over questions |
| `costo_usd` | Cost of the run for that model and language, in USD (`null` = no verified price at run time) |
| `costo_por_respuesta_correcta` | Cost per correct answer, in USD |
| `errores` | Failures per category |
| `esquema` | Schema in the prompt: `corto` (`schema.sql`) or `completo` (`schema_completo.sql`) |
| `citas` | The run asked the model to cite the tables it read |
| `sin_historial` | The run left out the previous turns (the follow-up control) |
| `citas_exactas`, `citas_precision`, `citas_exhaustividad` | Citation scores: exact match between cited and reference tables, precision, recall |
