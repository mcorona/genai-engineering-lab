# Week 4 distillation set (recorded evidence)

[Glossary](../../../docs/glossary.md) · [Week 4 README](../../README.md) · [Distillation and DPO README](../README.md)

The supervised fine-tuning set for context distillation: each example pairs a training question with the SQL the
teacher wrote for it, kept only where the teacher's result matched the reference. The system prompt has the schema
but not the business rules, so the student must learn to apply the rules without seeing them. `construir_datasets.py`
builds `train.jsonl` from the teacher answers in [`../data/`](../data/README.md). The `lora/` files hold the same
examples, split into the train and validation files that mlx-lm expects; no script in the repository writes them.

**Recorded evidence:** these files are the training data built from the recorded teacher run, kept exactly as
written (not edited, not translated). The questions and the system prompt are the Spanish ones of week 3. The
English summary of the distillation results is in the
[Results](../README.md#results) section of the distillation and DPO README; the evaluation run itself is
`semana-03/resultados/destilacion150_*` ([its README](../../../semana-03/resultados/README.md)).

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `train.jsonl` | All the distillation examples, one chat example per line (system prompt, question, teacher's SQL) | Written by `construir_datasets.py` |
| `lora/*.jsonl` | The same examples, split into `train.jsonl` and `valid.jsonl` | Split for `mlx_lm.lora` (no script in the repository writes them); read by `mlx_lm.lora` |
