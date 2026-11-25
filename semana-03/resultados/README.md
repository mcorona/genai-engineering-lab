# Week 3 SQL evaluation runs (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 3 README](../README.md)

The runs of `evaluar_sql.py` on the evaluation pairs (`../data/pares_eval.jsonl`). Each run is named with
`--nombre`, and writes one detail file (one line per pair: the model's SQL, the reference SQL and the checks) and one
summary file. `evaluar_sql.py --reevaluar` recomputes the checks of a saved detail file without calling a model and
writes a `*_reevaluado_resumen.json`. `estadistica.py` reads the detail files to compute the confidence intervals and
the paired comparisons.

**Recorded evidence:** these are the raw outputs of the runs, kept exactly as recorded (not edited, not translated).
The questions and the error messages are Spanish. The English summary of the results is in the week README:
[Results](../README.md#results), [Before and after](../README.md#before-and-after) and
[Decision](../README.md#decision). The distillation run is summarized in the
[week 4 training README](../../semana-04/entrenamiento/README.md#results).

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `base_detalle.jsonl`, `base_resumen.json` | Qwen3.8-27B, no rules in the prompt | Written by `evaluar_sql.py`; the detail file is read by `estadistica.py` |
| `base27b_reglas_*` | Qwen3.8-27B with all the business rules in the prompt (`--reglas`) | Written by `evaluar_sql.py`; the detail file is read by `estadistica.py` |
| `base27b_rag_*` | Qwen3.8-27B with only the rules selected for each question (`--rag`) | Written by `evaluar_sql.py`; the detail file is read by `estadistica.py` |
| `base7b_detalle.jsonl`, `base7b_resumen.json` | Qwen2.5-Coder-7B, no rules in the prompt | Written by `evaluar_sql.py`; the detail file is read by `estadistica.py` |
| `base7b_reglas_*` | Qwen2.5-Coder-7B with all the business rules in the prompt | Written by `evaluar_sql.py`; the detail file is read by `estadistica.py` |
| `lora7b_detalle.jsonl`, `lora7b_resumen.json` | Qwen2.5-Coder-7B with the week 3 LoRA adapter | Written by `evaluar_sql.py`; the detail file is read by `estadistica.py` |
| `destilacion150_*` | Qwen2.5-Coder-7B with the week 4 distillation adapter (checkpoint 150), evaluated with this week's script | Written by `evaluar_sql.py`; the detail file is read by `estadistica.py` |
| `*_reevaluado_resumen.json` | The checks of a saved run, recomputed without a model (`--reevaluar`) | Written by `evaluar_sql.py --reevaluar` |
| `sin_razonamiento_roto_base_*` | A discarded 27B run with reasoning turned off and a short output limit; most answers had no SQL. Its summary still carries the name `base`, the name it was run under | Written by `evaluar_sql.py` |

## Keys

| Key | Meaning |
|---|---|
| `plantilla` | The template the question comes from |
| `pregunta` | The question, in Spanish |
| `sql_modelo` | The SQL the model wrote (empty when no SQL was found in the answer) |
| `sql_referencia` | The reference SQL |
| `ejecuta` | The model's SQL runs and returns rows (a rate in the summary) |
| `coincide_resultado` | The model's rows equal the reference rows, order ignored. The primary metric (a rate in the summary) |
| `coincide_sql` | The SQL text equals the reference after normalization. A weak measure (a rate in the summary) |
| `modelo` | Model id |
| `nombre` | The run name given with `--nombre` |
| `pares` | Number of pairs evaluated |
| `por_plantilla` | Counts per template: `n` pairs, and how many execute and match |
