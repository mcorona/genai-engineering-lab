# Week 3 question and SQL pairs (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 3 README](../README.md)

The pairs of a Spanish question and its reference SQL over the LegacyBridge legacy schema. `generar_pares.py` fills
templates with values from the database, runs every candidate SQL in a read-only transaction, drops duplicates,
gold-set overlaps and queries without usable rows, and splits the rest 80/20 by template into training and
evaluation pairs. `preparar_lora.py` then splits the training pairs into the train and validation files that mlx-lm
expects. The evaluation pairs never enter training. The week README gives the counts in [Data](../README.md#data).

**Why it is in Spanish:** the questions are Spanish, and the system prompt that describes the schema is Spanish,
because the lab measures a model that turns Spanish questions into SQL. Translating them would change what was
measured. The SQL itself uses the legacy schema's own names.

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `pares_train.jsonl` | Training pairs, one chat example per line (system prompt with the schema, question, reference SQL) | Written by `generar_pares.py`; read by `preparar_lora.py` |
| `pares_eval.jsonl` | Evaluation pairs, in the same format. Held out from all training | Written by `generar_pares.py`; read by `evaluar_sql.py` |
| `lora/*.jsonl` | `pares_train.jsonl` split into `train.jsonl` and `valid.jsonl` (the validation loss during fine-tuning) | Written by `preparar_lora.py`; read by `mlx_lm.lora` and by `../../semana-04/entrenamiento/generar_teacher.py` (`train.jsonl`) |
| `rechazados.jsonl` | Candidates dropped after running their SQL, with the reason | Written by `generar_pares.py` |
| `resumen.json` | Counts of the generation: candidates, accepted, split and rejected, by reason and by template | Written by `generar_pares.py` |

## Keys

| Key | Meaning |
|---|---|
| `plantilla` | The template the candidate comes from |
| `pregunta` | The question, in Spanish |
| `motivo` | Why the candidate was rejected. `sin filas útiles` = no usable rows: the SQL ran but returned no rows, or only NULLs |
| `candidatos` | Candidates generated |
| `aceptados` | Candidates accepted (their SQL ran and returned usable rows) |
| `rechazados` | Candidates rejected |
| `motivos` | Candidates dropped, per reason |
| `por_plantilla` | Accepted pairs per template |
