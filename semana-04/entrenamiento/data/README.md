# Week 4 teacher answers (Spanish data)

[Glossary](../../../docs/glossary.md) · [Week 4 README](../../README.md) · [Distillation and DPO README](../README.md)

The teacher model's answers to the week 3 training questions: Qwen3.8-27B, with the week 3 business rules in the
prompt, writes SQL for each question in `semana-03/data/lora/train.jsonl`. Each answer is executed and compared with
the reference SQL. `construir_datasets.py` turns these answers into the distillation set and the DPO set. The
evaluation pairs of week 3 never enter this step.

**Why it is in Spanish:** the questions and the system prompt are the Spanish ones of week 3, because the lab
measures a model that turns Spanish questions into SQL. Translating them would change what the student is trained
on.

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `teacher.jsonl` | The teacher's answer to every training question, with the checks: whether its SQL runs and whether its result matches the reference | Written by `generar_teacher.py`; read by `construir_datasets.py` |
| `teacher_reintento.jsonl` | A second attempt for the questions where the first pass produced no SQL. Its answers replace the empty ones | Written by `generar_teacher.py --reintentar`; read by `construir_datasets.py` |

## Keys

| Key | Meaning |
|---|---|
| `pregunta` | The question, in Spanish |
| `sistema` | The system prompt with the schema, without the rules (the rules are appended when the teacher is called) |
| `referencia` | The reference SQL |
| `sql_maestro` | The teacher's SQL (`null` when no SQL was found in the answer) |
| `ejecuta` | The teacher's SQL runs and returns rows |
| `coincide` | The teacher's rows equal the reference rows, order ignored |
| `finish` | The model's `finish_reason` (`length` means the output limit was reached) |
