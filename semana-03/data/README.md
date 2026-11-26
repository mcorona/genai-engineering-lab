# Week 3 question and SQL pairs (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 3 README](../README.md)

The pairs of a Spanish question and its reference SQL over the LegacyBridge legacy schema. `generar_pares.py` fills
templates with values from the database and drops duplicate questions and overlaps with the LegacyBridge gold set.
It runs every remaining SQL in a read-only transaction and rejects the queries that fail or return no usable rows.
It then splits the accepted pairs 80/20 by template, with seed 42, into training and evaluation pairs. `preparar_lora.py` then splits the training pairs into the train and validation files that mlx-lm
expects. The evaluation pairs never enter training. The week README gives the counts in [Data](../README.md#data).

**Why it is in Spanish:** the questions are Spanish, and the system prompt that describes the schema is Spanish,
because the lab measures a model that turns Spanish questions into SQL. Translating them would change what was
measured. The SQL itself uses the legacy schema's own names.

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `pares_train.jsonl` | Training pairs, one chat example per line (system prompt with the schema, question, reference SQL) | Written by `generar_pares.py`; read by `preparar_lora.py` |
| `pares_eval.jsonl` | Evaluation pairs, in the same format. Held out from all training | Written by `generar_pares.py`; read by `evaluar_sql.py` |
| `lora/*.jsonl` | `pares_train.jsonl` split 90/10 into `train.jsonl` and `valid.jsonl` (the 10% used for the validation loss during fine-tuning) | Written by `preparar_lora.py`; read by `mlx_lm.lora` and by `../../semana-04/entrenamiento/generar_teacher.py` (`train.jsonl`) |
| `rechazados.jsonl` | Candidates rejected after running their SQL, with their SQL and the reason. Duplicates and gold-set overlaps are only counted in `resumen.json` | Written by `generar_pares.py` |
| `resumen.json` | Counts of the generation: candidates, accepted, split and rejected, by reason and by template | Written by `generar_pares.py` |

## Keys

| Key | Meaning |
|---|---|
| `plantilla` | The template the candidate comes from |
| `pregunta` | The question, in Spanish |
| `motivo` | Why the candidate was rejected: `sin filas útiles` = no usable rows (the SQL ran but returned no rows, or only NULLs), or the database error |
| `candidatos` | Candidates generated |
| `aceptados` | Candidates accepted (their SQL ran and returned usable rows) |
| `rechazados` | Candidates rejected |
| `motivos` | Candidates dropped, per reason. Besides the rejection reasons, it can count `pregunta duplicada` (duplicate question) and `coincide con conjunto de evaluación` (matches the gold set); this run has neither |
| `por_plantilla` | Accepted pairs per template |
| `train`, `eval` | Pairs in the training and the evaluation split |
